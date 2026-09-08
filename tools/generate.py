#!/usr/bin/env python3
"""
Regenerate the selection-highlight assets for every colour variant of the
Prism Minimal rEFInd theme.

rEFInd draws ``selection_big`` / ``selection_small`` *behind* the focused icon
and never recolours the icon PNG itself. Every icon in this theme is a
pure-white silhouette on black, so "the selected icon turns green / purple / …"
has to happen entirely here:

  * a translucent colour-tinted glass square, so the white icon reads as
    sitting on a coloured tile (this is the "selected icon colour");
  * a crisp coloured border (square, as requested);
  * a soft outer glow so the tile lifts off the black background;
  * a hairline top highlight for a glassy lip.

The three premium variants additionally bake in an *iridescent* sheen — a
hue-cycling border gradient plus a specular streak and corner glint — because
rEFInd has no shader to do that at runtime; it must be pre-rendered.

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

# Simple variants: one flat colour for border, fill tint and glow.
# "white" is the default the theme ships with.
SIMPLE: dict[str, str] = {
    "white":  "#FFFFFF",
    "green":  "#40DC77",
    "red":    "#FF4D4D",
    "violet": "#8B5CF6",
    "pink":   "#FF74C4",
    "gray":   "#AAB2C0",
    "blue":   "#4D9DFF",
}

# Premium variants: an ordered loop of hue stops the border gradient cycles
# through (the list wraps — last stop back to first). Weighted toward the
# name hue so the square still reads as purple / silver / gold at a glance,
# while the off-hues give the "tovlanadigan" oil-slick shimmer.
PREMIUM: dict[str, list[str]] = {
    "obsidian-purple": ["#1C0733", "#4A159C", "#8226D6", "#C24EEC",
                        "#7A54F4", "#3E63E8", "#22C1D0"],
    "titanium-silver": ["#4A5058", "#9AA4B2", "#E4ECF6", "#FBFDFF",
                        "#8FD6F0", "#C9A6F0", "#F0D9A0"],
    "champagne-gold":  ["#7A4E1C", "#C68C3C", "#F0CC7E", "#FFF6DC",
                        "#FFD9C2", "#F2B0C6", "#B8E6C4"],
}

# Base tint for the glass fill on premium variants (kept very low-alpha so the
# white icon stays crisp — the user asked for a tasteful tint, not a wash).
PREMIUM_ANCHOR: dict[str, str] = {
    "obsidian-purple": "#8A46D8",
    "titanium-silver": "#C6D0DE",
    "champagne-gold":  "#E7C98A",
}

# Per-variant phase offset for the gradient, so the shimmer sits differently
# on each and they do not look like recolours of one image.
PREMIUM_PHASE: dict[str, float] = {
    "obsidian-purple": 0.00,
    "titanium-silver": 0.37,
    "champagne-gold":  0.68,
}

ALL_VARIANTS = list(SIMPLE) + list(PREMIUM)

# --------------------------------------------------------------- geometry --

# The icon content in this theme sits ~50 px inside a 256 px cell (and ~14 px
# inside a 64 px cell), so a square inset ~18 / ~4 px leaves the border clearly
# outside the icon while the fill still covers it — and leaves room for the
# outer glow to fade out before the canvas edge instead of being clipped.
SPECS = {
    "big":   dict(px=256, margin=18.0, radius=6.0,  border=3.0, glow=11.0),
    "small": dict(px=64,  margin=4.0,  radius=2.5,  border=1.6, glow=4.0),
}
SS = 4  # supersample factor for the crisp layers

FILL_ALPHA_SIMPLE = 0.28
FILL_ALPHA_PREMIUM = 0.17
BORDER_ALPHA = 0.95
GLOW_ALPHA = 0.34
TOP_HI_ALPHA = 0.11
STREAK_ALPHA = 0.22
GLINT_ALPHA = 0.12
# Premium border: hue cycles *around the frame* (angular) for a holographic
# frame. Must be a whole number so the loop closes seamlessly across arctan2's
# branch cut; the fill uses a gentler diagonal sheen where a fraction is fine.
RING_CYCLES_BIG = 2.0
RING_CYCLES_SMALL = 1.0
FILL_CYCLES_BIG = 1.05
FILL_CYCLES_SMALL = 0.9

WHITE = np.array([1.0, 1.0, 1.0])


# ------------------------------------------------------------------ maths --

def hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float) / 255.0


def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def rounded_rect_sdf(px: np.ndarray, py: np.ndarray, half: float, r: float) -> np.ndarray:
    """Signed distance to an axis-aligned rounded square centred at 0 (<0 inside)."""
    qx = np.abs(px) - (half - r)
    qy = np.abs(py) - (half - r)
    outside = np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0))
    inside = np.minimum(np.maximum(qx, qy), 0.0)
    return outside + inside - r


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


def gaussian_blur(mask: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian, edge-padded, full float precision (no scipy here)."""
    if sigma <= 0:
        return mask
    radius = max(1, int(round(sigma * 3)))
    x = np.arange(-radius, radius + 1, dtype=float)
    k = np.exp(-(x ** 2) / (2.0 * sigma ** 2))
    k /= k.sum()
    h, w = mask.shape
    m = np.pad(mask, radius, mode="edge")
    tmp = np.zeros_like(mask)
    for i, wt in enumerate(k):
        tmp += wt * m[radius:radius + h, i:i + w]
    m2 = np.pad(tmp, radius, mode="edge")
    out = np.zeros_like(mask)
    for i, wt in enumerate(k):
        out += wt * m2[i:i + h, radius:radius + w]
    return out


