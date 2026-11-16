import json
import logging
import os
import shutil
import subprocess
import wave
from pathlib import Path
from time import monotonic
from tempfile import TemporaryDirectory

from PIL import Image, ImageOps
from pypdf import PdfReader
from pptx import Presentation

from .db import DATA_DIR
from .documents import convert_with_office, validate_format

ROOT = DATA_DIR / "digital-courses"
PRESETS = Path(__file__).parent / "course_presets"
VOICE_PRESETS = {"zf_001": "普通话 · 女声", "zm_010": "普通话 · 男声"}
MAX_SLIDES = 40
PDF_FILTER = 'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}'
log = logging.getLogger(__name__)


class CourseMediaError(RuntimeError):
    pass


def executable(name):
    value = os.getenv(f"DIANOIA_{name.upper()}") or name
    result = shutil.which(value)
    if not result:
        raise CourseMediaError(f"服务器未配置 {name}")
    return result


def run(args, *, cwd=None, timeout=90, heartbeat=None):
    with TemporaryDirectory(prefix="dianoia-course-log-") as folder:
        with (Path(folder) / "process.log").open("w+b") as output:
            try:
                with subprocess.Popen(args, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL) as process:
                    deadline = monotonic() + timeout
                    try:
                        while process.poll() is None:
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                if monotonic() >= deadline:
                                    raise CourseMediaError("媒体处理超时")
                                if heartbeat:
                                    heartbeat()
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait()
            except OSError as error:
                raise CourseMediaError("无法启动媒体处理程序") from error
            if process.returncode:
                output.seek(max(0, output.tell() - 3000))
                log.warning("Media process exited with %s: %s", process.returncode, output.read().decode(errors="replace"))
                raise CourseMediaError("媒体处理程序执行失败")


def save_upload(file, target, limit):
    size = 0
    with target.open("wb") as output:
        while block := file.read(1024 * 1024):
            size += len(block)
            if size > limit:
                raise CourseMediaError(f"文件大小不能超过 {limit // (1024 * 1024)} MB")
            output.write(block)
    if not size:
        raise CourseMediaError("请选择非空文件")


def import_deck(source, folder):
    extension = source.suffix.lower()
    notes = []
    if extension == ".pptx":
        validate_format(source, "pptx")
        deck = Presentation(source)
        if not 1 <= len(deck.slides) <= MAX_SLIDES:
            raise CourseMediaError(f"课件需要包含 1 至 {MAX_SLIDES} 页")
        for slide in deck.slides:
            placeholder = slide.notes_slide.notes_text_frame if slide.has_notes_slide else None
            notes.append(placeholder.text[:3000] if placeholder else "")
    else:
        with source.open("rb") as file:
            if file.read(8) != bytes.fromhex("D0CF11E0A1B11AE1"):
                raise CourseMediaError("文件不是有效的 PowerPoint PPT")
    pdf = convert_with_office(source, PDF_FILTER, folder)
    if not pdf:
        raise CourseMediaError("无法转换课件，请检查 LibreOffice 配置与文件内容")
    reader = PdfReader(pdf)
    if not 1 <= len(reader.pages) <= MAX_SLIDES or (notes and len(notes) != len(reader.pages)):
        raise CourseMediaError(f"课件需要包含 1 至 {MAX_SLIDES} 页，且预览页数须与源文件一致")
    run([executable("pdftoppm"), "-r", "110", "-scale-to", "1440", "-png", str(pdf), str(folder / "slide")])
    for index, image in enumerate(sorted(folder.glob("slide-*.png")), 1):
        image.rename(folder / f"page-{index}.png")
    slides = []
    for index, page in enumerate(reader.pages):
        content = (page.extract_text() or "").strip()[:5000]
        slides.append({"title": next(iter(content.splitlines()), f"第 {index + 1} 页")[:100],
                       "text": content, "notes": notes[index] if notes else "", "script": ""})
    if any(not (folder / f"page-{index}.png").exists() for index in range(1, len(slides) + 1)):
        raise CourseMediaError("课件预览生成不完整")
    return slides


