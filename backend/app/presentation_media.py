import json
import os
import shutil
import subprocess
from contextlib import suppress
from math import isfinite
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from .db import DATA_DIR
from .models import PresentationMedia, identifier

MEDIA = DATA_DIR / "presentation-media"
MIME = {"audio": "audio/mpeg", "video": "video/mp4"}
SUFFIX = {"audio": ".mp3", "video": ".mp4"}
MAX_FILE_SIZE = 32 * 1024 * 1024
MAX_DECK_SIZE = 96 * 1024 * 1024


def media_path(asset):
    return MEDIA / (asset.id + SUFFIX[asset.kind])


def media_view(asset):
    return {key: getattr(asset, key) for key in ("id", "kind", "filename", "size", "duration_ms", "width", "height")}


def probe_media(path, kind):
    probe = os.getenv("DIANOIA_FFPROBE") or shutil.which("ffprobe")
    if not probe:
        raise HTTPException(503, "服务器未配置 ffprobe，暂时无法上传音视频")
    options = ["-f", "mov", "-enable_drefs", "0", "-use_absolute_path", "0"] if kind == "video" else ["-f", "mp3"]
    try:
        result = subprocess.run(
            [probe, "-v", "error", "-max_alloc", "134217728", "-protocol_whitelist", "file", *options, "-show_entries",
             "format=duration:stream=codec_name,codec_type,width,height:stream_disposition=attached_pic", "-of", "json", str(path)],
            check=True, capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        if not isfinite(duration) or not 0 < duration <= 8 * 60 * 60:
            raise ValueError
        streams = data["streams"]
        video = [entry for entry in streams if entry.get("codec_type") == "video" and not entry.get("disposition", {}).get("attached_pic")]
        audio = [entry for entry in streams if entry.get("codec_type") == "audio"]
        if kind == "audio" and not video and len(audio) == 1 and audio[0].get("codec_name") == "mp3":
            return round(duration * 1000), 0, 0
        if kind == "video" and len(video) == 1 and video[0].get("codec_name") == "h264" and all(s.get("codec_name") == "aac" for s in audio):
            width, height = int(video[0]["width"]), int(video[0]["height"])
            if 0 < width <= 4096 and 0 < height <= 4096:
                return round(duration * 1000), width, height
        raise ValueError
    except OSError as error:
        raise HTTPException(503, "无法调用服务器的 ffprobe，请检查部署配置") from error
    except (subprocess.SubprocessError, ValueError, TypeError, KeyError) as error:
        raise HTTPException(422, "请选择有效的 MP3 音频或 H.264/AAC MP4 视频（最高 4096 像素）") from error


def upload_media(db, user, course_id, kind, file):
    name = Path((file.filename or "").replace("\\", "/")).name
    name = "".join(character for character in name if character.isprintable())
    if not name or not name.lower().endswith(SUFFIX[kind]):
        raise HTTPException(415, "请选择 MP3 音频" if kind == "audio" else "请选择 MP4 视频")
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(413, "音视频文件不能超过 32 MB")
    key = identifier()
    MEDIA.mkdir(parents=True, exist_ok=True)
    temporary = MEDIA / (key + ".upload")
    size = 0
    try:
        with temporary.open("xb") as destination:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    raise HTTPException(413, "音视频文件不能超过 32 MB")
                destination.write(chunk)
        if not size:
            raise HTTPException(422, "音视频文件为空")
        if kind == "video":
            with temporary.open("rb") as handle:
                if handle.read(8)[4:] != b"ftyp":
                    raise HTTPException(422, "请选择有效的 MP4 容器")
        duration_ms, width, height = probe_media(temporary, kind)
        if len(name) > 160:
            name = name[:156] + SUFFIX[kind]
        asset = PresentationMedia(id=key, owner_id=user.id, course_id=course_id, filename=name, kind=kind,
                                  size=size, duration_ms=duration_ms, width=width, height=height)
        final = media_path(asset)
        temporary.replace(final)
        try:
            db.add(asset)
            db.commit()
        except Exception:
            with suppress(OSError):
                final.unlink()
            raise
        return media_view(asset)
    finally:
        temporary.unlink(missing_ok=True)


def list_media(db, user, course_id):
    return db.scalars(select(PresentationMedia).where(PresentationMedia.owner_id == user.id,
                      PresentationMedia.course_id == course_id).order_by(PresentationMedia.created_at.desc()))


def media_for_deck(db, user, course_id, deck):
    references = {(item.media_id, item.kind) for slide in deck.slides for item in slide.elements if item.media_id}
    if not references:
        return {}
    assets = {asset.id: asset for asset in db.scalars(select(PresentationMedia).where(
        PresentationMedia.id.in_({key for key, _ in references}), PresentationMedia.owner_id == user.id, PresentationMedia.course_id == course_id,
    ))}
    if any(key not in assets or assets[key].kind != kind or not media_path(assets[key]).is_file()
           for key, kind in references):
        raise HTTPException(422, "课件引用了不可用的音视频，请重新选择")
    if sum(item.size for item in assets.values()) > MAX_DECK_SIZE:
        raise HTTPException(422, "单份课件的音视频总量不能超过 96 MB")
    return assets


def stream_media(asset):
    if not asset or not media_path(asset).is_file():
        raise HTTPException(404, "音视频文件不存在")
    return FileResponse(media_path(asset), media_type=MIME[asset.kind], filename=asset.filename, content_disposition_type="inline")
