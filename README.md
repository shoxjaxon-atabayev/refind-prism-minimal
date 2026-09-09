# Prism Minimal

A dark, ultra-minimal [rEFInd](https://www.rodsbooks.com/refind/) boot theme —
pure-black background, white silhouette OS icons, no panels, no labels. The
**selected** entry gets a coloured cell: a translucent fill plus a thin
outline — a **square** on the OS row, a **circle** on the tool row. rEFInd
draws that only behind the focused entry, so the selected OS/tool reads as
"that colour" while every other icon stays plain white; no icon PNG is
touched. No glow, no sheen — just fill + outline.

It ships in **10 colours** — hence *Prism*. Six flat ones and a plain white
default; three "premium" ones that are **iridescent** — the fill and outline
cycle hue like holographic foil (rEFInd has no shader to do that live, so it's
pre-rendered into the PNG).

![all ten selection styles](preview.png)

| tier | colours |
|---|---|
| default | `white` |
| flat | `green` · `red` · `violet` · `pink` · `gray` · `blue` |
| premium · iridescent | `obsidian-purple` · `titanium-silver` · `champagne-gold` |

![white / blue / obsidian-purple in a mock menu](preview-menu.png)

The colour lives entirely in `selection_big.png` / `selection_small.png`. The
icon set, the black background, `theme.conf` and the layout are identical
across every colour — switching colour only swaps those two PNGs.

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
   `theme.conf` expects), with the colour you picked staged as
   `selection_big.png` / `selection_small.png`;
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

Swaps the two selection PNGs in place; `refind.conf` and the icons are left
untouched.

### If rEFInd isn't installed yet

`install.sh` stops with instructions — set up rEFInd itself first
(`sudo refind-install`), then re-run. Or pass `--deploy-refind` to let the
script call `refind-install` for you once.

## Manual install

1. Copy this directory to `<your ESP>/EFI/refind/themes/prism-minimal/`.
2. Pick a colour: copy `colors/<name>/selection_big.png` and
   `selection_small.png` over the two files of the same name at the top of the
   theme dir. (`white` is already in place.)
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
icons/                 the OS / tool icon set (one set, shared by every colour)
colors/<name>/         selection_big.png + selection_small.png per colour
install.sh             the installer (also --uninstall)
tools/generate.py      regenerates every colors/ asset from code
```

## Regenerating the outline assets

```
python3 tools/generate.py              # rebuild all colours
python3 tools/generate.py blue green   # just some
python3 tools/generate.py --preview    # also rebuild preview*.png
```

Needs `Pillow` and `numpy` (dev-only). Colours, geometry and the iridescence
parameters all live at the top of that file. After regenerating, re-sync the
default:

```
cp colors/white/selection_big.png selection_big.png
cp colors/white/selection_small.png selection_small.png
```

## Credits

Icon set and base layout from
[rEFInd-minimal](https://github.com/EvanPurkhiser/rEFInd-minimal) by Evan
Purkhiser. Colour + iridescent selection system and installer added here.
