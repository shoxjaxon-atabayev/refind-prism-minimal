# refind-theme

A dark, ultra-minimal [rEFInd](https://www.rodsbooks.com/refind/) boot theme —
pure-black background, white silhouette OS icons, no panels, no labels. The
**selected** entry is marked by a square highlight: a crisp coloured border,
a translucent tinted tile behind the white icon (so the focused icon reads as
*coloured*), and a soft outer glow.

It ships in **10 colours**. Six flat ones and a plain white default; three
"premium" ones with a baked-in **iridescent** sheen (a hue-cycling border plus
a specular streak — rEFInd has no shader to do that live, so it's pre-rendered
into the PNG).

![all ten selection styles](preview.png)

| tier | colours |
|---|---|
| default | `white` |
| flat | `green` · `red` · `violet` · `pink` · `gray` · `blue` |
| premium · iridescent | `obsidian-purple` · `titanium-silver` · `champagne-gold` |

![white / blue / obsidian-purple in a mock menu](preview-menu.png)

Only the selection highlight changes between colours. Everything else — the icon
set, the black background, `theme.conf`, the layout — is identical.

## Install

```
git clone <this repo>
cd refind-theme
./install.sh                       # installs the white variant
./install.sh --color obsidian-purple
```

`install.sh` re-execs itself with `sudo` when it needs to (the ESP is usually
root-only). It:

1. finds your rEFInd install — checks `/boot`, `/boot/efi`, `/boot/EFI`,
   `/efi` and every mounted FAT volume for a `refind_*.efi` next to a
   `refind.conf`;
2. copies the theme to `<refind-dir>/themes/rEFInd-minimal/` (the path
   `theme.conf` already expects), staging the colour you picked as the active
   `selection_big.png` / `selection_small.png`;
3. adds one managed line to `refind.conf`:
   `include themes/rEFInd-minimal/theme.conf` — backing the file up first.

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

Swaps the two selection PNGs in place; `refind.conf` is left untouched.

### If rEFInd isn't installed yet

`install.sh` stops with instructions — set up rEFInd itself first
(`sudo refind-install`), then re-run. Or pass `--deploy-refind` to let the
script call `refind-install` for you once.

## Manual install

1. Copy this directory to `<your ESP>/EFI/refind/themes/rEFInd-minimal/`.
2. Pick a colour: copy `colors/<name>/selection_big.png` and
   `selection_small.png` over the two files of the same name at the top of
   the theme dir. (`white` is already in place.)
3. Add to `refind.conf`:

   ```
   include themes/rEFInd-minimal/theme.conf
   ```

If any themed asset is missing, rEFInd falls back to its built-in rendering —
you always get a usable menu.

## Layout

```
theme.conf            rEFInd directives (unchanged from rEFInd-minimal)
background.png         the black backdrop (banner_scale fillscreen)
selection_big.png      active OS-row highlight   — a copy of colors/white/…
selection_small.png    active tool-row highlight — a copy of colors/white/…
colors/<name>/         selection_big.png + selection_small.png per colour
icons/                 white-silhouette OS / tool icon set
install.sh             the installer (also --uninstall)
tools/generate.py      regenerates every colors/ asset from code
```

## Regenerating the selection assets

```
python3 tools/generate.py              # rebuild all colours
python3 tools/generate.py blue green   # just some
python3 tools/generate.py --preview    # also rebuild preview*.png
```

Needs `Pillow` and `numpy` (dev-only). Geometry, palettes and the iridescence
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
# refind-prism-minimal
