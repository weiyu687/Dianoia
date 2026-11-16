import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Literal
from zipfile import BadZipFile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image
from pydantic import BaseModel, Field
from pypdf.errors import PdfReadError
from sqlalchemy import select, update

from .auth import DB, Teacher, course_access
from .course_media import (
    ROOT, CourseMediaError, executable, import_deck, normalize_avatar, normalize_voice,
    preset_assets, save_upload, talk_command, tts_command,
)
from .course_models import CourseAsset, CourseJob, CourseVoiceFolder, CourseVoiceSample, DigitalCourse
from .models import identifier, now

router = APIRouter(prefix="/api/digital-courses", tags=["digital courses"])
ACTIVE = ("queued", "running")
LEASE = timedelta(minutes=2)
MEDIA_TYPES = {"avatar": "image/png", "voice": "audio/wav"}
MB = 1024 * 1024


class Name(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CourseEdit(BaseModel):
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=160)
    scripts: list[str] = Field(min_length=1, max_length=40)
    avatar: str = Field(default="", max_length=64)
    voice: str = Field(default="", max_length=64)


class StartJob(BaseModel):
    revision: int = Field(ge=1)
    kind: Literal["scripts", "video", "audio"]
    page: int | None = Field(default=None, ge=1, le=40)
    replace_existing: bool = False


class FolderEdit(Name):
    reference_id: str | None = Field(default=None, max_length=32)


def project_path(project_id):
    return ROOT / "projects" / project_id


def job_path(project_id, job_id):
    return project_path(project_id) / "jobs" / job_id


def asset_path(asset):
    return ROOT / "assets" / f"{asset.id}.{'png' if asset.kind == 'avatar' else 'wav'}"


def find_project(db, user, project_id):
    row = db.get(DigitalCourse, project_id)
    if not row or row.owner_id != user.id:
        raise HTTPException(404, "数字课程不存在")
    course_access(db, user, row.course_id)
    return row


def find_asset(db, user, asset_id):
    row = db.get(CourseAsset, asset_id)
    if not row or row.owner_id != user.id:
        raise HTTPException(404, "素材不存在")
    return row


def find_folder(db, user, folder_id):
    row = db.get(CourseVoiceFolder, folder_id)
    if not row or row.owner_id != user.id:
        raise HTTPException(404, "声音档案不存在")
    return row


def folder_samples(db, folder):
    return db.scalars(select(CourseAsset).join(CourseVoiceSample, CourseVoiceSample.asset_id == CourseAsset.id)
                      .where(CourseVoiceSample.folder_id == folder.id, CourseAsset.owner_id == folder.owner_id)
                      .order_by(CourseAsset.created_at, CourseAsset.id)).all()


def asset_view(row):
    return {"id": row.id, "kind": row.kind, "name": row.name, "transcript": row.transcript, "preset": False}


def folder_view(db, folder):
    samples = folder_samples(db, folder)
    return {"id": folder.id, "name": folder.name, "reference_id": folder.reference_id,
            "samples": [asset_view(sample) for sample in samples]}


def asset_option(db, user, asset_id, kind):
    preset = next((item for item in preset_assets() if item["id"] == asset_id and item["kind"] == kind), None)
    if preset:
        return preset
    if kind == "voice" and asset_id.startswith("folder-"):
        folder = find_folder(db, user, asset_id.removeprefix("folder-"))
        sample = next((row for row in folder_samples(db, folder) if row.id == folder.reference_id), None)
        if not sample:
            raise HTTPException(422, f"请先为「{folder.name}」指定一条参考样本")
        return {"id": asset_id, "kind": kind, "name": folder.name, "path": asset_path(sample),
                "transcript": sample.transcript}
    row = find_asset(db, user, asset_id)
    if row.kind != kind:
        raise HTTPException(422, "素材类型不匹配")
    return {"id": row.id, "kind": row.kind, "name": row.name, "path": asset_path(row), "transcript": row.transcript}


def expire_job(db, row):
    if row.status == "running" and row.updated_at < now() - LEASE:
        db.execute(update(CourseJob).where(CourseJob.id == row.id, CourseJob.status == "running",
                                           CourseJob.updated_at == row.updated_at)
                   .values(status="failed", stage="任务中断", error="生产服务已中断，请重试"))
        db.commit()
        db.refresh(row)


def current_job(db, project):
    row = db.get(CourseJob, project.job_id) if project.job_id else None
    if row:
        expire_job(db, row)
    return row