def downscale(arr: np.ndarray, size: int) -> np.ndarray:
    """LANCZOS downscale of a float array in [0,1]; keeps last axis for RGB."""
    if arr.ndim == 2:
        img = Image.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8), "L")
        img = img.resize((size, size), Image.LANCZOS)
        return np.asarray(img, dtype=float) / 255.0
    img = Image.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8), "RGB")
    img = img.resize((size, size), Image.LANCZOS)
    return np.asarray(img, dtype=float) / 255.0


# ---------------------------------------------------------------- compose --

class Compositor:
    """Straight-alpha 'source over', accumulated in premultiplied space."""

    def __init__(self, size: int):
        self.pm = np.zeros((size, size, 3))
        self.a = np.zeros((size, size))

    def over(self, rgb: np.ndarray, alpha: np.ndarray) -> None:
        alpha = np.clip(alpha, 0.0, 1.0)
        if rgb.ndim == 1:
            rgb = np.broadcast_to(rgb, self.pm.shape)
        src_pm = rgb * alpha[..., None]
        self.pm = src_pm + self.pm * (1.0 - alpha)[..., None]
        self.a = alpha + self.a * (1.0 - alpha)

    def rgba(self) -> np.ndarray:
        a = self.a[..., None]
        straight = np.divide(self.pm, a, out=np.zeros_like(self.pm), where=a > 1e-6)
        return np.clip(np.dstack([straight, self.a]), 0.0, 1.0)


