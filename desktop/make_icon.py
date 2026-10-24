"""Draws the app icon (navy disc, brass ring, DHC) as icon.ico and icon.icns."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.ellipse((40, 40, S - 40, S - 40), fill=(31, 42, 68))
d.ellipse((110, 110, S - 110, S - 110), outline=(214, 180, 121), width=28)
try:
    font = ImageFont.truetype("arialbd.ttf", 300)
except OSError:
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 300)
    except OSError:
        font = ImageFont.load_default(size=300)
d.text((S / 2, S / 2), "DHC", font=font, fill=(250, 248, 244), anchor="mm")
img.save(HERE / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
try:
    img.save(HERE / "icon.icns")
except Exception:  # only the Mac build needs it
    pass
