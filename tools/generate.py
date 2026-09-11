#!/usr/bin/env python3
"""
Regenerate every colour / background asset for the Prism Minimal rEFInd theme.

A "look" here is a **colour** x a **background**:

  * colour     — white (default) + green red violet pink gray blue
                 + premium iridescent obsidian-purple / titanium-silver /
                 champagne-gold
                 + premium gradient aurora / solaris / forest / rose-gold /
                 cyberpunk / platinum — dark-background pieces
  * background — dark (black, default) or light (near-white)

rEFInd can't tint just the focused icon, so the whole icon set is recoloured
to the chosen hue (flat for SIMPLE, the same hue cycle for PREMIUM and
GRADIENT alike); the selection is an *outline* (rounded square on the OS row,
circle on the tool row) — no fill, no glow, except GRADIENT, which adds a
low-opacity fill plus an outer glow riding the same hue on top of that
outline, still inside the same ring geometry. On the light background flat/
iridescent/gradient hues are all darkened for contrast, and white's icons go
dark-on-white.

Every icon is also re-padded to a fixed content size so the row has consistent,
generous spacing regardless of how tightly each source icon was cropped.

There is no permanent, pre-generated `colors/` directory in this repository —
colour variants are build products, generated on demand (by install.sh, or by
hand) into a throwaway output directory.

Output:

    backgrounds/<bg>.png                           solid colour, 64x64
                                                     (only rewritten on a full,
                                                     no-args / no --out-dir run)
    <out>/<colour>/selection_big.png               1024x1024 (dark bg)
    <out>/<colour>/selection_small.png             256x256
    <out>/<colour>/icons/*.png
    <out>/<colour>/light/selection_big.png                   (light bg)
    <out>/<colour>/light/selection_small.png
    <out>/<colour>/light/icons/*.png

`<out>` is `--out-dir=PATH` if given, else `build/colors/` in this repo
checkout (gitignored — a local scratch dir, never committed).

Usage:
    python3 tools/generate.py                 # regenerate everything into build/colors/
    python3 tools/generate.py green blue      # just these colours
    python3 tools/generate.py --out-dir=/tmp/look white  # build one colour elsewhere
    python3 tools/generate.py --list          # print available colour names, one per line
    python3 tools/generate.py --preview       # also write preview*.png
    python3 tools/generate.py --icons-dir=PATH   # read source icons from PATH
                                                 # instead of icons/

Dependencies: Pillow, numpy   (never shipped to the ESP — install.sh checks
for these before it runs this script).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

REPO = Path(__file__).resolve().parent.parent
COLORS_DIR = REPO / "build" / "colors"   # default; override with --out-dir=PATH
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

# Premium gradients: a simple two-stop hue loop (start -> end -> back to
# start), for the dark background specifically. Tints the icon set the same
# way PREMIUM does, and on top of that render_outline() adds a low-opacity
# fill tile plus an outer glow riding the same hue around the outline.
GRADIENT: dict[str, list[str]] = {
    "aurora":     ["#00E676", "#00D4FF"],
    "solaris":    ["#FACC15", "#FB923C"],
    "forest":     ["#22C55E", "#84CC16"],
    "rose-gold":  ["#F472B6", "#FDE68A"],
    "cyberpunk":  ["#FF0080", "#00E5FF"],
    "platinum":   ["#9CA3AF", "#F3F4F6"],
}

GRADIENT_PHASE: dict[str, float] = {
    "aurora":    0.00,
    "solaris":   0.17,
    "forest":    0.34,
    "rose-gold": 0.51,
    "cyberpunk": 0.68,
    "platinum":  0.85,
}

# One combined lookup for the angular hue-cycle offset — used by every
# gradient-painted variant, iridescent PREMIUM or two-stop GRADIENT alike.
CYCLE_PHASE: dict[str, float] = {**PREMIUM_PHASE, **GRADIENT_PHASE}

ALL_VARIANTS = list(SIMPLE) + list(PREMIUM) + list(GRADIENT)

# Backgrounds and how the hue shifts for each.
BACKGROUNDS: dict[str, str] = {"dark": "#000000", "light": "#F4F4F5"}
LIGHT_DARKEN_SIMPLE = 0.52   # flat hue x this on the light background
LIGHT_DARKEN_PREMIUM = 0.58  # also used for GRADIENT — same treatment
WHITE_ON_LIGHT = "#2B2B2D"   # the "white" variant's ink on the light background

# GRADIENT-only selection extras: a translucent fill inside the ring and a
# soft glow outside it, both painted with the same hue field as the border
# stroke. Existing SIMPLE/PREMIUM variants never take this path — their
# render_outline() output is byte-for-byte what it always was.
GRADIENT_FILL_ALPHA = 0.14   # low-opacity tile behind the icon
GRADIENT_GLOW_ALPHA = 0.35   # glow strength right at the ring's outer edge
GRADIENT_GLOW_FALLOFF = 1.6  # >1 = fast-then-long fade, not a linear ramp

# --------------------------------------------------------------- geometry --

# Every icon is re-padded so its content fills this fraction of its canvas —
# evens out the ~0.5-0.62 the source icons vary between and, with a large
# big_icon_size in theme.conf, gives big icons AND wide, even gaps.
ICON_CONTENT = 0.58

# Master resolution multiplier. The OS icons in icons/ are 4x hi-res masters
# (Real-ESRGAN x4plus upscales of the originals), so every big asset is
# emitted at 4x the historical size — OS icons 1024, selection outlines to
# match. theme.conf still asks for big_icon_size 200 / small_icon_size 50, so
# rEFInd only ever *downscales* these at boot → crisp.
SCALE = 4

# OS icons emit at 256*SCALE (1024), downscaled to big_icon_size at boot.
# Function/tool icons emit at 64, not 128: a controlled study against rEFInd's
# actual egScaleImage() (libeg/image.c) -- a naive 2-tap bilinear with no
# area/box filter, so it only ever blends the 4 source pixels straddling each
# output sample -- found the max single-pixel alpha jump in the final 50px
# render fell from ~250/255 at 128px down to ~165/255 at 64px. The smaller
# master keeps the downscale ratio (64/50 = 1.28x) close to identity, so
# egScaleImage's taps land inside the master's own AA ramp instead of
# skipping across most of it. See FEATHER_SMALL below for the rest of the fix.
OUT_BIG, OUT_SMALL = 256 * SCALE, 64

# Small (func_/tool_) icons get a touch of alpha-only Gaussian feather after
# padding, widening their AA ramp before egScaleImage sees it -- this narrows
# the max single-step alpha jump in the final 50px render further without
# softening the icon's white interior (only edge pixels have any alpha
# gradient to blur). Tuned against a reference theme's shipped 64px icon run
# through the same egScaleImage math: 0.5px lands at reference-level edge
# smoothness (comparable max-jump and transition-pixel counts) while keeping
# the silhouette crisp, not blurry.
FEATHER_SMALL = 0.5

# The big outline canvas is 256*SCALE, the small one 64*SCALE; rEFInd scales
# them down to big_icon_size / small_icon_size (200 / 50 in theme.conf) — so
# `border` is a bit more than the thin on-screen stroke. `margin` keeps the
# outline just outside the re-padded icon. All four measures scale with SCALE.
SPECS = {
    "big":   dict(px=256 * SCALE, shape="square",
                  margin=34.0 * SCALE, radius=7.0 * SCALE, border=3.4 * SCALE),
    "small": dict(px=64 * SCALE, shape="circle",
                  margin=9.0 * SCALE, radius=0.0, border=2.3 * SCALE),
}
SS = 4  # supersample factor
# Cap the outline supersample buffer: at SCALE 4 the square outline is 1024 px
# and 1024*SS would be a 4096² float grid (OOM-prone on low-RAM boxes). A
# rounded-rect stroke needs no more than ~2x SSAA at that size; the smaller
# circle outline stays at the full factor.
MAX_OUTLINE_RES = 2048
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


def clear_transparent_rgb(rgba_u8: np.ndarray) -> np.ndarray:
    """Zero the RGB of fully-transparent pixels (alpha == 0) in place, so
    transparent regions carry no colour — smaller PNGs and no matte / fringe
    risk for any downstream compositor."""
    rgba_u8[rgba_u8[..., 3] == 0, 0:3] = 0
    return rgba_u8


def downscale(arr: np.ndarray, size: int) -> np.ndarray:
    """LANCZOS downscale of a float array in [0,1]; keeps last axis for RGB."""
    mode = "L" if arr.ndim == 2 else "RGB"
    img = Image.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8), mode)
    img = img.resize((size, size), Image.LANCZOS)
    return np.asarray(img, dtype=float) / 255.0


def paint(variant: str, bg: str):
    """The colour for a (variant, background): ('flat', rgb) or ('grad', lut)."""
    if variant in PREMIUM or variant in GRADIENT:
        stops = PREMIUM[variant] if variant in PREMIUM else GRADIENT[variant]
        lut = gradient_lut(stops)
        return "grad", lut * (LIGHT_DARKEN_PREMIUM if bg == "light" else 1.0)
    if variant == "white":
        return "flat", hex_rgb("#FFFFFF" if bg == "dark" else WHITE_ON_LIGHT)
    rgb = hex_rgb(SIMPLE[variant])
    return "flat", rgb * (LIGHT_DARKEN_SIMPLE if bg == "light" else 1.0)


# ---------------------------------------------------------------- outline --

def render_outline(kind: str, variant: str, bg: str) -> Image.Image:
    spec = SPECS[kind]
    size = spec["px"]
    ss = SS if size * SS <= MAX_OUTLINE_RES else MAX_OUTLINE_RES / size
    hi = int(round(size * ss))
    ys, xs = np.mgrid[0:hi, 0:hi].astype(float)
    c = (hi - 1) / 2.0
    px, py = xs - c, ys - c

    outer = (size / 2.0 - spec["margin"]) * ss
    bw = spec["border"] * ss
    r = spec["radius"] * ss
    aa = 1.1 * ss

    d_out = shape_sdf(spec["shape"], px, py, outer, r)
    d_in = shape_sdf(spec["shape"], px, py, outer - bw, max(r - bw, 0.4 * ss))
    ring = np.clip(smoothstep(aa, -aa, d_out) - smoothstep(aa, -aa, d_in), 0.0, 1.0)

    mode, col = paint(variant, bg)
    if mode == "grad":
        lut = col
        cycles = RING_CYCLES_BIG if kind == "big" else RING_CYCLES_SMALL
        theta = np.arctan2(py, px) / (2.0 * np.pi) + 0.5
        if spec["shape"] == "square":  # even the hue out across the corners
            theta = theta + 0.18 * ((xs / hi) * 0.58 + (ys / hi) * 0.42)
        t = np.mod((theta + CYCLE_PHASE[variant]) * cycles, 1.0)
        stroke_rgb = downscale(lut[np.clip((t * len(lut)).astype(int), 0, len(lut) - 1)], size)
    else:
        stroke_rgb = np.broadcast_to(col, (size, size, 3)).astype(float)

    alpha = downscale(ring, size) * BORDER_ALPHA

    # GRADIENT-only extras: a low-opacity fill inside the ring and a soft glow
    # outside it, both riding the same hue field as the stroke. SIMPLE/PREMIUM
    # variants never touch this — their output is unchanged from before.
    if variant in GRADIENT:
        fill_mask = downscale(smoothstep(aa, -aa, d_in), size)
        glow_span = max(spec["margin"] * ss, 1.0)
        glow_raw = np.clip(1.0 - np.maximum(d_out, 0.0) / glow_span, 0.0, 1.0) ** GRADIENT_GLOW_FALLOFF
        glow_mask = downscale(np.where(d_out > 0.0, glow_raw, 0.0), size)
        alpha = np.clip(
            alpha + fill_mask * GRADIENT_FILL_ALPHA + glow_mask * GRADIENT_GLOW_ALPHA,
            0.0, 1.0)

    rgba = np.clip(np.dstack([stroke_rgb, alpha]), 0.0, 1.0)
    return Image.fromarray(
        clear_transparent_rgb((rgba * 255.0 + 0.5).astype(np.uint8)), "RGBA")


# ------------------------------------------------------------------ icons --

def pad_icon(img: Image.Image, out: int, sharpen: bool = True, feather: float = 0.0) -> Image.Image:
    """Re-centre an icon's content to ICON_CONTENT of an `out`-px canvas. When
    `sharpen`, also crisp the edges: a light unsharp mask undoes interpolation
    softness and a steep contrast curve on the alpha pulls the anti-aliased
    border back to a tight ~1 px — so it still reads clean after rEFInd's own
    downscale. Function/tool icons render at a flat 64px with `sharpen` off:
    that post-processing was tuned for the big OS icons' 1024->200 downscale
    and just adds ringing ahead of the small icons' 64->50 one. `feather`
    (small icons only) is a Gaussian blur applied to the alpha channel alone
    after compositing — it widens the AA ramp for egScaleImage's naive 2-tap
    bilinear without touching the interior's flat 255 alpha."""
    im = img.convert("RGBA")
    a = np.asarray(im)
    ys, xs = np.where(a[..., 3] > 8)
    if len(xs) == 0:
        return im.resize((out, out), Image.LANCZOS)
    content = im.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    s = (out * ICON_CONTENT) / max(content.size)
    nw, nh = max(1, round(content.size[0] * s)), max(1, round(content.size[1] * s))
    content = content.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (out, out), (0, 0, 0, 0))
    canvas.alpha_composite(content, ((out - nw) // 2, (out - nh) // 2))
    if not sharpen:
        if feather > 0:
            r, g, b, alpha_ch = canvas.split()
            alpha_ch = alpha_ch.filter(ImageFilter.GaussianBlur(feather))
            canvas = Image.merge("RGBA", (r, g, b, alpha_ch))
        return canvas

    canvas = canvas.filter(ImageFilter.UnsharpMask(radius=1.4, percent=90, threshold=0))
    arr = np.asarray(canvas, dtype=float) / 255.0
    edge = arr[..., 3]
    arr[..., 3] = np.clip((edge - 0.5) * 1.5 + 0.5, 0.0, 1.0)
    return Image.fromarray((arr * 255.0 + 0.5).astype(np.uint8), "RGBA")


def recolor_icon(padded: Image.Image, variant: str, bg: str) -> Image.Image:
    a = np.asarray(padded.convert("RGBA"), dtype=float) / 255.0
    if variant == "white" and bg == "dark":  # keep as-is (bar the transparent-RGB clear)
        return Image.fromarray(
            clear_transparent_rgb((a * 255.0 + 0.5).astype(np.uint8)), "RGBA")
    alpha = a[..., 3]
    h, w = alpha.shape
    mode, col = paint(variant, bg)
    if mode == "grad":
        lut = col
        ys, xs = np.mgrid[0:h, 0:w].astype(float)
        t = np.mod(((xs / max(w - 1, 1)) * 0.62 + (ys / max(h - 1, 1)) * 0.38)
                   * 1.25 + CYCLE_PHASE[variant], 1.0)
        rgb = lut[np.clip((t * len(lut)).astype(int), 0, len(lut) - 1)]
    else:
        rgb = np.broadcast_to(col, (h, w, 3))
    out = np.clip(np.dstack([rgb, alpha]), 0.0, 1.0)
    return Image.fromarray(
        clear_transparent_rgb((out * 255.0 + 0.5).astype(np.uint8)), "RGBA")


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


def is_big_icon(name: str) -> bool:
    return name.startswith(("os_", "boot_"))


def build(variant: str) -> None:
    sources = sorted(ICONS_DIR.glob("*.png"))
    padded = {f.name: pad_icon(Image.open(f), OUT_BIG if is_big_icon(f.name) else OUT_SMALL,
                                sharpen=is_big_icon(f.name),
                                feather=0.0 if is_big_icon(f.name) else FEATHER_SMALL)
              for f in sources}
    for bg in ("dark", "light"):
        d = look_dir(variant, bg)
        (d / "icons").mkdir(parents=True, exist_ok=True)
        render_outline("big", variant, bg).save(d / "selection_big.png", optimize=True)
        render_outline("small", variant, bg).save(d / "selection_small.png", optimize=True)
        for name, pic in padded.items():
            recolor_icon(pic, variant, bg).save(d / "icons" / name, optimize=True)
    print(f"  {variant:16s} -> {COLORS_DIR}/{variant}/  (+ light/)  {len(sources)} icons x2")


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

    def as_refind(img: Image.Image, refind_px: int, draw_px: int) -> Image.Image:
        # rEFInd downscales the shipped icon to *_icon_size with a plain filter;
        # mimic that so the preview shows the real on-screen sharpness.
        return img.resize((refind_px, refind_px), Image.BILINEAR).resize((draw_px, draw_px), Image.LANCZOS)

    for row, (v, bg) in enumerate(combos):
        rgb = tuple(int(round(c * 255)) for c in hex_rgb(BACKGROUNDS[bg]))
        strip = Image.new("RGBA", (W, strip_h), rgb + (255,))
        sel_b = as_refind(Image.open(look_dir(v, bg) / "selection_big.png").convert("RGBA"), 200, big)
        sel_s = as_refind(Image.open(look_dir(v, bg) / "selection_small.png").convert("RGBA"), 50, small)

        x0 = (W - (len(os_names) * big + (len(os_names) - 1) * gap_big)) // 2
        y_os = 64
        for i, n in enumerate(os_names):
            x = x0 + i * (big + gap_big)
            if i == sel_os:
                strip.alpha_composite(sel_b, (x, y_os))
            strip.alpha_composite(as_refind(look_icon(v, bg, f"{n}.png"), 200, big), (x, y_os))

        tx0 = (W - (len(tool_names) * small + (len(tool_names) - 1) * gap_small)) // 2
        y_tool = y_os + big + 56
        for i, n in enumerate(tool_names):
            x = tx0 + i * (small + gap_small)
            if i == sel_tool:
                strip.alpha_composite(sel_s, (x, y_tool))
            strip.alpha_composite(as_refind(look_icon(v, bg, f"{n}.png"), 50, small), (x, y_tool))

        panel.paste(strip.convert("RGB"), (0, row * strip_h))

    dest = REPO / "preview-menu.png"
    panel.save(dest, optimize=True)
    print(f"  menu preview -> preview-menu.png ({panel.width}x{panel.height}; {', '.join(v for v, _ in combos)})")


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for v in ALL_VARIANTS:
            print(v)
        return 0

    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}

    global ICONS_DIR, COLORS_DIR
    out_dir_explicit = False
    for a in flags:
        if a.startswith("--icons-dir="):
            ICONS_DIR = Path(a.split("=", 1)[1]).expanduser().resolve()
        elif a.startswith("--out-dir="):
            COLORS_DIR = Path(a.split("=", 1)[1]).expanduser().resolve()
            out_dir_explicit = True
    if not ICONS_DIR.is_dir():
        print(f"icons dir not found: {ICONS_DIR}", file=sys.stderr)
        return 2

    variants = args or ALL_VARIANTS
    unknown = [v for v in variants if v not in ALL_VARIANTS]
    if unknown:
        print(f"unknown variant(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"available: {', '.join(ALL_VARIANTS)}", file=sys.stderr)
        return 2

    print(f"source icons: {ICONS_DIR}")
    print(f"output: {COLORS_DIR}")
    # Backgrounds are committed source (backgrounds/dark.png, light.png), not a
    # per-colour build product — only touch them on a full, in-repo rebuild
    # (no --out-dir), never when install.sh drives a narrow, throwaway build.
    if not out_dir_explicit:
        build_backgrounds()
    COLORS_DIR.mkdir(parents=True, exist_ok=True)
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
