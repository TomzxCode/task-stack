from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

_SIZE = 64
def _fg_for(bg: tuple[int, int, int]) -> tuple[int, int, int]:
    # W3C relative luminance (WCAG 2.x)
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = bg
    L = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    return (0, 0, 0) if L > 0.179 else (255, 255, 255)

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]

# Default thresholds: list of (min_count, rgb), sorted descending.
# First entry where count >= min_count wins. count==0 always uses grey.
DEFAULT_THRESHOLDS: list[tuple[int, tuple[int, int, int]]] = [
    (11, (200, 50, 50)),    # red
    (6,  (220, 180, 0)),    # yellow
    (1,  (70, 130, 180)),   # blue
]
_BG_EMPTY = (120, 120, 120)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_icon(
    count: int,
    thresholds: list[tuple[int, tuple[int, int, int]]] | None = None,
) -> Image.Image:
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS

    if count == 0:
        color: tuple[int, int, int] = _BG_EMPTY
    else:
        color = thresholds[-1][1]
        for min_count, rgb in sorted(thresholds, key=lambda t: t[0], reverse=True):
            if count >= min_count:
                color = rgb
                break

    img = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0, 0, _SIZE - 1, _SIZE - 1], fill=color)

    label = str(min(count, 99)) if count > 0 else ""
    if label:
        font_size = 42 if len(label) == 1 else 30
        font = _load_font(font_size)
        bbox = draw.textbbox((0, 0), label, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((_SIZE - w) / 2 - bbox[0], (_SIZE - h) / 2 - bbox[1]),
            label,
            font=font,
            fill=_fg_for(color),
        )
    return img
