"""Shared 1080p scene geometry and deterministic video compositing."""

import os
import wave
from array import array
from pathlib import Path
from sys import byteorder
from typing import Literal

from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel, Field

from .course_media import audio_seconds, executable, run


CANVAS = (1920, 1080)
Scene = Literal["auto", "studio", "focus", "pip"]


class StudioSettings(BaseModel):
    theme: Literal["navy", "paper", "chalk"] = "navy"
    layout: Scene = "auto"
    pages: list[Scene] = Field(default_factory=list, max_length=40)


THEMES = {
    "navy": {"name": "深蓝演播室", "top": "#1b3553", "bottom": "#091627",
             "accent": "#90c6ff", "ink": "#eff7ff", "frame": "#385674", "matte": "#0d1d30"},
    "paper": {"name": "暖白课堂", "top": "#f5eee3", "bottom": "#dcd0bd",
              "accent": "#965335", "ink": "#362920", "frame": "#b8a791", "matte": "#e5dbcd"},
    "chalk": {"name": "墨绿教室", "top": "#204b43", "bottom": "#112b27",
              "accent": "#a9e6c6", "ink": "#edf9f1", "frame": "#477a6f", "matte": "#122f2a"},
}

# Coordinates are [left, top, width, height] on the exported 1920 × 1080 canvas.
LAYOUTS = {
    "studio": {"name": "演播室", "slide": (72, 188, 1260, 710), "avatar": (1376, 282, 470, 616)},
    "focus": {"name": "课件全屏", "slide": (54, 102, 1812, 924), "avatar": None},
    "pip": {"name": "画中画", "slide": (54, 102, 1812, 924), "avatar": (1528, 658, 320, 330)},
}


def resolve_scene(settings, index, total):
    chosen = settings.pages[index] if index < len(settings.pages) else "auto"
    if chosen == "auto":
        chosen = settings.layout
    if chosen == "auto":
        chosen = "studio" if index in {0, total - 1} else "focus"
    return LAYOUTS[chosen]


def studio_font(size):
    configured = os.getenv("DIANOIA_COURSE_FONT")
    candidates = [configured, str(Path(os.getenv("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"),
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                  "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"]
    for filename in candidates:
        if filename:
            try:
                return ImageFont.truetype(filename, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def trim_title(draw, title, font, width):
    if draw.textlength(title, font=font) <= width:
        return title
    while title and draw.textlength(title + "…", font=font) > width:
        title = title[:-1]
    return title + "…"


def scene_background(image_path, slide, scene, theme, title, index, total):
    image = Image.linear_gradient("L").resize(CANVAS)
    image = ImageOps.colorize(image, theme["top"], theme["bottom"])
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1919, 5), fill=theme["accent"])
    draw.line((54, 85, 1866, 85), fill=theme["frame"], width=2)
    label = studio_font(33)
    draw.text((54, 25), trim_title(draw, " ".join(title.split()), label, 1550), font=label, fill=theme["ink"])
    draw.text((1866, 29), f"{index + 1:02} / {total:02}", anchor="ra", font=studio_font(28), fill=theme["accent"])
    left, top, width, height = scene["slide"]
    draw.rounded_rectangle((left - 8, top - 8, left + width + 8, top + height + 8), 14, fill=theme["frame"])
    draw.rectangle((left, top, left + width - 1, top + height - 1), fill=theme["matte"])
    with Image.open(slide) as source:
        content = ImageOps.contain(source.convert("RGB"), (width, height), Image.Resampling.LANCZOS)
    image.paste(content, (left + (width - content.width) // 2, top + (height - content.height) // 2))
    if scene["avatar"]:
        x, y, w, h = scene["avatar"]
        draw.rounded_rectangle((x - 8, y - 8, x + w + 8, y + h + 8), 14, fill=theme["frame"])
    image.save(image_path)


def can_normalize_audio(filename):
    # FFmpeg loudnorm cannot normalize a silent stream. Examine the bounded PCM chunks.
    with wave.open(str(filename), "rb") as audio:
        while chunk := audio.readframes(audio.getframerate()):
            samples = array("h", chunk)
            if byteorder == "big":
                samples.byteswap()
            if max(samples) >= 32 or min(samples) <= -32:
                return True
    return False


def compose_scene(folder, image, avatar, audio, heartbeat, *, settings, title, index, total):
    scene = resolve_scene(settings, index, total)
    theme = THEMES[settings.theme]
    backdrop = folder / "scene.png"
    scene_background(backdrop, image, scene, theme, title, index, total)
    output = folder / "segment.mp4"
    args = [executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-loop", "1", "-framerate", "25", "-i", str(backdrop)]
    if avatar:
        x, y, w, h = scene["avatar"]
        args += ["-i", str(avatar), "-i", str(audio), "-filter_complex_threads", "1", "-filter_complex",
                 f"[1:v]fps=25,scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2,"
                 f"crop={w}:{h}:(iw-ow)/2:(ih-oh)/3,setsar=1[portrait];"
                 f"[0:v][portrait]overlay={x}:{y}:eof_action=repeat,format=yuv420p[video]",
                 "-map", "[video]", "-map", "2:a:0"]
    else:
        args += ["-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-vf", "format=yuv420p"]
    if can_normalize_audio(audio):
        args += ["-af", "loudnorm=I=-18:TP=-2:LRA=7"]
    args += ["-t", f"{audio_seconds(audio):.3f}", "-c:v", "libx264", "-preset", "fast", "-crf", "19",
             "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "1",
             "-movflags", "+faststart", str(output)]
    run(args, timeout=600, heartbeat=heartbeat)
    return output