def job_view(job):
    if not job:
        return None
    values = {key: getattr(job, key) for key in ("kind", "status", "stage", "completed", "total", "error")}
    return values | {"id": job.id, "page": job.input.get("page")}


def project_view(db, row, *, detail=True):
    result = {key: getattr(row, key) for key in ("id", "title", "filename", "revision", "avatar", "voice", "updated_at")}
    video = db.get(CourseJob, row.video_id) if row.video_id else None
    job = current_job(db, row)
    audio_available = bool(job and job.kind == "audio" and job.status == "succeeded" and job.input["revision"] == row.revision)
    result.update(job=job_view(job), page_count=len(row.slides), has_video=bool(video), audio_available=audio_available,
                  video_is_previous=bool(video and video.input["revision"] != row.revision))
    if detail:
        result["slides"] = row.slides
    return result


def update_project(db, row, expected_revision, **values):
    job = current_job(db, row)
    if job and job.status in ACTIVE:
        raise HTTPException(409, "当前项目有任务正在处理")
    result = db.execute(update(DigitalCourse).where(DigitalCourse.id == row.id,
                                                    DigitalCourse.revision == expected_revision,
                                                    DigitalCourse.job_id == row.job_id)
                        .values(**values))
    if result.rowcount != 1:
        raise HTTPException(409, "数字课程已更新，请刷新后重试")


@router.get("")
def list_projects(course_id: int, db: DB, user: Teacher):
    course_access(db, user, course_id)
    rows = db.scalars(select(DigitalCourse).where(DigitalCourse.owner_id == user.id, DigitalCourse.course_id == course_id)
                      .order_by(DigitalCourse.updated_at.desc())).all()
    return [project_view(db, row, detail=False) for row in rows]


@router.post("", status_code=201)
def upload_project(db: DB, user: Teacher, course_id: int = Form(), file: UploadFile = File()):
    course_access(db, user, course_id)
    original = Path((file.filename or "").replace("\\", "/")).name
    suffix = Path(original).suffix.lower()
    if suffix not in {".ppt", ".pptx"}:
        raise HTTPException(422, "请选择 PPT 或 PPTX 课件")
    entry_id = identifier()
    folder = project_path(entry_id)
    folder.mkdir(parents=True)
    source = folder / f"source{suffix}"
    try:
        save_upload(file.file, source, 50 * MB)
        slides = import_deck(source, folder)
        row = DigitalCourse(id=entry_id, owner_id=user.id, course_id=course_id, title=Path(original).stem[:160],
                            filename=original[:255], slides=slides)
        db.add(row)
        db.commit()
    except (CourseMediaError, ValueError, BadZipFile, PdfReadError, subprocess.SubprocessError, OSError) as error:
        shutil.rmtree(folder, ignore_errors=True)
        detail = str(error) if isinstance(error, CourseMediaError) else "无法读取课件，请检查文件后重新上传"
        raise HTTPException(422, detail) from error
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return project_view(db, row)


@router.get("/assets")
def list_assets(db: DB, user: Teacher):
    personal = db.scalars(select(CourseAsset).where(CourseAsset.owner_id == user.id)
                          .order_by(CourseAsset.created_at.desc())).all()
    presets = [{key: item[key] for key in ("id", "kind", "name")} | {"preset": True} for item in preset_assets()]
    return presets + [asset_view(row) for row in personal]


@router.post("/assets", status_code=201)
def upload_asset(db: DB, user: Teacher, kind: Literal["avatar", "voice"] = Form(), name: str = Form(max_length=100),
                 consent: bool = Form(), transcript: str = Form(default="", max_length=600), file: UploadFile = File(),
                 folder_id: str | None = Form(default=None, max_length=32)):
    if not consent or not name.strip():
        raise HTTPException(422, "请填写素材名称，并确认已获得使用授权")
    transcript = transcript.strip()
    if kind == "voice" and not transcript:
        raise HTTPException(422, "请填写与音频内容一致的样本文字")
    if folder_id and kind != "voice":
        raise HTTPException(422, "声音档案仅接受音频样本")
    folder = find_folder(db, user, folder_id) if folder_id else None
    row = CourseAsset(id=identifier(), owner_id=user.id, name=name.strip(), kind=kind,
                      transcript=transcript if kind == "voice" else "")
    target = asset_path(row)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".upload")
    try:
        save_upload(file.file, temp, 12 * MB)
        (normalize_avatar if kind == "avatar" else normalize_voice)(temp, target)
        db.add(row)
        if folder:
            db.flush()
            attach_sample(db, folder, row)
        db.commit()
    except (CourseMediaError, OSError, ValueError, Image.DecompressionBombError) as error:
        target.unlink(missing_ok=True)
        message = str(error) if isinstance(error, CourseMediaError) else "无法读取素材，请检查文件格式"
        raise HTTPException(422, message) from error
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        temp.unlink(missing_ok=True)
    return asset_view(row)


