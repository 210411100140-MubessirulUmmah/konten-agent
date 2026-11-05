"""Thumbnail 1280x720: ambil frame dari video, gelapkan, tempel teks besar."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .common import run

FONTS = [
    "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
W, H = 1280, 720


def _font(size):
    for p in FONTS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def make_thumbnail(media, at_seconds, text, out_path, workdir):
    frame = Path(workdir) / "_frame.jpg"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{at_seconds:.2f}",
         "-i", media, "-frames:v", "1", "-q:v", "2", frame])
    img = Image.open(frame).convert("RGB")
    frame.unlink(missing_ok=True)

    # crop tengah ke 16:9, lalu resize
    ratio = W / H
    iw, ih = img.size
    if iw / ih > ratio:
        nw = int(ih * ratio)
        img = img.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else:
        nh = int(iw / ratio)
        img = img.crop((0, (ih - nh) // 2, iw, (ih - nh) // 2 + nh))
    img = img.resize((W, H), Image.LANCZOS).convert("RGBA")

    # gradasi gelap dari kiri supaya teks terbaca
    grad = Image.new("RGBA", (W, H))
    px = grad.load()
    for x in range(W):
        a = int(220 * max(0.0, 1 - x / (W * 0.85)))
        for y in range(H):
            px[x, y] = (0, 0, 0, a)
    img = Image.alpha_composite(img, grad)

    draw = ImageDraw.Draw(img)
    text = text.upper().strip() or "PODCAST"
    size = 130
    while size > 50:
        font = _font(size)
        lines = _wrap(draw, text, font, W * 0.62)
        if len(lines) <= 4 and max(draw.textlength(l, font=font) for l in lines) <= W * 0.62:
            break
        size -= 8
    line_h = size * 1.1
    y = (H - line_h * len(lines)) / 2
    for line in lines:
        draw.text((60, y), line, font=font, fill=(255, 214, 10), stroke_width=6, stroke_fill=(0, 0, 0))
        y += line_h
    img.convert("RGB").save(out_path, quality=92)