def render(kind: str, variant: str) -> Image.Image:
    spec = SPECS[kind]
    size = spec["px"]
    premium = variant in PREMIUM

    # --- crisp layers at supersample resolution -------------------------------
    hi = size * SS
    ys, xs = np.mgrid[0:hi, 0:hi].astype(float)
    c = (hi - 1) / 2.0
    px, py = xs - c, ys - c

    half = (size / 2.0 - spec["margin"]) * SS
    r = spec["radius"] * SS
    bw = spec["border"] * SS
    aa = 1.1 * SS  # ~0.28 px feather in final pixels — crisp, not aliased

    d_out = rounded_rect_sdf(px, py, half, r)
    d_in = rounded_rect_sdf(px, py, half - bw, max(r - bw, 0.6 * SS))

    shape = smoothstep(aa, -aa, d_out)          # 1 inside the whole square
    inner = smoothstep(aa, -aa, d_in)           # 1 inside the fill area
    ring = np.clip(shape - inner, 0.0, 1.0)     # the border band

    # glass lip: a bright hairline just inside the top edge
    top_y = -(half - bw - 1.2 * SS)
    top_hi = np.exp(-((py - top_y) / (1.6 * SS)) ** 2) * shape

    if premium:
        lut = gradient_lut(PREMIUM[variant])
        phase = PREMIUM_PHASE[variant]
        diag = (xs / hi) * 0.58 + (ys / hi) * 0.42

        # ring: hue wraps *around* the frame (angular) + a touch of diagonal
        ring_cycles = RING_CYCLES_BIG if kind == "big" else RING_CYCLES_SMALL
        theta = np.arctan2(py, px) / (2.0 * np.pi) + 0.5
        t_ring = np.mod((theta + 0.18 * diag + phase) * ring_cycles, 1.0)
        grad_ring = lut[np.clip((t_ring * len(lut)).astype(int), 0, len(lut) - 1)]

        # fill: gentle diagonal sheen
        fill_cycles = FILL_CYCLES_BIG if kind == "big" else FILL_CYCLES_SMALL
        t_fill = np.mod((diag + phase) * fill_cycles, 1.0)
        grad_fill = lut[np.clip((t_fill * len(lut)).astype(int), 0, len(lut) - 1)]

        # specular streak across the glass + soft glint off the top-left corner
        ang = np.radians(118.0)
        proj = (px * np.cos(ang) + py * np.sin(ang)) / half
        streak = np.exp(-((proj - 0.12) / 0.20) ** 2) * shape
        streak += 0.35 * np.exp(-((proj + 0.38) / 0.10) ** 2) * shape
        gx, gy = px + half * 0.72, py + half * 0.72
        glint = np.exp(-((np.hypot(gx, gy) / half) / 0.5) ** 2) * shape
    else:
        grad_ring = grad_fill = None
        streak = glint = np.zeros_like(shape)

    # downscale every crisp layer to native resolution
    ring_n = downscale(ring, size)
    inner_n = downscale(inner, size)
    top_hi_n = downscale(top_hi, size)
    streak_n = downscale(streak, size)
    glint_n = downscale(glint, size)
    grad_ring_n = downscale(grad_ring, size) if grad_ring is not None else None
    grad_fill_n = downscale(grad_fill, size) if grad_fill is not None else None

    # --- glow: computed directly at native res (large sigma, no crispness needed)
    gy2, gx2 = np.mgrid[0:size, 0:size].astype(float)
    cc = (size - 1) / 2.0
    d_native = rounded_rect_sdf(gx2 - cc, gy2 - cc, half / SS, r / SS)
    solid = smoothstep(0.8, -0.8, d_native)
    glow = gaussian_blur(solid, spec["glow"])
    glow = np.clip(glow - solid, 0.0, 1.0)
    if glow.max() > 1e-6:
        glow /= glow.max()
    # feather the last few px so the glow never leaves a hard line at the edge
    fade = size * 0.06
    edge = (smoothstep(0.0, fade, gx2) * smoothstep(0.0, fade, size - 1 - gx2)
            * smoothstep(0.0, fade, gy2) * smoothstep(0.0, fade, size - 1 - gy2))
    glow *= edge

    # --- colours -------------------------------------------------------------
    if premium:
        anchor = hex_rgb(PREMIUM_ANCHOR[variant])
        border_rgb = grad_ring_n
        fill_rgb = 0.68 * grad_fill_n + 0.32 * anchor
        # glow picks up the gradient too (a faint two-tone halo, not a flat wash)
        glow_rgb = 0.45 * grad_fill_n + 0.55 * anchor
        fill_alpha = FILL_ALPHA_PREMIUM
    else:
        base = hex_rgb(SIMPLE[variant])
        border_rgb = np.broadcast_to(base, (size, size, 3))
        fill_rgb = np.broadcast_to(base, (size, size, 3))
        glow_rgb = np.broadcast_to(base, (size, size, 3))
        fill_alpha = FILL_ALPHA_SIMPLE

    # --- composite back-to-front -------------------------------------------
    comp = Compositor(size)
    comp.over(glow_rgb, glow * GLOW_ALPHA)
    comp.over(fill_rgb, inner_n * fill_alpha)
    if premium:
        comp.over(WHITE, streak_n * STREAK_ALPHA)
        comp.over(WHITE, glint_n * GLINT_ALPHA)
    comp.over(WHITE, top_hi_n * TOP_HI_ALPHA)
    comp.over(border_rgb, ring_n * BORDER_ALPHA)

    rgba = comp.rgba()
    return Image.fromarray((rgba * 255.0 + 0.5).astype(np.uint8), "RGBA")


# ----------------------------------------------------------------- driver --