@router.get("/assets/{asset_id}/preview")
def preview_asset(asset_id: str, db: DB, user: Teacher):
    preset = next((item for item in preset_assets() if item["id"] == asset_id), None)
    if preset:
        return FileResponse(preset["path"], media_type=MEDIA_TYPES[preset["kind"]])
    row = find_asset(db, user, asset_id)
    return FileResponse(asset_path(row), media_type=MEDIA_TYPES[row.kind])


@router.patch("/assets/{asset_id}", status_code=204)
def rename_asset(asset_id: str, data: Name, db: DB, user: Teacher):
    row = find_asset(db, user, asset_id)
    if not data.name.strip():
        raise HTTPException(422, "素材名称不能为空")
    row.name = data.name.strip()
    db.commit()
    return Response(status_code=204)


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: str, db: DB, user: Teacher):
    row = find_asset(db, user, asset_id)
    relative = asset_path(row)
    db.delete(row)
    db.commit()
    relative.unlink(missing_ok=True)
    return Response(status_code=204)


def attach_sample(db, folder, asset):
    if asset.kind != "voice":
        raise HTTPException(422, "声音档案仅接受音频样本")
    existing = db.get(CourseVoiceSample, asset.id)
    if existing:
        if existing.folder_id != folder.id:
            raise HTTPException(409, "该样本已属于其他档案")
        return
    db.add(CourseVoiceSample(folder_id=folder.id, asset_id=asset.id))
    db.execute(update(CourseVoiceFolder).where(CourseVoiceFolder.id == folder.id,
                                             CourseVoiceFolder.reference_id.is_(None)).values(reference_id=asset.id))


@router.get("/voice-folders")
def list_voice_folders(db: DB, user: Teacher):
    rows = db.scalars(select(CourseVoiceFolder).where(CourseVoiceFolder.owner_id == user.id)
                      .order_by(CourseVoiceFolder.created_at.desc())).all()
    return [folder_view(db, folder) for folder in rows]


@router.post("/voice-folders", status_code=201)
def add_voice_folder(data: Name, db: DB, user: Teacher):
    if not data.name.strip():
        raise HTTPException(422, "请输入档案名称")
    folder = CourseVoiceFolder(owner_id=user.id, name=data.name.strip())
    db.add(folder)
    db.commit()
    return folder_view(db, folder)


@router.put("/voice-folders/{folder_id}")
def edit_voice_folder(folder_id: str, data: FolderEdit, db: DB, user: Teacher):
    folder = find_folder(db, user, folder_id)
    if not data.name.strip():
        raise HTTPException(422, "请输入档案名称")
    if data.reference_id and not any(sample.id == data.reference_id for sample in folder_samples(db, folder)):
        raise HTTPException(422, "请从此档案中选择参考样本")
    folder.name, folder.reference_id = data.name.strip(), data.reference_id
    db.commit()
    return folder_view(db, folder)


@router.post("/voice-folders/{folder_id}/samples/{asset_id}", status_code=204)
def assign_voice_sample(folder_id: str, asset_id: str, db: DB, user: Teacher):
    attach_sample(db, find_folder(db, user, folder_id), find_asset(db, user, asset_id))
    db.commit()
    return Response(status_code=204)


@router.delete("/voice-folders/{folder_id}", status_code=204)
def delete_voice_folder(folder_id: str, db: DB, user: Teacher):
    db.delete(find_folder(db, user, folder_id))
    db.commit()
    return Response(status_code=204)


@router.get("/{project_id}")
def get_project(project_id: str, db: DB, user: Teacher):
    return project_view(db, find_project(db, user, project_id))


