# Prism Minimal

An ultra-minimal [rEFInd](https://www.rodsbooks.com/refind/) boot theme — one
solid background, silhouette icons, no panels, no labels. Pick a **colour** and
the **whole thing** turns that colour: every icon *and* the selection outline.
The selected entry is marked by a thin outline around it — a **square** on the
OS row, a **circle** on the tool row. No fill, no glow, no sheen.

(rEFInd draws the same icon PNG whether an entry is focused or not, so it can't
tint just the selected one — the whole set is recoloured instead.)

Two axes:

* **colour** — `white` (default) + `green red violet pink gray blue` +
  premium iridescent `obsidian-purple` / `titanium-silver` / `champagne-gold`
  (the icons and outline cycle hue like holographic foil, pre-rendered since
  rEFInd has no shader)
* **background** — `dark` (black, default) or `light` (near-white; the icons
  and outline go dark for contrast)

![every colour on both backgrounds](preview.png)

![white / blue / obsidian-purple in a mock menu, dark then light](preview-menu.png)

`theme.conf` and the layout are identical for every combination — switching
only swaps `background.png`, the two `selection_*.png` and the `icons/` set.

## Install

```
git clone https://github.com/shoxjaxon-atabayev/refind-prism-minimal.git
cd refind-prism-minimal
./install.sh                                    # white on a dark background
./install.sh --color obsidian-purple
./install.sh --color blue --background light
```

`install.sh` re-execs itself with `sudo` when it needs to (the ESP is usually
root-only). It:

1. finds your rEFInd install — checks `/boot`, `/boot/efi`, `/boot/EFI`,
   `/efi` and every mounted FAT volume for a `refind_*.efi` next to a
   `refind.conf`;
2. copies the theme to `<refind-dir>/themes/prism-minimal/` (the path
   `theme.conf` expects) — the `background.png`, `selection_*.png` and
   `icons/` for the colour + background you picked;
3. adds one managed line to `refind.conf`:
   `include themes/prism-minimal/theme.conf` — backing the file up first.

It never touches EFI boot entries, NVRAM, Secure Boot, or any other
bootloader. It's safe to re-run: it won't duplicate the include line, and if
the files are already current it skips the copy entirely. Reboot to see it.

### Flags

| flag | effect |
|---|---|
| `--color <name>` | colour to install / switch to (default `white`) |
| `--background <dark\|light>` | background to use (default `dark`); `--bg` for short |
| `--list` | print the available colours and backgrounds, exit |
| `--dry-run` | show the plan, change nothing (no `sudo`) |
| `--yes` | skip the confirmation prompt |
| `--refind-dir <path>` | skip detection; use this dir (the one with `refind.conf`) |
| `--deploy-refind` | run the system's `refind-install` first if rEFInd isn't on the ESP yet |
| `--uninstall` | remove the theme and the managed `refind.conf` block |

### Restyle later

```
sudo ./install.sh --color champagne-gold --background light
```

Swaps `background.png`, the two `selection_*.png` and the `icons/` set in
place; `refind.conf` is left untouched.

### If rEFInd isn't installed yet

`install.sh` stops with instructions — set up rEFInd itself first
(`sudo refind-install`), then re-run. Or pass `--deploy-refind` to let the
script call `refind-install` for you once.

## Manual install

1. Copy this directory to `<your ESP>/EFI/refind/themes/prism-minimal/`.
2. Pick a look. For `<colour>` on the **dark** background copy the three from
   `colors/<colour>/` — `selection_big.png`, `selection_small.png`, `icons/` —
   over the ones at the top of the theme dir; for the **light** background use
   `colors/<colour>/light/` instead. Then copy `backgrounds/<dark|light>.png`
   to `background.png`. (`white` + `dark` is already in place.)
3. Add to `refind.conf`:

   ```
   include themes/prism-minimal/theme.conf
   ```

If any themed asset is missing, rEFInd falls back to its built-in rendering —
you always get a usable menu.

## Layout

```
theme.conf            rEFInd directives (rEFInd-minimal's, only the theme-dir name differs)
background.png         active backdrop         — a copy of backgrounds/dark.png
selection_big.png      active OS-row outline   — a copy of colors/white/…
selection_small.png    active tool-row outline — a copy of colors/white/…
backgrounds/           dark.png (black) · light.png (near-white)
colors/<name>/         selection_big/small.png + icons/  (dark background)
colors/<name>/light/   the same, darkened for the light background
icons/                 the raw source icon set (input to generate.py only)
install.sh             the installer (also --uninstall)
tools/generate.py      regenerates backgrounds/ and colors/ from code
```

## Regenerating the assets

```
python3 tools/generate.py              # rebuild every colour x background
python3 tools/generate.py blue green   # just some colours
python3 tools/generate.py --preview    # also rebuild preview*.png
```

Needs `Pillow` and `numpy` (dev-only). Colours, backgrounds, icon padding and
the iridescence parameters all live at the top of that file. Each colour's
`icons/` is the top-level `icons/` re-padded and recoloured. After
regenerating, re-sync the repo's default copies:

```
cp backgrounds/dark.png background.png
cp colors/white/selection_big.png selection_big.png
cp colors/white/selection_small.png selection_small.png
```

## Credits

Icon set and base layout from
[rEFInd-minimal](https://github.com/EvanPurkhiser/rEFInd-minimal) by Evan
Purkhiser. Colour + iridescent selection system and installer added here.