def build(variant: str) -> None:
    out = COLORS_DIR / variant
    out.mkdir(parents=True, exist_ok=True)
    render("big", variant).save(out / "selection_big.png", optimize=True)
    render("small", variant).save(out / "selection_small.png", optimize=True)
    print(f"  {variant:16s} -> {out.relative_to(REPO)}/")


def make_preview(variants: list[str]) -> None:
    """Contact sheet: each variant's selection_big behind the white arch icon,
    exactly the way rEFInd stacks them (selection first, icon on top)."""
    icon_path = REPO / "icons" / "os_arch.png"
    if not icon_path.exists():
        print("  (skipping preview: icons/os_arch.png not found)")
        return
    icon = Image.open(icon_path).convert("RGBA").resize((256, 256), Image.LANCZOS)

    cell, pad, cols = 256, 24, 5
    rows = (len(variants) + cols - 1) // cols
    W = cols * cell + (cols + 1) * pad
    H = rows * cell + (rows + 1) * pad
    sheet = Image.new("RGBA", (W, H), (11, 11, 13, 255))

    for i, v in enumerate(variants):
        cx = pad + (i % cols) * (cell + pad)
        cy = pad + (i // cols) * (cell + pad)
        tile = Image.new("RGBA", (cell, cell), (11, 11, 13, 255))
        sel = Image.open(COLORS_DIR / v / "selection_big.png").convert("RGBA")
        tile.alpha_composite(sel)
        tile.alpha_composite(icon)
        sheet.alpha_composite(tile, (cx, cy))

    dest = REPO / "preview.png"
    sheet.convert("RGB").save(dest, optimize=True)
    print(f"  preview -> {dest.relative_to(REPO)} ({W}x{H}, order: {', '.join(variants)})")


def make_menu_preview(variants: list[str]) -> None:
    """A rough approximation of the actual rEFInd screen for a few variants:
    black fill, a centred row of big OS icons (3rd one selected), a row of
    small tool icons below (1st selected) — icons drawn *on top* of the
    selection asset, exactly rEFInd's own draw order. Labels are off (hideui)."""
    os_names = ["os_omarchy", "os_arch", "os_linux", "os_win11", "os_mac"]
    tool_names = ["func_shutdown", "func_firmware", "func_about"]
    os_icons = [p for n in os_names if (p := REPO / "icons" / f"{n}.png").exists()]
    tool_icons = [p for n in tool_names if (p := REPO / "icons" / f"{n}.png").exists()]
    if len(os_icons) < 3:
        print("  (skipping menu preview: not enough icons)")
        return

    W = 1280
    strip_h = 300
    big, small = 96, 44
    gap_big, gap_small = 88, 64
    sel_os, sel_tool = 1, 0  # which index is "focused" in each row

    panel = Image.new("RGB", (W, strip_h * len(variants)), (0, 0, 0))

    for row, v in enumerate(variants):
        strip = Image.new("RGBA", (W, strip_h), (0, 0, 0, 255))
        sel_b = Image.open(COLORS_DIR / v / "selection_big.png").convert("RGBA").resize((big, big), Image.LANCZOS)
        sel_s = Image.open(COLORS_DIR / v / "selection_small.png").convert("RGBA").resize((small, small), Image.LANCZOS)

        row_w = len(os_icons) * big + (len(os_icons) - 1) * gap_big
        x0 = (W - row_w) // 2
        y_os = 70
        for i, ip in enumerate(os_icons):
            x = x0 + i * (big + gap_big)
            if i == sel_os:
                strip.alpha_composite(sel_b, (x, y_os))
            ic = Image.open(ip).convert("RGBA").resize((big, big), Image.LANCZOS)
            strip.alpha_composite(ic, (x, y_os))

        trow_w = len(tool_icons) * small + (len(tool_icons) - 1) * gap_small
        tx0 = (W - trow_w) // 2
        y_tool = y_os + big + 60
        for i, ip in enumerate(tool_icons):
            x = tx0 + i * (small + gap_small)
            if i == sel_tool:
                strip.alpha_composite(sel_s, (x, y_tool))
            ic = Image.open(ip).convert("RGBA").resize((small, small), Image.LANCZOS)
            strip.alpha_composite(ic, (x, y_tool))

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
        make_menu_preview([v for v in ("white", "blue", "obsidian-purple") if v in shown]
                          or shown[:3])

    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