@router.put("/{project_id}")
def edit_project(project_id: str, data: CourseEdit, db: DB, user: Teacher):
    row = find_project(db, user, project_id)
    if not data.title.strip() or len(data.scripts) != len(row.slides) or any(len(script) > 1500 for script in data.scripts):
        raise HTTPException(422, "请填写项目名称，每页口播稿限 1500 字")
    if data.avatar and data.avatar != row.avatar:
        asset_option(db, user, data.avatar, "avatar")
    if data.voice and data.voice != row.voice:
        asset_option(db, user, data.voice, "voice")
    slides = [slide | {"script": text.strip()} for slide, text in zip(row.slides, data.scripts)]
    update_project(db, row, data.revision, title=data.title.strip(), slides=slides,
                   avatar=data.avatar, voice=data.voice, revision=data.revision + 1)
    db.commit()
    return project_view(db, row)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, revision: int, db: DB, user: Teacher):
    row = find_project(db, user, project_id)
    update_project(db, row, revision, revision=revision + 1)
    db.delete(row)
    db.commit()
    shutil.rmtree(project_path(project_id), ignore_errors=True)
    return Response(status_code=204)


@router.get("/{project_id}/pages/{page}")
def get_page(project_id: str, page: int, db: DB, user: Teacher):
    row = find_project(db, user, project_id)
    if not 1 <= page <= len(row.slides):
        raise HTTPException(404, "页面不存在")
    return FileResponse(project_path(row.id) / f"page-{page}.png", media_type="image/png")


@router.post("/{project_id}/jobs", status_code=202)
def start_job(project_id: str, data: StartJob, db: DB, user: Teacher):
    row = find_project(db, user, project_id)
    indexes = [data.page - 1] if data.page else [
        i for i, slide in enumerate(row.slides) if data.replace_existing or not slide["script"]
    ]
    spec = {"revision": data.revision}
    folder = job_path(row.id, identifier())
    if data.kind == "scripts":
        if not indexes or any(index >= len(row.slides) for index in indexes):
            raise HTTPException(422, "没有需要生成口播稿的页面")
        spec["indexes"] = indexes
    else:
        if data.kind == "audio" and (not data.page or data.page > len(row.slides)):
            raise HTTPException(422, "请选择需要试听的页面")
        scripts = [row.slides[data.page - 1]["script"]] if data.kind == "audio" else [slide["script"] for slide in row.slides]
        if not row.voice or any(not text.strip() for text in scripts):
            raise HTTPException(422, "请选择音色并填写需要生成的口播稿")
        if data.kind == "video" and not row.avatar:
            raise HTTPException(422, "请先选择讲师形象")
        avatar = asset_option(db, user, row.avatar, "avatar") if data.kind == "video" else None
        voice = asset_option(db, user, row.voice, "voice")
        try:
            tts_command(voice.get("preset"))
            if data.kind == "video":
                executable("ffmpeg")
                talk_command()
        except CourseMediaError as error:
            raise HTTPException(503, str(error)) from error
        spec.update(scripts=scripts, page=data.page if data.kind == "audio" else None, preset=voice.get("preset"),
                    transcript=voice.get("transcript", ""))
    previous = db.get(CourseJob, row.job_id) if row.job_id else None
    update_project(db, row, data.revision, job_id=folder.name)
    try:
        if data.kind != "scripts":
            folder.mkdir(parents=True)
            if avatar:
                shutil.copyfile(avatar["path"], folder / "avatar.png")
            if not spec["preset"]:
                shutil.copyfile(voice["path"], folder / "voice.wav")
        job = CourseJob(id=folder.name, project_id=row.id, kind=data.kind, input=spec,
                        total=len(indexes) if data.kind == "scripts" else len(scripts))
        db.add(job)
        db.commit()
    except OSError as error:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(422, "所选素材已不可用，请重新选择") from error
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    if previous and previous.kind == "audio":
        shutil.rmtree(job_path(row.id, previous.id), ignore_errors=True)
    return project_view(db, row)


@router.get("/{project_id}/audio")
def course_audio(project_id: str, db: DB, user: Teacher):
    row = find_project(db, user, project_id)
    job = current_job(db, row)
    if not job or job.kind != "audio" or job.status != "succeeded" or job.input["revision"] != row.revision:
        raise HTTPException(404, "该讲稿暂无可用试听")
    return FileResponse(job_path(row.id, job.id) / "preview.wav", media_type="audio/wav")


@router.get("/{project_id}/video")
def course_video(project_id: str, db: DB, user: Teacher, download: bool = False):
    row = find_project(db, user, project_id)
    if not row.video_id:
        raise HTTPException(404, "课程视频尚未生成")
    path = job_path(row.id, row.video_id) / "course.mp4"
    if not path.is_file():
        raise HTTPException(404, "课程视频已不可用")
    return FileResponse(path, media_type="video/mp4", filename=f"{row.title}.mp4" if download else None)
