#!/usr/bin/env python3
"""
Regenerate the selection-highlight assets for every colour variant of the
Prism Minimal rEFInd theme.

rEFInd draws ``selection_big`` / ``selection_small`` *behind* the focused icon.
The selection here is **only a coloured outline** — nothing inside it, no fill,
no glow, no sheen. The white icon shows through unchanged.

  * ``selection_big``   (OS row)   — a rounded **square** outline
  * ``selection_small`` (tool row) — a **circular** outline

The three premium variants use an *iridescent* stroke: the colour cycles hue
around the outline (a holographic-foil look) instead of being one flat colour.
rEFInd has no shader to do that at runtime, so it's baked into the PNG.

Output (this script only ever writes here):

    colors/<variant>/selection_big.png     256x256  RGBA
    colors/<variant>/selection_small.png    64x64   RGBA

``install.sh --color <variant>`` copies the chosen pair over
``selection_big.png`` / ``selection_small.png`` at the theme root — the exact
paths ``theme.conf`` references, which never change. ``white`` is the default.

Usage:
    python3 tools/generate.py                 # regenerate every variant
    python3 tools/generate.py green blue      # just these
    python3 tools/generate.py --preview       # also write preview.png + preview-menu.png

Dependencies: Pillow, numpy   (dev-only — never shipped to the ESP).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
COLORS_DIR = REPO / "colors"

# ---------------------------------------------------------------- palette --

# Simple variants: one flat border colour. "white" is the shipped default.
SIMPLE: dict[str, str] = {
    "white":  "#FFFFFF",
    "green":  "#40DC77",
    "red":    "#FF4D4D",
    "violet": "#8B5CF6",
    "pink":   "#FF74C4",
    "gray":   "#AAB2C0",
    "blue":   "#4D9DFF",
}

# Premium variants: an ordered loop of hue stops the border stroke cycles
# through (the list wraps — last stop back to first). Weighted toward the
# name hue so the frame still reads as purple / silver / gold at a glance,
# while the off-hues give the "tovlanadigan" oil-slick shimmer. Every stop is
# kept bright enough to stay visible on pure black — there's no glow or fill
# behind the stroke to lift a dark segment now.
PREMIUM: dict[str, list[str]] = {
    "obsidian-purple": ["#7A28D8", "#A838E8", "#D060E8", "#9A6CF6",
                        "#4E78F0", "#30C6D2", "#6E2CD0"],
    "titanium-silver": ["#9AA4B4", "#C4CEDC", "#EAF0F8", "#FCFEFF",
                        "#AEDCF2", "#DCC8F2", "#EEDCAC"],
    "champagne-gold":  ["#D0A24E", "#E6BE72", "#F4D68E", "#FFF2D2",
                        "#FFDCC6", "#F4B4C8", "#CCE8CC"],
}

# Per-variant phase offset so the shimmer sits differently on each and they
# don't look like recolours of one image.
PREMIUM_PHASE: dict[str, float] = {
    "obsidian-purple": 0.00,
    "titanium-silver": 0.37,
    "champagne-gold":  0.68,
}

ALL_VARIANTS = list(SIMPLE) + list(PREMIUM)

# --------------------------------------------------------------- geometry --

# The outline is drawn on a canvas the size of the icon cell, inset a few px so
# it clears the edge. `border` is a touch wider than the visible stroke because
# rEFInd scales the asset down to icon size (192 / 48 here), which thins it.
#   big   -> rounded square outline for the OS row
#   small -> circle outline for the tool row
SPECS = {
    "big":   dict(px=256, shape="square", margin=8.0, radius=6.0, border=5.5),
    "small": dict(px=64,  shape="circle", margin=2.0, radius=0.0, border=2.6),
}
SS = 4  # supersample factor

BORDER_ALPHA = 1.0
# Premium: hue cycles *around the outline* (angular). Must be a whole number so
# the loop closes seamlessly across arctan2's branch cut.
RING_CYCLES_BIG = 2.0
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
    """Signed distance (<0 inside) to a circle or an axis-aligned rounded square
    centred at the origin."""
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


# ---------------------------------------------------------------- render --

def render(kind: str, variant: str) -> Image.Image:
    spec = SPECS[kind]
    size = spec["px"]
    premium = variant in PREMIUM

    hi = size * SS
    ys, xs = np.mgrid[0:hi, 0:hi].astype(float)
    c = (hi - 1) / 2.0
    px, py = xs - c, ys - c

    outer = (size / 2.0 - spec["margin"]) * SS
    bw = spec["border"] * SS
    r = spec["radius"] * SS
    aa = 1.1 * SS  # ~0.28 px feather in final pixels — crisp, not aliased

    d_out = shape_sdf(spec["shape"], px, py, outer, r)
    d_in = shape_sdf(spec["shape"], px, py, outer - bw, max(r - bw, 0.4 * SS))
    ring = np.clip(smoothstep(aa, -aa, d_out) - smoothstep(aa, -aa, d_in), 0.0, 1.0)

    if premium:
        lut = gradient_lut(PREMIUM[variant])
        cycles = RING_CYCLES_BIG if kind == "big" else RING_CYCLES_SMALL
        theta = np.arctan2(py, px) / (2.0 * np.pi) + 0.5
        # a square perimeter bunches the hue at its corners under a pure angular
        # map; a touch of diagonal evens it out. A circle doesn't need it.
        if spec["shape"] == "square":
            theta = theta + 0.18 * ((xs / hi) * 0.58 + (ys / hi) * 0.42)
        t = np.mod((theta + PREMIUM_PHASE[variant]) * cycles, 1.0)
        stroke_rgb = lut[np.clip((t * len(lut)).astype(int), 0, len(lut) - 1)]
        stroke_rgb = downscale(stroke_rgb, size)
    else:
        stroke_rgb = np.broadcast_to(hex_rgb(SIMPLE[variant]), (size, size, 3)).copy()

    alpha = downscale(ring, size) * BORDER_ALPHA
    rgba = np.clip(np.dstack([stroke_rgb, alpha]), 0.0, 1.0)
    return Image.fromarray((rgba * 255.0 + 0.5).astype(np.uint8), "RGBA")


# ----------------------------------------------------------------- driver --

def build(variant: str) -> None:
    out = COLORS_DIR / variant
    out.mkdir(parents=True, exist_ok=True)
    render("big", variant).save(out / "selection_big.png", optimize=True)
    render("small", variant).save(out / "selection_small.png", optimize=True)
    print(f"  {variant:16s} -> {out.relative_to(REPO)}/")


def make_preview(variants: list[str]) -> None:
    """Contact sheet: per variant, the square selection_big behind the white
    arch icon (OS row) and, inset bottom-right, the circular selection_small
    behind a tool icon — icons drawn on top, rEFInd's own order."""
    os_p = REPO / "icons" / "os_arch.png"
    tool_p = REPO / "icons" / "func_shutdown.png"
    if not os_p.exists():
        print("  (skipping preview: icons/os_arch.png not found)")
        return
    os_icon = Image.open(os_p).convert("RGBA").resize((256, 256), Image.LANCZOS)
    chip = 92
    tool_icon = (Image.open(tool_p).convert("RGBA").resize((chip, chip), Image.LANCZOS)
                 if tool_p.exists() else None)

    cell, pad, cols = 256, 24, 5
    rows = (len(variants) + cols - 1) // cols
    W = cols * cell + (cols + 1) * pad
    H = rows * cell + (rows + 1) * pad
    sheet = Image.new("RGBA", (W, H), (11, 11, 13, 255))

    for i, v in enumerate(variants):
        cx = pad + (i % cols) * (cell + pad)
        cy = pad + (i // cols) * (cell + pad)
        tile = Image.new("RGBA", (cell, cell), (11, 11, 13, 255))
        tile.alpha_composite(Image.open(COLORS_DIR / v / "selection_big.png").convert("RGBA"))
        tile.alpha_composite(os_icon)
        if tool_icon is not None:
            sm = Image.open(COLORS_DIR / v / "selection_small.png").convert("RGBA").resize((chip, chip), Image.LANCZOS)
            ox, oy = cell - chip - 6, cell - chip - 6
            tile.alpha_composite(sm, (ox, oy))
            tile.alpha_composite(tool_icon, (ox, oy))
        sheet.alpha_composite(tile, (cx, cy))

    dest = REPO / "preview.png"
    sheet.convert("RGB").save(dest, optimize=True)
    print(f"  preview -> {dest.relative_to(REPO)} ({W}x{H}, order: {', '.join(variants)})")


def make_menu_preview(variants: list[str]) -> None:
    """A rough approximation of the actual rEFInd screen for a few variants:
    black fill, a centred row of big OS icons (2nd selected), a row of small
    tool icons below (1st selected) — icons drawn *on top* of the selection
    asset, exactly rEFInd's own draw order. Labels are off (hideui)."""
    os_names = ["os_omarchy", "os_arch", "os_linux", "os_win11", "os_mac"]
    tool_names = ["func_shutdown", "func_firmware", "func_about"]
    os_icons = [p for n in os_names if (p := REPO / "icons" / f"{n}.png").exists()]
    tool_icons = [p for n in tool_names if (p := REPO / "icons" / f"{n}.png").exists()]
    if len(os_icons) < 3:
        print("  (skipping menu preview: not enough icons)")
        return

    # icon sizes here track theme.conf's 192 / 48 at ~0.44 px-per-rEFInd-px
    W, strip_h = 1280, 300
    big, small = 84, 40
    gap_big, gap_small = 96, 72
    sel_os, sel_tool = 1, 0

    panel = Image.new("RGB", (W, strip_h * len(variants)), (0, 0, 0))

    for row, v in enumerate(variants):
        strip = Image.new("RGBA", (W, strip_h), (0, 0, 0, 255))
        sel_b = Image.open(COLORS_DIR / v / "selection_big.png").convert("RGBA").resize((big, big), Image.LANCZOS)
        sel_s = Image.open(COLORS_DIR / v / "selection_small.png").convert("RGBA").resize((small, small), Image.LANCZOS)

        x0 = (W - (len(os_icons) * big + (len(os_icons) - 1) * gap_big)) // 2
        y_os = 70
        for i, ip in enumerate(os_icons):
            x = x0 + i * (big + gap_big)
            if i == sel_os:
                strip.alpha_composite(sel_b, (x, y_os))
            strip.alpha_composite(Image.open(ip).convert("RGBA").resize((big, big), Image.LANCZOS), (x, y_os))

        tx0 = (W - (len(tool_icons) * small + (len(tool_icons) - 1) * gap_small)) // 2
        y_tool = y_os + big + 60
        for i, ip in enumerate(tool_icons):
            x = tx0 + i * (small + gap_small)
            if i == sel_tool:
                strip.alpha_composite(sel_s, (x, y_tool))
            strip.alpha_composite(Image.open(ip).convert("RGBA").resize((small, small), Image.LANCZOS), (x, y_tool))

        panel.paste(strip.convert("RGB"), (0, row * strip_h))

    dest = REPO / "preview-menu.png"
    panel.save(dest, optimize=True)
    print(f"  menu preview -> {dest.relative_to(REPO)} ({panel.width}x{panel.height}, rows: {', '.join(variants)})")


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}

    variants = args or ALL_VARIANTS
    unknown = [v for v in variants if v not in ALL_VARIANTS]
    if unknown:
        print(f"unknown variant(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"available: {', '.join(ALL_VARIANTS)}", file=sys.stderr)
        return 2

    print(f"generating {len(variants)} variant(s) into {COLORS_DIR.relative_to(REPO)}/")
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
