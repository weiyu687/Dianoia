import warnings
from html import escape
from io import BytesIO

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from ..models import identifier
from .models import QuestionAsset
from .service import FILES

THEMES = [
    {"id": "academic", "name": "极简学术", "background": "#f2eee7", "ink": "#252333", "accent": "#7759ce"},
    {"id": "blue", "name": "蓝白科技", "background": "#eaf2ff", "ink": "#153568", "accent": "#396bd5"},
    {"id": "paper", "name": "暖纸书页", "background": "#f5e8d9", "ink": "#50372c", "accent": "#b56443"},
    {"id": "nature", "name": "青绿自然", "background": "#e7f2ec", "ink": "#173e35", "accent": "#25846d"},
    {"id": "purple", "name": "紫色几何", "background": "#eeebfc", "ink": "#352561", "accent": "#7759ce"},
    {"id": "grid", "name": "深色网格", "background": "#172433", "ink": "#f0f4ff", "accent": "#6ed8d1"},
]


def cover_svg(title, course, cover):
    theme = next((t for t in THEMES if t["id"] == cover.get("theme")), THEMES[0])
    background, ink, accent = theme["background"], theme["ink"], cover.get("accent") or theme["accent"]
    # Only known templates and escaped text are rendered; never render uploaded SVG.
    shapes = {
        "academic": f'<path d="M875 0h325v675H875z" fill="{accent}" opacity=".12"/><circle cx="1080" cy="160" r="230" fill="none" stroke="{accent}" stroke-width="2"/><path d="M895 400h175m-175 30h125" stroke="{accent}" stroke-width="12"/>',
        "blue": f'<path d="M750 675L1200 200v475zM920 0h280v280z" fill="{accent}" opacity=".18"/><circle cx="1110" cy="155" r="95" fill="{accent}" opacity=".22"/>',
        "paper": f'<rect x="880" y="130" width="255" height="440" rx="15" fill="{accent}" opacity=".12" transform="rotate(12 1000 300)"/><path d="M930 230h140m-140 35h140m-140 35h90" stroke="{accent}" stroke-width="5"/>',
        "nature": f'<ellipse cx="1090" cy="185" rx="145" ry="260" fill="{accent}" opacity=".15" transform="rotate(-36 1090 185)"/><ellipse cx="980" cy="570" rx="170" ry="240" fill="{accent}" opacity=".16"/>',
        "purple": f'<circle cx="1090" cy="80" r="220" fill="{accent}" opacity=".18"/><rect x="840" y="390" width="330" height="330" rx="70" fill="{accent}" opacity=".20" transform="rotate(24 1000 500)"/>',
        "grid": f'<defs><pattern id="g" width="55" height="55" patternUnits="userSpaceOnUse"><path d="M55 0H0v55" fill="none" stroke="{accent}" opacity=".12"/></pattern></defs><rect width="1200" height="675" fill="url(#g)"/><circle cx="1060" cy="260" r="200" fill="none" stroke="{accent}" opacity=".3" stroke-width="2"/>',
    }[theme["id"]]
    centered = cover.get("layout") == "center"
    x, anchor = (600, "middle") if centered else (85, "start")
    lines = [title[i:i + 17] for i in range(0, min(len(title), 51), 17)] or ["未命名题库"]
    if len(title) > 51:
        lines[-1] = lines[-1][:-1] + "…"
    text = "".join(f'<tspan x="{x}" dy="{0 if i == 0 else 77}">{escape(line)}</tspan>' for i, line in enumerate(lines))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">'
            f'<rect width="1200" height="675" fill="{background}"/>{shapes}'
            f'<g font-family="Microsoft YaHei,PingFang SC,Noto Sans CJK SC,sans-serif" text-anchor="{anchor}">'
            f'<text x="{x}" y="106" fill="{accent}" font-size="22" letter-spacing="3">DIANOIA · 自主练习</text>'
            f'<text x="{x}" y="{280 if len(lines) < 3 else 230}" fill="{ink}" font-size="59" font-weight="700">{text}</text>'
            f'<text x="{x}" y="585" fill="{ink}" opacity=".6" font-size="25">{escape(course[:36])}</text></g></svg>').encode()


def save_image(db, bank, raw, filename, kind, crop=None):
    if not raw or len(raw) > 5 * 1024 * 1024:
        raise HTTPException(422, "图片应为 5 MB 内的 JPG、PNG 或 WebP")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"} or original.width * original.height > 20000000:
                    raise ValueError("不支持的图片格式或图片超过 2000 万像素")
                image = ImageOps.exif_transpose(original)
                if kind == "cover" and ("A" in image.getbands() or "transparency" in image.info):
                    foreground = image.convert("RGBA")
                    image = Image.new("RGB", image.size, "white")
                    image.paste(foreground, mask=foreground.getchannel("A"))
                else:
                    image = image.convert("RGBA" if kind == "image" and ("A" in image.getbands() or "transparency" in image.info) else "RGB")
                image.info.clear()
        if kind == "cover":
            if crop:
                x, y, width, height = crop
                if not 0 < width <= 1 or not 0 < height <= 1 or x < 0 or y < 0 or x + width > 1.001 or y + height > 1.001:
                    raise ValueError("封面裁剪区域超出图片边界")
                bounds = (round(x * image.width), round(y * image.height), min(image.width, round((x + width) * image.width)), min(image.height, round((y + height) * image.height)))
                if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                    raise ValueError("裁剪区域过小")
                image = image.crop(bounds)
            image = ImageOps.fit(image, (1200, 675), method=Image.Resampling.LANCZOS)
        else:
            image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
        asset = QuestionAsset(id=identifier(), bank_id=bank.id, name=filename[:255], kind=kind, width=image.width, height=image.height)
        FILES.mkdir(parents=True, exist_ok=True)
        image.save(FILES / (asset.id + ".webp"), "WEBP", quality=88)
        if kind == "cover":
            image.resize((400, 225), Image.Resampling.LANCZOS).save(FILES / (asset.id + "-thumb.webp"), "WEBP", quality=85)
        db.add(asset)
        return asset
    except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise HTTPException(422, "无法处理图片，请检查格式、大小及裁剪区域") from error
