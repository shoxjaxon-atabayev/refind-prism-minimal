#!/usr/bin/env python3
"""
Regenerate every colour / background asset for the Prism Minimal rEFInd theme.

A "look" here is a **colour** x a **background**:

  * colour     — white (default) + green red violet pink gray blue
                 + premium iridescent obsidian-purple / titanium-silver /
                 champagne-gold
  * background — dark (black, default) or light (near-white)

rEFInd can't tint just the focused icon, so the whole icon set is recoloured
to the chosen hue; the selection is only an *outline* (rounded square on the OS
row, circle on the tool row) — no fill, no glow. On the light background the
hue is darkened for contrast and the icons go dark-on-white.

Every icon is also re-padded to a fixed content size so the row has consistent,
generous spacing regardless of how tightly each source icon was cropped.

Output (this script only writes here):

    backgrounds/<bg>.png                           solid colour, 64x64
    colors/<colour>/selection_big.png              256x256   (dark bg)
    colors/<colour>/selection_small.png             64x64
    colors/<colour>/icons/*.png
    colors/<colour>/light/selection_big.png                  (light bg)
    colors/<colour>/light/selection_small.png
    colors/<colour>/light/icons/*.png

Usage:
    python3 tools/generate.py                 # regenerate everything
    python3 tools/generate.py green blue      # just these colours
    python3 tools/generate.py --preview       # also write preview*.png

Dependencies: Pillow, numpy   (dev-only — never shipped to the ESP).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
COLORS_DIR = REPO / "colors"
ICONS_DIR = REPO / "icons"
BG_DIR = REPO / "backgrounds"

# ---------------------------------------------------------------- palette --

SIMPLE: dict[str, str] = {
    "white":  "#FFFFFF",
    "green":  "#40DC77",
    "red":    "#FF4D4D",
    "violet": "#8B5CF6",
    "pink":   "#FF74C4",
    "gray":   "#AAB2C0",
    "blue":   "#4D9DFF",
}

# Premium variants: an ordered loop of hue stops the colour cycles through
# (the list wraps). Weighted toward the name hue so it still reads as
# purple / silver / gold, with off-hues for the oil-slick shimmer.
PREMIUM: dict[str, list[str]] = {
    "obsidian-purple": ["#7A28D8", "#A838E8", "#D060E8", "#9A6CF6",
                        "#4E78F0", "#30C6D2", "#6E2CD0"],
    "titanium-silver": ["#9AA4B4", "#C4CEDC", "#EAF0F8", "#FCFEFF",
                        "#AEDCF2", "#DCC8F2", "#EEDCAC"],
    "champagne-gold":  ["#D0A24E", "#E6BE72", "#F4D68E", "#FFF2D2",
                        "#FFDCC6", "#F4B4C8", "#CCE8CC"],
}

PREMIUM_PHASE: dict[str, float] = {
    "obsidian-purple": 0.00,
    "titanium-silver": 0.37,
    "champagne-gold":  0.68,
}

ALL_VARIANTS = list(SIMPLE) + list(PREMIUM)

# Backgrounds and how the hue shifts for each.
BACKGROUNDS: dict[str, str] = {"dark": "#000000", "light": "#F4F4F5"}
LIGHT_DARKEN_SIMPLE = 0.52   # flat hue x this on the light background
LIGHT_DARKEN_PREMIUM = 0.58
WHITE_ON_LIGHT = "#2B2B2D"   # the "white" variant's ink on the light background

# --------------------------------------------------------------- geometry --

# Every icon is re-padded so its content fills this fraction of its (square)
# canvas — evens out the ~0.5-0.62 the source icons vary between. Combined with
# a large big_icon_size in theme.conf this gives big icons AND wide, even gaps.
ICON_CONTENT = 0.58

# The outline canvas is 256 / 64; rEFInd scales it to big_icon_size /
# small_icon_size (200 / 50 in theme.conf). `margin` is tuned so the outline
# sits just outside the re-padded icon; `border` is ~1.4x the on-screen stroke.
SPECS = {
    "big":   dict(px=256, shape="square", margin=34.0, radius=7.0, border=5.0),
    "small": dict(px=64,  shape="circle", margin=9.0, radius=0.0, border=3.0),
}
SS = 4  # supersample factor
BORDER_ALPHA = 1.0
RING_CYCLES_BIG = 2.0       # whole numbers only — seamless across the branch cut
RING_CYCLES_SMALL = 1.0


# ------------------------------------------------------------------ maths --

def hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float) / 255.0


def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def shape_sdf(shape: str, px: np.ndarray, py: np.ndarray,
              half: float, r: float) -> np.ndarray:
    """Signed distance (<0 inside) to a circle or rounded square at the origin."""
    if shape == "circle":
        return np.hypot(px, py) - half
    qx = np.abs(px) - (half - r)
    qy = np.abs(py) - (half - r)
    return (np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0))
            + np.minimum(np.maximum(qx, qy), 0.0) - r)


def gradient_lut(stops: list[str], n: int = 1024) -> np.ndarray:
    """A looped LUT (n,3): linear ramp through the stops, last wrapping to first."""
    cols = [hex_rgb(s) for s in stops]
    cols.append(cols[0])
    segs = len(cols) - 1
    lut = np.empty((n, 3), dtype=float)
    for i in range(n):
        f = (i / n) * segs
        k = int(f)
        frac = f - k
        lut[i] = cols[k] * (1.0 - frac) + cols[k + 1] * frac
    return lut


def downscale(arr: np.ndarray, size: int) -> np.ndarray:
    """LANCZOS downscale of a float array in [0,1]; keeps last axis for RGB."""
    mode = "L" if arr.ndim == 2 else "RGB"
    img = Image.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8), mode)
    img = img.resize((size, size), Image.LANCZOS)
    return np.asarray(img, dtype=float) / 255.0


def paint(variant: str, bg: str):
    """The colour for a (variant, background): ('flat', rgb) or ('grad', lut)."""
    if variant in PREMIUM:
        lut = gradient_lut(PREMIUM[variant])
        return "grad", lut * (LIGHT_DARKEN_PREMIUM if bg == "light" else 1.0)
    if variant == "white":
        return "flat", hex_rgb("#FFFFFF" if bg == "dark" else WHITE_ON_LIGHT)
    rgb = hex_rgb(SIMPLE[variant])
    return "flat", rgb * (LIGHT_DARKEN_SIMPLE if bg == "light" else 1.0)


# ---------------------------------------------------------------- outline --

def render_outline(kind: str, variant: str, bg: str) -> Image.Image:
    spec = SPECS[kind]
    size = spec["px"]
    hi = size * SS
    ys, xs = np.mgrid[0:hi, 0:hi].astype(float)
    c = (hi - 1) / 2.0
    px, py = xs - c, ys - c

    outer = (size / 2.0 - spec["margin"]) * SS
    bw = spec["border"] * SS
    r = spec["radius"] * SS
    aa = 1.1 * SS

    d_out = shape_sdf(spec["shape"], px, py, outer, r)
    d_in = shape_sdf(spec["shape"], px, py, outer - bw, max(r - bw, 0.4 * SS))
    ring = np.clip(smoothstep(aa, -aa, d_out) - smoothstep(aa, -aa, d_in), 0.0, 1.0)

    mode, col = paint(variant, bg)
    if mode == "grad":
        lut = col
        cycles = RING_CYCLES_BIG if kind == "big" else RING_CYCLES_SMALL
        theta = np.arctan2(py, px) / (2.0 * np.pi) + 0.5
        if spec["shape"] == "square":  # even the hue out across the corners
            theta = theta + 0.18 * ((xs / hi) * 0.58 + (ys / hi) * 0.42)
        t = np.mod((theta + PREMIUM_PHASE[variant]) * cycles, 1.0)
        stroke_rgb = downscale(lut[np.clip((t * len(lut)).astype(int), 0, len(lut) - 1)], size)
    else:
        stroke_rgb = np.broadcast_to(col, (size, size, 3)).astype(float)

    alpha = downscale(ring, size) * BORDER_ALPHA
    rgba = np.clip(np.dstack([stroke_rgb, alpha]), 0.0, 1.0)
    return Image.fromarray((rgba * 255.0 + 0.5).astype(np.uint8), "RGBA")


# ------------------------------------------------------------------ icons --

def pad_icon(img: Image.Image) -> Image.Image:
    """Re-centre an icon so its content fills ICON_CONTENT of the square canvas."""
    im = img.convert("RGBA")
    a = np.asarray(im)
    ys, xs = np.where(a[..., 3] > 8)
    if len(xs) == 0:
        return im
    content = im.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    w = im.size[0]
    s = (w * ICON_CONTENT) / max(content.size)
    nw, nh = max(1, round(content.size[0] * s)), max(1, round(content.size[1] * s))
    content = content.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    canvas.alpha_composite(content, ((w - nw) // 2, (w - nh) // 2))
    return canvas


def recolor_icon(padded: Image.Image, variant: str, bg: str) -> Image.Image:
    a = np.asarray(padded.convert("RGBA"), dtype=float) / 255.0
    if variant == "white" and bg == "dark":
        return Image.fromarray((a * 255.0 + 0.5).astype(np.uint8), "RGBA")  # keep as-is
    alpha = a[..., 3]
    h, w = alpha.shape
    mode, col = paint(variant, bg)
    if mode == "grad":
        lut = col
        ys, xs = np.mgrid[0:h, 0:w].astype(float)
        t = np.mod(((xs / max(w - 1, 1)) * 0.62 + (ys / max(h - 1, 1)) * 0.38)
                   * 1.25 + PREMIUM_PHASE[variant], 1.0)
        rgb = lut[np.clip((t * len(lut)).astype(int), 0, len(lut) - 1)]
    else:
        rgb = np.broadcast_to(col, (h, w, 3))
    out = np.clip(np.dstack([rgb, alpha]), 0.0, 1.0)
    return Image.fromarray((out * 255.0 + 0.5).astype(np.uint8), "RGBA")


def look_dir(variant: str, bg: str) -> Path:
    return COLORS_DIR / variant if bg == "dark" else COLORS_DIR / variant / "light"


def look_icon(variant: str, bg: str, name: str) -> Image.Image:
    return Image.open(look_dir(variant, bg) / "icons" / name).convert("RGBA")


# ----------------------------------------------------------------- driver --

def build_backgrounds() -> None:
    BG_DIR.mkdir(exist_ok=True)
    for name, hx in BACKGROUNDS.items():
        rgb = tuple(int(round(v * 255)) for v in hex_rgb(hx))
        Image.new("RGB", (64, 64), rgb).save(BG_DIR / f"{name}.png", optimize=True)


def build(variant: str) -> None:
    sources = sorted(ICONS_DIR.glob("*.png"))
    for bg in ("dark", "light"):
        d = look_dir(variant, bg)
        (d / "icons").mkdir(parents=True, exist_ok=True)
        render_outline("big", variant, bg).save(d / "selection_big.png", optimize=True)
        render_outline("small", variant, bg).save(d / "selection_small.png", optimize=True)
        for f in sources:
            recolor_icon(pad_icon(Image.open(f)), variant, bg).save(d / "icons" / f.name, optimize=True)
    print(f"  {variant:16s} -> colors/{variant}/  (+ light/)  {len(sources)} icons x2")


# ----------------------------------------------------------------- preview --

def _cell(bg_hex: str, size: int, *layers: Image.Image) -> Image.Image:
    tile = Image.new("RGBA", (size, size), tuple(int(round(v * 255)) for v in hex_rgb(bg_hex)) + (255,))
    for l in layers:
        tile.alpha_composite(l)
    return tile


def make_preview(variants: list[str]) -> None:
    if not (ICONS_DIR / "os_arch.png").exists():
        print("  (skipping preview: no icons)")
        return
    cell, pad, cols = 240, 22, 5
    chip = 84
    rows_per_bg = (len(variants) + cols - 1) // cols
    W = cols * cell + (cols + 1) * pad
    H = 2 * rows_per_bg * cell + (2 * rows_per_bg + 2) * pad + 40
    sheet = Image.new("RGB", (W, H), (17, 17, 19))

    for bi, bg in enumerate(("dark", "light")):
        y_off = bi * (rows_per_bg * cell + (rows_per_bg + 1) * pad + 20)
        for i, v in enumerate(variants):
            cx = pad + (i % cols) * (cell + pad)
            cy = y_off + 24 + pad + (i // cols) * (cell + pad)
            big = look_dir(v, bg) / "selection_big.png"
            small = look_dir(v, bg) / "selection_small.png"
            tile = _cell(BACKGROUNDS[bg], cell,
                         Image.open(big).convert("RGBA").resize((cell, cell), Image.LANCZOS),
                         look_icon(v, bg, "os_arch.png").resize((cell, cell), Image.LANCZOS))
            ox = cell - chip - 6
            tile.alpha_composite(Image.open(small).convert("RGBA").resize((chip, chip), Image.LANCZOS), (ox, ox))
            tile.alpha_composite(look_icon(v, bg, "func_shutdown.png").resize((chip, chip), Image.LANCZOS), (ox, ox))
            sheet.paste(tile.convert("RGB"), (cx, cy))

    dest = REPO / "preview.png"
    sheet.save(dest, optimize=True)
    print(f"  preview -> preview.png ({W}x{H}; rows: {', '.join(variants)}; dark then light)")


def make_menu_preview(variants: list[str]) -> None:
    os_names = [n for n in ("os_omarchy", "os_arch", "os_linux", "os_win11", "os_mac")
                if (ICONS_DIR / f"{n}.png").exists()]
    tool_names = [n for n in ("func_shutdown", "func_firmware", "func_about")
                  if (ICONS_DIR / f"{n}.png").exists()]
    if len(os_names) < 3:
        print("  (skipping menu preview: not enough icons)")
        return

    W, strip_h = 1280, 250
    big, small = 100, 25         # ~theme.conf 200/50 at 0.5 px per rEFInd px
    gap_big, gap_small = 16, 12  # rEFInd's own cell gap is small; the spacing
    sel_os, sel_tool = 1, 0      # you see comes from the icons' transparent pad
    combos = [(v, bg) for bg in ("dark", "light") for v in variants]
    panel = Image.new("RGB", (W, strip_h * len(combos)), (17, 17, 19))

    for row, (v, bg) in enumerate(combos):
        rgb = tuple(int(round(c * 255)) for c in hex_rgb(BACKGROUNDS[bg]))
        strip = Image.new("RGBA", (W, strip_h), rgb + (255,))
        sel_b = Image.open(look_dir(v, bg) / "selection_big.png").convert("RGBA").resize((big, big), Image.LANCZOS)
        sel_s = Image.open(look_dir(v, bg) / "selection_small.png").convert("RGBA").resize((small, small), Image.LANCZOS)

        x0 = (W - (len(os_names) * big + (len(os_names) - 1) * gap_big)) // 2
        y_os = 64
        for i, n in enumerate(os_names):
            x = x0 + i * (big + gap_big)
            if i == sel_os:
                strip.alpha_composite(sel_b, (x, y_os))
            strip.alpha_composite(look_icon(v, bg, f"{n}.png").resize((big, big), Image.LANCZOS), (x, y_os))

        tx0 = (W - (len(tool_names) * small + (len(tool_names) - 1) * gap_small)) // 2
        y_tool = y_os + big + 56
        for i, n in enumerate(tool_names):
            x = tx0 + i * (small + gap_small)
            if i == sel_tool:
                strip.alpha_composite(sel_s, (x, y_tool))
            strip.alpha_composite(look_icon(v, bg, f"{n}.png").resize((small, small), Image.LANCZOS), (x, y_tool))

        panel.paste(strip.convert("RGB"), (0, row * strip_h))

    dest = REPO / "preview-menu.png"
    panel.save(dest, optimize=True)
    print(f"  menu preview -> preview-menu.png ({panel.width}x{panel.height}; {', '.join(v for v, _ in combos)})")


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}

    variants = args or ALL_VARIANTS
    unknown = [v for v in variants if v not in ALL_VARIANTS]
    if unknown:
        print(f"unknown variant(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"available: {', '.join(ALL_VARIANTS)}", file=sys.stderr)
        return 2

    build_backgrounds()
    print(f"generating {len(variants)} colour(s) x 2 backgrounds")
    for v in variants:
        build(v)

    if "--preview" in flags:
        shown = [v for v in ALL_VARIANTS if v in variants] or ALL_VARIANTS
        make_preview(shown)
        make_menu_preview([v for v in ("white", "blue", "obsidian-purple") if v in shown] or shown[:3])

    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
