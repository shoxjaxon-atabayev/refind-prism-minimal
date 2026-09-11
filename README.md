# Prism Minimal

A minimal [rEFInd](https://www.rodsbooks.com/refind/) boot theme. One solid
background, silhouette icons, no labels. Pick a colour and the icons and
selection outline turn that colour. The entry you're about to boot gets a
thin outline: a square on the top row, a circle on the tools row. The six
premium gradients (below) work the other way round — icons stay plain and
the gradient lives in the selection: border, a soft fill, and a glow.

![every colour, dark and light](preview.png)

![a mock boot menu](preview-menu.png)

## Install

```
git clone https://github.com/shoxjaxon-atabayev/refind-prism-minimal.git
cd refind-prism-minimal
./install.sh
```

No pre-built colour library is cloned — there's nothing bulky to fetch.
Colour variants are generated on your machine, on the spot, by
`tools/generate.py` (needs **Python 3 + Pillow + numpy**; the installer
checks for these first and tells you what to install if either is missing).

Run with no `--color` and a terminal attached, and you get an interactive
picker:

```
Prism Minimal
─────────────

Select theme colours:

❯ ◉ White             the default — plain white / dark ink
  ◯ Aurora             premium gradient · emerald → cyan
  ◯ Solaris            premium gradient · amber → orange
  ◯ Forest             premium gradient · green → lime
  ◯ Rose Gold          premium gradient · pink → champagne
  ◯ Cyberpunk          premium gradient · magenta → cyan
  ◯ Platinum           premium gradient · cool grey → white
  ...

↑/↓ Navigate   Space Select   Enter Install
```

Toggle as many colours as you like with Space; the first one (in the list
above) becomes the active theme, the rest are generated too but not wired
in — handy if you want to eyeball a few before committing to one. Press
Enter with nothing selected and you get `white`, unchanged. It then asks for
your password (writing the EFI partition needs root), then **reboot** to see
it.

## Change the colour

```
./install.sh --color blue                # no prompt, skips the menu
./install.sh --color obsidian-purple
./install.sh --color blue,aurora         # generate both; blue (first) is active
```

Colours: `white` `green` `red` `violet` `pink` `gray` `blue`
`obsidian-purple` `titanium-silver` `champagne-gold` `aurora` `solaris`
`forest` `rose-gold` `cyberpunk` `platinum`
&nbsp;&nbsp;*(`obsidian-purple`/`titanium-silver`/`champagne-gold` shimmer;
`aurora`/`solaris`/`forest`/`rose-gold`/`cyberpunk`/`platinum` are premium
gradients for the dark background)*

An unknown colour name warns and is skipped rather than aborting the
install — e.g. `--color purple,blue` installs `blue` and prints:

```
⚠ Unknown color: purple
  Available colors: white green red violet ...
```

Run `./install.sh --list` to see every colour and its note.

## Change the background

```
./install.sh --background light
./install.sh --background dark
```

`dark` is black (default), `light` is near-white (icons and outline turn dark
so they stay readable).

## Combine them

```
./install.sh --color champagne-gold --background light
```

Re-run with different options any time to switch — it only swaps the images,
nothing else. Run `./install.sh --list` to see every option.

## Remove it

```
./install.sh --uninstall
```

Puts `refind.conf` back the way it was.

## All commands

| command | what it does |
|---|---|
| `./install.sh` | interactive colour picker, `dark` background |
| `./install.sh --color <name>[,<name>...]` | pick one or more colours without the picker |
| `./install.sh --background <dark\|light>` | pick a background (short: `--bg`) |
| `./install.sh --list` | list the colours and backgrounds |
| `./install.sh --uninstall` | remove the theme, restore `refind.conf` |
| `./install.sh --dry-run` | show what would happen, change nothing |
| `./install.sh --yes` | don't ask for confirmation |
| `./install.sh --refind-dir <path>` | if it can't find rEFInd, point it at the folder with `refind.conf` |
| `./install.sh --deploy-refind` | if rEFInd itself isn't installed, set it up first |

## Notes

* **rEFInd must already be installed.** If it isn't, `./install.sh` stops and
  tells you what to run (`sudo refind-install`), or pass `--deploy-refind` and
  it does that step for you.
* **Needs Python 3 + Pillow + numpy** to generate the colour you pick. The
  installer checks for these up front and tells you exactly what's missing.
* **Safe to re-run.** It only ever touches `themes/prism-minimal/` on your EFI
  partition and one marked block in `refind.conf` (backed up first). It never
  touches boot entries, Secure Boot, or other bootloaders.
* If a theme file ever goes missing, rEFInd just falls back to its built-in
  look — you never get a broken boot menu.

## Manual install (no script)

There's no pre-built `colors/` folder to copy from — generate the look you
want first, then place it by hand:

1. `python3 tools/generate.py <colour> --out-dir=/tmp/prism-look` (needs
   Pillow + numpy — `pip install Pillow numpy` if you don't have them).
2. Copy this repo's folder to `<your EFI partition>/EFI/refind/themes/prism-minimal/`.
3. Copy files over the ones at the top of that folder:
   * `backgrounds/dark.png` **or** `backgrounds/light.png` → `background.png`
   * from `/tmp/prism-look/<colour>/` (dark bg) or
     `/tmp/prism-look/<colour>/light/` (light bg): `selection_big.png`,
     `selection_small.png`, and the whole `icons/` folder
4. Add one line to `refind.conf`:

   ```
   include themes/prism-minimal/theme.conf
   ```

## Developing

`tools/generate.py` builds every `<out>/<name>/` (and `<out>/<name>/light/`)
from `icons/` plus the constants at the top of the file — colours,
backgrounds, icon padding, iridescence. With no `--out-dir`, `<out>` is
`build/` in this checkout (gitignored, never committed) and a plain
no-args run also rewrites the committed `backgrounds/dark.png` /
`backgrounds/light.png` (harmless — they're deterministic solid fills).

```
python3 tools/generate.py                       # rebuild everything into build/colors/
python3 tools/generate.py blue red               # just some colours
python3 tools/generate.py --list                 # print available colour names
python3 tools/generate.py --preview               # also rebuild preview*.png
python3 tools/generate.py white --out-dir=/tmp/x  # build one colour elsewhere
```

Then re-sync the repo's default copies (used by `--help`/docs and as a
manual-install fallback — not read by `install.sh`, which always generates
fresh):

```
cp backgrounds/dark.png background.png
cp build/colors/white/selection_big.png selection_big.png
cp build/colors/white/selection_small.png selection_small.png
```

## Credits

Icons and base layout from
[rEFInd-minimal](https://github.com/EvanPurkhiser/rEFInd-minimal) by Evan
Purkhiser. The colour / background system and the installer are new here.
