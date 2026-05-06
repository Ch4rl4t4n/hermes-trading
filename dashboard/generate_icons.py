#!/usr/bin/env python3
"""Generate Hermes PWA icons (PNG + WebP) under dashboard/static/icons/."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

_BG = "#0a0a0f"
_IN = "#6366f1"
_IN_HI = "#818cf8"
_SIZES = (72, 96, 128, 144, 152, 192, 384, 512)


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _draw_icon(size: int, *, maskable: bool) -> Image.Image:
    """Indigo H monogram on dark field; maskable uses larger inset (safe zone)."""
    img = Image.new("RGBA", (size, size), (10, 10, 15, 255))
    draw = ImageDraw.Draw(img)

    inset = int(round(size * 0.14)) if maskable else int(round(size * 0.08))
    w = size - 2 * inset
    cx, cy = size // 2, size // 2

    r0, g0, b0 = _hex_rgb(_BG)
    r1, g1, b1 = _hex_rgb(_IN)
    r2, g2, b2 = _hex_rgb(_IN_HI)
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(r0 + (r1 + (r2 - r1) * t - r0) * 0.22)
        g = int(g0 + (g1 + (g2 - g1) * t - g0) * 0.22)
        b = int(b0 + (b1 + (b2 - b1) * t - b0) * 0.22)
        draw.line([(0, y), (size, y)], fill=(max(0, r), max(0, g), max(0, b), 255))

    bar = max(2, w // 10)
    gap = int(bar * 1.15)
    h_top = cy - w // 3
    h_bot = cy + w // 3
    mid_y1 = cy - w // 8
    mid_y2 = cy + w // 8
    xl = cx - gap - bar // 2
    xr = cx + gap - bar // 2
    rr = bar // 2
    col = _hex_rgb(_IN) + (255,)
    col_hi = _hex_rgb(_IN_HI) + (255,)

    draw.rounded_rectangle([xl, h_top, xl + bar, h_bot], radius=rr, fill=col)
    draw.rounded_rectangle([xr, h_top, xr + bar, h_bot], radius=rr, fill=col)
    draw.rounded_rectangle([xl, mid_y1, xr + bar, mid_y2], radius=rr, fill=col_hi)
    return img


def main() -> None:
    root = Path(__file__).resolve().parent
    out = root / "static" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    for sz in _SIZES:
        im = _draw_icon(sz, maskable=False)
        stem = f"icon-{sz}"
        im.save(out / f"{stem}.png", "PNG", optimize=True)
        im.save(out / f"{stem}.webp", "WEBP", quality=90, method=6)
        if sz in (192, 512):
            imm = _draw_icon(sz, maskable=True)
            imm.save(out / f"{stem}-maskable.png", "PNG", optimize=True)
            imm.save(out / f"{stem}-maskable.webp", "WEBP", quality=90, method=6)
    print("Wrote icons to", out)


if __name__ == "__main__":
    main()
