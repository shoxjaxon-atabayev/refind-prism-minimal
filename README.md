# Prism Minimal

A dark, ultra-minimal [rEFInd](https://www.rodsbooks.com/refind/) boot theme —
pure-black background, silhouette icons, no panels, no labels. Pick a colour
and the **whole thing** turns that colour: every icon *and* the selection
outline. The selected entry is marked by a thin outline around it — a
**square** on the OS row, a **circle** on the tool row. No fill, no glow, no
sheen; the box interior stays empty.

(rEFInd draws the same icon PNG whether an entry is focused or not, so it can't
tint just the selected one — the whole set is recoloured instead.)

It ships in **10 colours** — hence *Prism*. Six flat ones and a plain white
default; three "premium" ones that are **iridescent** — the icons and the
outline cycle hue like holographic foil (rEFInd has no shader to do that live,
so it's pre-rendered into the PNG).

![all ten selection styles](preview.png)

| tier | colours |
|---|---|
| default | `white` |
| flat | `green` · `red` · `violet` · `pink` · `gray` · `blue` |
| premium · iridescent | `obsidian-purple` · `titanium-silver` · `champagne-gold` |

![white / blue / obsidian-purple in a mock menu](preview-menu.png)

Switching colour swaps the two selection PNGs and the `icons/` set. The black
background, `theme.conf` and the layout are identical across every colour.
`white` keeps the original light icons.

## Install

```
git clone https://github.com/shoxjaxon-atabayev/refind-prism-minimal.git
cd refind-prism-minimal
./install.sh                       # installs the white variant
./install.sh --color obsidian-purple
```

`install.sh` re-execs itself with `sudo` when it needs to (the ESP is usually
root-only). It:

1. finds your rEFInd install — checks `/boot`, `/boot/efi`, `/boot/EFI`,
   `/efi` and every mounted FAT volume for a `refind_*.efi` next to a
   `refind.conf`;
2. copies the theme to `<refind-dir>/themes/prism-minimal/` (the path
   `theme.conf` expects), with the colour you picked — its two selection PNGs
   and its recoloured `icons/` set;
3. adds one managed line to `refind.conf`:
   `include themes/prism-minimal/theme.conf` — backing the file up first.

It never touches EFI boot entries, NVRAM, Secure Boot, or any other
bootloader. It's safe to re-run: it won't duplicate the include line, and if
the files are already current it skips the copy entirely. Reboot to see it.

### Flags

| flag | effect |
|---|---|
| `--color <name>` | which colour to install / switch to (default `white`) |
| `--list-colors` | print the available colours and exit |
| `--dry-run` | show the plan, change nothing (no `sudo`) |
| `--yes` | skip the confirmation prompt |
| `--refind-dir <path>` | skip detection; use this dir (the one with `refind.conf`) |
| `--deploy-refind` | run the system's `refind-install` first if rEFInd isn't on the ESP yet |
| `--uninstall` | remove the theme and the managed `refind.conf` block |

### Change colour later

```
sudo ./install.sh --color champagne-gold
```

Swaps the two selection PNGs and the `icons/` set in place; `refind.conf` is
left untouched.

### If rEFInd isn't installed yet

`install.sh` stops with instructions — set up rEFInd itself first
(`sudo refind-install`), then re-run. Or pass `--deploy-refind` to let the
script call `refind-install` for you once.

## Manual install

1. Copy this directory to `<your ESP>/EFI/refind/themes/prism-minimal/`.
2. Pick a colour: from `colors/<name>/`, copy `selection_big.png`,
   `selection_small.png` and the `icons/` folder over the ones at the top of
   the theme dir. (`white` is the default already in place; it has no
   `colors/white/icons/` and just uses the top-level `icons/`.)
3. Add to `refind.conf`:

   ```
   include themes/prism-minimal/theme.conf
   ```

If any themed asset is missing, rEFInd falls back to its built-in rendering —
you always get a usable menu.

## Layout

```
theme.conf            rEFInd directives (rEFInd-minimal's, only the theme-dir name differs)
background.png         the black backdrop (banner_scale fillscreen)
selection_big.png      active OS-row outline   — a copy of colors/white/…
selection_small.png    active tool-row outline — a copy of colors/white/…
icons/                 the default (white) OS / tool icon set
colors/<name>/         per colour: selection_big/small.png + a recoloured icons/
                       ("white" has only the two PNGs — it reuses icons/)
install.sh             the installer (also --uninstall)
tools/generate.py      regenerates every colors/ asset from code
```

## Regenerating the colour assets

```
python3 tools/generate.py              # rebuild all colours (outlines + icon sets)
python3 tools/generate.py blue green   # just some
python3 tools/generate.py --preview    # also rebuild preview*.png
```

Needs `Pillow` and `numpy` (dev-only). Colours, geometry and the iridescence
parameters all live at the top of that file; each colour's `icons/` is the
top-level `icons/` recoloured. After regenerating, re-sync the default:

```
cp colors/white/selection_big.png selection_big.png
cp colors/white/selection_small.png selection_small.png
```

## Credits

Icon set and base layout from
[rEFInd-minimal](https://github.com/EvanPurkhiser/rEFInd-minimal) by Evan
Purkhiser. Colour + iridescent selection system and installer added here.
