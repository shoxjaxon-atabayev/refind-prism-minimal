# Prism Minimal

A minimal [rEFInd](https://www.rodsbooks.com/refind/) boot theme. One solid
background, silhouette icons, no labels. Pick a colour and everything — icons
and the selection outline — turns that colour. The entry you're about to boot
gets a thin outline: a square on the top row, a circle on the tools row.

![every colour, dark and light](preview.png)

![a mock boot menu](preview-menu.png)

## Install

```
git clone https://github.com/shoxjaxon-atabayev/refind-prism-minimal.git
cd refind-prism-minimal
./install.sh
```

That's it. This installs the **white** theme on a **black** background. It asks
for your password (writing the EFI partition needs root), then **reboot** to
see it.

## Change the colour

```
./install.sh --color blue
./install.sh --color obsidian-purple
```

Colours: `white` `green` `red` `violet` `pink` `gray` `blue`
`obsidian-purple` `titanium-silver` `champagne-gold`
&nbsp;&nbsp;*(the last three shimmer)*

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
| `./install.sh` | install `white` on a `dark` background |
| `./install.sh --color <name>` | pick a colour |
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
* **Safe to re-run.** It only ever touches `themes/prism-minimal/` on your EFI
  partition and one marked block in `refind.conf` (backed up first). It never
  touches boot entries, Secure Boot, or other bootloaders.
* If a theme file ever goes missing, rEFInd just falls back to its built-in
  look — you never get a broken boot menu.

## Manual install (no script)

1. Copy this folder to `<your EFI partition>/EFI/refind/themes/prism-minimal/`.
2. Choose a look and copy its files over the ones at the top of that folder:
   * `backgrounds/dark.png` **or** `backgrounds/light.png` → `background.png`
   * from `colors/<colour>/` (dark bg) or `colors/<colour>/light/` (light bg):
     `selection_big.png`, `selection_small.png`, and the whole `icons/` folder
3. Add one line to `refind.conf`:

   ```
   include themes/prism-minimal/theme.conf
   ```

## Developing

`tools/generate.py` builds `backgrounds/` and every `colors/<name>/` (and
`colors/<name>/light/`) from `icons/` plus the constants at the top of the
file — colours, backgrounds, icon padding, iridescence.

```
python3 tools/generate.py            # rebuild everything (needs Pillow + numpy)
python3 tools/generate.py blue red   # just some colours
python3 tools/generate.py --preview  # also rebuild preview*.png
```

Then re-sync the repo's default copies:

```
cp backgrounds/dark.png background.png
cp colors/white/selection_big.png selection_big.png
cp colors/white/selection_small.png selection_small.png
```

## Credits

Icons and base layout from
[rEFInd-minimal](https://github.com/EvanPurkhiser/rEFInd-minimal) by Evan
Purkhiser. The colour / background system and the installer are new here.
