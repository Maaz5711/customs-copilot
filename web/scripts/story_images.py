"""Build the story photos: crop, grade to one dark cool look, export AVIF + WebP at three widths.

Originals (Unsplash License, see web/public/ASSETS.md) live in design-refs/story_photos_src/ (local only).
Run from the project root:  .venv/Scripts/python web/scripts/story_images.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "design-refs" / "story_photos_src"
OUT = ROOT / "web" / "public" / "story"
WIDTHS = (960, 1600)

# name -> (crop box in source pixels or None, warmth kept 0..1)
PHOTOS = {
    "01_arrival": (None, 0.0),
    "02_terminal": (None, 0.0),
    "03_yard": (None, 0.0),
    "04_doors": (None, 0.0),
    "05_papers": (None, 0.0),
    "06_cleared": ((630, 430, 2400, 1426), 0.85),  # crop out the chimney smoke on the left
}


def grade(im: Image.Image, warmth: float) -> Image.Image:
    im = im.convert("RGB")
    im = ImageEnhance.Color(im).enhance(0.78 + 0.25 * warmth)
    im = ImageEnhance.Brightness(im).enhance(0.72)
    im = ImageEnhance.Contrast(im).enhance(1.08)
    # cool navy tint in the shadows (skipped mostly for the warm "cleared" scene)
    tint = Image.new("RGB", im.size, (8, 22, 48))
    im = Image.blend(im, tint, 0.18 * (1 - warmth) + 0.05)
    # soft vignette so overlays and text read at the edges
    w, h = im.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((-w * 0.15, -h * 0.2, w * 1.15, h * 1.2), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) * 0.12))
    dark = Image.new("RGB", (w, h), (4, 9, 20))
    return Image.composite(im, dark, mask)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (box, warmth) in PHOTOS.items():
        im = Image.open(SRC / f"{name}.jpg")
        if box:
            im = im.crop(box)
        im = grade(im, warmth)
        for w in WIDTHS:
            if w > im.width and w != WIDTHS[0]:
                continue
            h = round(im.height * w / im.width)
            r = im.resize((w, h), Image.LANCZOS)
            r.save(OUT / f"{name}-{w}.avif", quality=52, speed=4)
            r.save(OUT / f"{name}-{w}.webp", quality=74, method=6)
        print(name, im.size)


if __name__ == "__main__":
    main()