def normalize_avatar(source, output):
    with Image.open(source, formats=["PNG", "JPEG"]) as image:
        if image.width * image.height > 25_000_000 or min(image.size) < 256:
            raise CourseMediaError("请上传尺寸至少 256×256、像素总数不超过 2500 万的照片")
        result = ImageOps.exif_transpose(image).convert("RGB")
        result.thumbnail((1024, 1024))
        result.save(output, "PNG")


def audio_seconds(path):
    try:
        with wave.open(str(path), "rb") as audio:
            return audio.getnframes() / audio.getframerate()
    except (EOFError, OSError, wave.Error) as error:
        raise CourseMediaError("无法读取生成的 WAV 音频") from error


def normalize_voice(source, output):
    run([executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-protocol_whitelist", "file",
         "-format_whitelist", "wav,mp3", "-i", str(source), "-t", "31", "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", str(output)])
    if not 3 <= audio_seconds(output) <= 30:
        raise CourseMediaError("请上传 3 至 30 秒的清晰语音")


def tts_command(preset):
    if preset in VOICE_PRESETS:
        python = os.getenv("DIANOIA_COURSE_KOKORO_PYTHON")
        if python and shutil.which(python):
            return [python, str(Path(__file__).with_name("course_kokoro.py"))]
    try:
        values = json.loads(os.getenv("DIANOIA_COURSE_TTS_COMMAND", "[]"))
        if isinstance(values, list) and values and all(isinstance(value, str) and value for value in values):
            if shutil.which(values[0]):
                return values
    except ValueError:
        pass
    raise CourseMediaError("服务器尚未配置数字课程语音合成")


def talk_command():
    keys = ("ROOT", "PYTHON", "WAN", "WAV2VEC", "WEIGHTS")
    settings = [os.getenv(f"DIANOIA_INFINITETALK_{key}", "") for key in keys]
    root, python, wan, wav2vec, weights = map(Path, settings)
    if not all(settings) or not (root / "generate_infinitetalk.py").is_file() or not shutil.which(str(python)):
        raise CourseMediaError("服务器尚未配置 InfiniteTalk 推理环境")
    if not wan.is_dir() or not wav2vec.is_dir() or not weights.is_file():
        raise CourseMediaError("服务器缺少 InfiniteTalk 模型权重")
    return root.resolve(), [str(python), str((root / "generate_infinitetalk.py").resolve()),
                            "--ckpt_dir", str(wan.resolve()), "--wav2vec_dir", str(wav2vec.resolve()),
                            "--infinitetalk_dir", str(weights.resolve()), "--size", "infinitetalk-480",
                            "--mode", "streaming", "--motion_frame", "9", "--num_persistent_param_in_dit", "0"]


def preset_assets():
    rows = []
    for key, name in (("lecturer-lin", "林老师"), ("lecturer-chen", "陈老师")):
        path = PRESETS / f"{key}.png"
        if path.is_file():
            rows.append({"id": key, "kind": "avatar", "name": name, "path": path})
    for key, name in VOICE_PRESETS.items():
        path = PRESETS / f"{key}.wav"
        if path.is_file():
            rows.append({"id": "voice-" + key, "kind": "voice", "name": name, "path": path, "preset": key})
    if catalog := os.getenv("DIANOIA_COURSE_PRESET_VOICES"):
        try:
            records = json.loads(Path(catalog).read_text(encoding="utf-8"))
            used = set()
            for entry in records:
                key, name = entry["id"], entry["name"]
                if not isinstance(key, str) or not key.isascii() or not key.isalnum() or not 1 <= len(key) <= 40:
                    continue
                preview = Path(catalog).resolve().parent / entry["preview"]
                if key not in used and isinstance(name, str) and name.strip() and preview.is_file() and preview.suffix == ".wav":
                    rows.append({"id": "voice-" + key, "kind": "voice", "name": name[:100], "path": preview,
                                 "preset": key})
                    used.add(key)
        except (OSError, ValueError, TypeError, KeyError):
            log.warning("无法读取数字课程预置音色目录")
    return rows
