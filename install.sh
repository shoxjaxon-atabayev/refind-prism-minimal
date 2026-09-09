#!/usr/bin/env bash
# Prism Minimal — installer for a minimal rEFInd boot theme with colour variants.
#
#   ./install.sh                    detect rEFInd, install the "white" variant
#   ./install.sh --color blue       install (or just restyle) to a colour
#   ./install.sh --list-colors      list the available colour variants
#   ./install.sh --dry-run          print the plan, change nothing
#   ./install.sh --yes              skip the confirmation prompt
#   ./install.sh --refind-dir PATH  skip detection; PATH is the dir with refind.conf
#   ./install.sh --deploy-refind    run the system's `refind-install` first if
#                                   rEFInd isn't on the ESP yet
#   ./install.sh --uninstall        remove the theme, revert refind.conf
#
# Re-runnable and idempotent. It only ever touches:
#   <refind-dir>/themes/prism-minimal/     — the theme payload
#   one marked block inside <refind-dir>/refind.conf
# It never edits EFI boot entries, NVRAM, or Secure Boot, and never touches any
# other bootloader — unless you pass --deploy-refind, which shells out to the
# system's own `refind-install` exactly once.
#
# Needs root to write the ESP; if you don't run it as root it re-execs itself
# with sudo.

set -euo pipefail

if [ -z "${BASH_VERSINFO:-}" ] || [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "this installer needs bash 4+ (you have ${BASH_VERSION:-a non-bash shell}). Run: bash $0" >&2
  exit 1
fi

ORIG_ARGS=("$@")
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

THEME_SUBDIR="themes/prism-minimal"           # must match the paths inside theme.conf
INCLUDE_LINE="include ${THEME_SUBDIR}/theme.conf"
MARKER_BEGIN="# BEGIN Prism Minimal (managed by install.sh — do not edit this block by hand)"
MARKER_END="# END Prism Minimal"
DEFAULT_COLOR="white"

COLOR="$DEFAULT_COLOR"
REFIND_DIR_OVERRIDE=""
DRY_RUN=0
ASSUME_YES=0
UNINSTALL=0
DEPLOY_REFIND=0
LIST_COLORS=0

# --------------------------------------------------------------- output --

if [ -t 1 ]; then
  _r=$'\033[31m'; _g=$'\033[32m'; _y=$'\033[33m'; _b=$'\033[1m'; _x=$'\033[0m'
else
  _r=""; _g=""; _y=""; _b=""; _x=""
fi
info() { printf '  %s\n' "$*"; }
step() { printf '\n%s%s%s\n' "$_b" "$*" "$_x"; }
ok()   { printf '%s[ok]%s %s\n'   "$_g" "$_x" "$*"; }
warn() { printf '%s[warn]%s %s\n' "$_y" "$_x" "$*"; }
# die = a deliberate, already-explained stop: clear the trap so we don't also
# print the generic "aborted" line after our specific message.
die()  { printf '%s[error]%s %s\n' "$_r" "$_x" "$*" >&2; trap - EXIT; exit 1; }

on_exit() {
  local status=$?
  [ "$status" -ne 0 ] && printf '%s[error]%s aborted (exit %s) — nothing was left half-written; safe to re-run.\n' "$_r" "$_x" "$status" >&2
  return 0
}
trap on_exit EXIT

# -------------------------------------------------------------- helpers --

# Print the leading comment block (everything from line 2 up to the first
# non-comment line), with the "# " stripped.
usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$SELF"; }

timestamp() { date +%Y%m%d-%H%M%S; }

# A path that definitely doesn't exist yet (two runs in one second, etc.).
unique_path() {
  local base cand n=2
  base="$1-$(timestamp)"
  cand="$base"
  while [ -e "$cand" ]; do cand="${base}-${n}"; n=$((n + 1)); done
  printf '%s\n' "$cand"
}

# Normalise "Obsidian Purple" / obsidian_purple / OBSIDIAN-PURPLE -> obsidian-purple
normalise_color() {
  printf '%s\n' "$1" | tr '[:upper:] _' '[:lower:]--'
}

available_colors() {
  local d
  for d in "$SCRIPT_DIR"/colors/*/; do
    [ -d "$d" ] || continue
    [ -f "${d}selection_big.png" ] && [ -f "${d}selection_small.png" ] || continue
    basename "$d"
  done | sort
}

color_note() {
  case "$1" in
    white)                echo "default — clean white border" ;;
    green|red|violet|pink|gray|blue)
                          echo "flat $1 border + tinted tile" ;;
    obsidian-purple)      echo "premium · iridescent violet→magenta→teal" ;;
    titanium-silver)      echo "premium · iridescent brushed silver" ;;
    champagne-gold)       echo "premium · iridescent warm gold foil" ;;
    *)                    echo "" ;;
  esac
}

reexec_with_sudo() {
  command -v sudo >/dev/null 2>&1 \
    || die "need root to work with the ESP, and sudo isn't installed — re-run this as root."
  info "$1"
  trap - EXIT
  exec sudo -- "$SELF" ${ORIG_ARGS[@]+"${ORIG_ARGS[@]}"}
}

# Re-exec with sudo up front only if we can't even *look* for rEFInd unprivileged
# (the ESP is very often root-only, mode 700). If detection is possible as the
# user, we defer the decision to ensure_writable() once the real target is known.
escalate_if_needed() {
  [ "$DRY_RUN" -eq 1 ] && return 0
  [ "$(id -u)" -eq 0 ] && return 0

  if [ -n "$REFIND_DIR_OVERRIDE" ]; then
    { [ -d "$REFIND_DIR_OVERRIDE" ] && [ -w "$REFIND_DIR_OVERRIDE" ]; } && return 0
    reexec_with_sudo "not root — re-running under sudo to write $REFIND_DIR_OVERRIDE…"
  fi

  local r
  for r in /boot /boot/efi /boot/EFI /efi; do
    [ -e "$r" ] || continue
    ls "$r" >/dev/null 2>&1 || \
      reexec_with_sudo "not root and $r is not readable — re-running under sudo…"
  done
}

# Definitive check: we know the rEFInd dir now; if we can't write it, escalate.
ensure_writable() {
  [ "$(id -u)" -eq 0 ] && return 0
  [ -w "$1" ] && return 0
  reexec_with_sudo "not root — re-running under sudo to write $1…"
}

# Every FAT/ESP-ish mount root worth searching, de-duplicated, existing only.
candidate_roots() {
  local roots=(/boot /boot/efi /boot/EFI /efi /boot/EFI/BOOT) r seen=""
  if command -v findmnt >/dev/null 2>&1; then
    while IFS= read -r r; do [ -n "$r" ] && roots+=("$r"); done \
      < <(findmnt -rno TARGET,FSTYPE 2>/dev/null | awk '$2 ~ /vfat|fat/ {print $1}')
  fi
  for r in "${roots[@]}"; do
    [ -d "$r" ] || continue
    case ",$seen," in *",$r,"*) continue ;; esac
    seen="$seen,$r"
    printf '%s\n' "$r"
  done
}

# rEFInd install dirs = a refind.conf (or refind_*.efi) next to a refind_*.efi
# binary. De-dup by the refind_*.efi inode, because the same ESP is often
# mounted at several of the candidate roots at once.
find_refind_installs() {
  local root efi dir key seen=""
  while IFS= read -r root; do
    while IFS= read -r efi; do
      dir="$(dirname "$efi")"
      key="$(stat -c '%d:%i' "$efi" 2>/dev/null || printf 'p:%s' "$efi")"
      case ",$seen," in *",$key,"*) continue ;; esac
      seen="$seen,$key"
      printf '%s\n' "$dir"
    done < <(find "$root" -maxdepth 5 -type f \( -iname 'refind_x64.efi' -o -iname 'refind_ia32.efi' -o -iname 'refind_aa64.efi' \) 2>/dev/null)
  done < <(candidate_roots)
}

is_refind_dir() {
  [ -d "$1" ] || return 1
  ls "$1"/refind_*.efi >/dev/null 2>&1 || ls "$1"/refind.conf >/dev/null 2>&1
}

# Resolves the rEFInd directory into the global REFIND_DIR, or dies with guidance.
REFIND_DIR=""
resolve_refind_dir() {
  if [ -n "$REFIND_DIR_OVERRIDE" ]; then
    is_refind_dir "$REFIND_DIR_OVERRIDE" \
      || die "--refind-dir '$REFIND_DIR_OVERRIDE' has no refind_*.efi or refind.conf in it."
    REFIND_DIR="$(cd "$REFIND_DIR_OVERRIDE" && pwd)"
    return 0
  fi

  local installs count
  mapfile -t installs < <(find_refind_installs)
  count=${#installs[@]}

  if [ "$count" -eq 0 ] && [ "$DEPLOY_REFIND" -eq 1 ]; then
    deploy_refind
    mapfile -t installs < <(find_refind_installs)
    count=${#installs[@]}
  fi

  if [ "$count" -eq 0 ]; then
    # In --dry-run we may just be unable to *read* a root-only ESP as the user.
    # Don't hard-fail a preview: guess a path so the plan still prints.
    if [ "$DRY_RUN" -eq 1 ] && [ "$(id -u)" -ne 0 ]; then
      local guess
      for guess in /boot/EFI/refind /boot/efi/EFI/refind /efi/EFI/refind /boot/EFI/BOOT; do
        REFIND_DIR="$guess"; break
      done
      warn "can't scan the ESP without root — guessing $REFIND_DIR for this preview."
      warn "run 'sudo $SELF --dry-run …' (or without --dry-run) for real detection."
      return 0
    fi
    { printf '%s[error]%s no rEFInd install found under: ' "$_r" "$_x"
      candidate_roots | paste -sd' '
      cat <<EOF

rEFInd itself is not on your EFI System Partition yet. Set it up first, then
re-run this:

  sudo refind-install            # Arch: pacman -S refind && sudo refind-install
  sudo $SELF --color $COLOR

Or let this script run refind-install for you:

  sudo $SELF --deploy-refind --color $COLOR

If rEFInd *is* installed somewhere unusual, point at it directly:

  sudo $SELF --refind-dir /path/to/dir/with/refind.conf --color $COLOR
EOF
    } >&2
    die "rEFInd not found."
  fi

  if [ "$count" -gt 1 ]; then
    warn "found more than one rEFInd install:"
    printf '    %s\n' "${installs[@]}" >&2
    die "ambiguous — pick one with:  sudo $SELF --refind-dir <path> --color $COLOR"
  fi

  REFIND_DIR="${installs[0]}"
}

deploy_refind() {
  step "deploying rEFInd (--deploy-refind)"
  command -v refind-install >/dev/null 2>&1 \
    || die "refind-install not found — install the 'refind' package first (e.g. pacman -S refind)."
  info "running: refind-install"
  refind-install || die "refind-install failed — see its output above; nothing of this theme was written."
  ok "refind-install finished"
}

# Print $conf with any prior managed block removed. Safe on a file that has none
# and on one with CRLF line endings.
strip_block() {
  awk -v b="$MARKER_BEGIN" -v e="$MARKER_END" '
    { sub(/\r$/, "") }
    $0 == b { skip = 1; next }
    $0 == e { skip = 0; next }
    skip   { next }
    { print }
  ' "$1"
}

# ------------------------------------------------------------- validate --

# The icon set for the chosen colour: colors/<colour>/icons/ (the whole set
# recoloured to that hue) if present, else the repo's plain icons/ — that's
# what "white" uses.
icons_src() {
  if [ -d "$SCRIPT_DIR/colors/$COLOR/icons" ]; then
    printf '%s\n' "$SCRIPT_DIR/colors/$COLOR/icons"
  else
    printf '%s\n' "$SCRIPT_DIR/icons"
  fi
}

validate_source() {
  step "checking theme source"
  local missing=0 f
  for f in theme.conf background.png; do
    [ -f "$SCRIPT_DIR/$f" ] || { warn "missing: $f"; missing=1; }
  done
  [ -d "$SCRIPT_DIR/icons" ] || { warn "missing: icons/"; missing=1; }
  [ -d "$SCRIPT_DIR/colors" ] || { warn "missing: colors/"; missing=1; }
  ls "$SCRIPT_DIR"/icons/*.png >/dev/null 2>&1 || { warn "icons/ has no PNGs"; missing=1; }
  [ "$missing" -eq 0 ] \
    || die "theme source is incomplete — run this from inside the refind-prism-minimal checkout."

  if ! available_colors | grep -qx "$COLOR"; then
    warn "colour '$COLOR' not found. Available:"
    available_colors | sed 's/^/    /' >&2
    die "pick one with --color, or run --list-colors."
  fi
  local isrc; isrc="$(icons_src)"
  ls "$isrc"/*.png >/dev/null 2>&1 \
    || die "$isrc has no PNGs — regenerate with tools/generate.py."
  ok "source OK — colour: $COLOR  (icons: ${isrc#"$SCRIPT_DIR"/})"
}

# After copying, make sure every path theme.conf points at actually resolves
# from refind.conf's directory, the way rEFInd will read it.
validate_installed() {
  local refind_dir="$1" conf="$1/$THEME_SUBDIR/theme.conf" directive value bad=0
  [ -f "$conf" ] || die "post-install check: $conf is missing."
  while read -r directive value _; do
    case "$directive" in
      icons_dir)
        [ -d "$refind_dir/$value" ] || { warn "theme.conf: icons_dir '$value' missing under $refind_dir"; bad=1; } ;;
      selection_big|selection_small|banner)
        [ -f "$refind_dir/$value" ] || { warn "theme.conf: $directive '$value' missing under $refind_dir"; bad=1; } ;;
    esac
  done < <(sed 's/\r$//' "$conf" | awk '!/^[[:space:]]*#/ && NF >= 2')
  [ "$bad" -eq 0 ] || die "post-install validation failed (paths above) — theme NOT wired into refind.conf."
  ok "all theme.conf paths resolve from $refind_dir"
}

# True if the installed theme dir already holds exactly what this run would
# write (same files, same chosen colour) — lets a re-run skip the ESP copy
# entirely instead of churning FAT files and rotating a backup every time.
theme_files_current() {
  local target="$1" f rel src
  [ -d "$target" ] || return 1
  cmp -s "$SCRIPT_DIR/theme.conf"      "$target/theme.conf"      || return 1
  cmp -s "$SCRIPT_DIR/background.png"  "$target/background.png"  || return 1
  cmp -s "$SCRIPT_DIR/colors/$COLOR/selection_big.png"   "$target/selection_big.png"   || return 1
  cmp -s "$SCRIPT_DIR/colors/$COLOR/selection_small.png" "$target/selection_small.png" || return 1
  src="$(icons_src)"
  [ "$(find "$src" -maxdepth 1 -type f | wc -l)" \
      -eq "$(find "$target/icons" -maxdepth 1 -type f 2>/dev/null | wc -l)" ] || return 1
  while IFS= read -r f; do
    rel="${f#"$src"/}"
    cmp -s "$f" "$target/icons/$rel" || return 1
  done < <(find "$src" -type f)
  return 0
}

# ------------------------------------------------------------- install --

do_install() {
  local refind_dir conf target backup tmp body fresh=1

  step "locating rEFInd"
  resolve_refind_dir
  refind_dir="$REFIND_DIR"
  conf="$refind_dir/refind.conf"
  target="$refind_dir/$THEME_SUBDIR"
  ok "rEFInd dir: $refind_dir"
  if [ -f "$conf" ]; then info "refind.conf: present"; else info "refind.conf: absent (will be created)"; fi

  validate_source

  if [ -d "$target" ] && theme_files_current "$target"; then fresh=0; fi

  step "plan"
  info "install theme to : $target"
  info "colour           : $COLOR  ($(color_note "$COLOR"))"
  info "refind.conf       : $conf"
  info "managed line      : $INCLUDE_LINE"
  if [ "$fresh" -eq 0 ]; then
    info "theme files       : already current — will only check refind.conf"
  elif [ -d "$target" ]; then
    info "theme files       : replacing (previous kept at ${target##*/}.previous)"
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    warn "dry run — nothing changed."
    return 0
  fi

  if [ "$ASSUME_YES" -ne 1 ] && [ -t 0 ]; then
    printf '\nProceed? [y/N] '
    read -r reply
    case "$reply" in y | Y | yes | YES) ;; *) die "aborted." ;; esac
  fi

  ensure_writable "$refind_dir"

  if [ "$fresh" -eq 1 ]; then
    step "installing theme files"
    if [ -d "$target" ]; then
      rm -rf "$target.previous"
      mv "$target" "$target.previous"
      ok "previous theme moved to $target.previous"
    fi
    mkdir -p "$target"

    # plain cp only — never cp -a/-p and never `install -m`: the ESP is FAT,
    # which has no per-file ownership or mode, so anything that tries to
    # chown/chmod a file there is at best a no-op and at worst an error.
    cp "$SCRIPT_DIR/theme.conf"     "$target/theme.conf"
    cp "$SCRIPT_DIR/background.png" "$target/background.png"
    cp -r "$(icons_src)" "$target/icons"   # the icon set recoloured for this colour
    cp "$SCRIPT_DIR/colors/$COLOR/selection_big.png"   "$target/selection_big.png"
    cp "$SCRIPT_DIR/colors/$COLOR/selection_small.png" "$target/selection_small.png"
    ok "copied theme to $target"
  else
    step "theme files already current — skipping copy"
  fi

  validate_installed "$refind_dir"

  step "wiring into refind.conf"
  local conf_created=0
  if [ ! -f "$conf" ]; then
    conf_created=1
    if [ -r /usr/share/refind/refind.conf-sample ]; then
      cp /usr/share/refind/refind.conf-sample "$conf"
      ok "created refind.conf from the stock sample"
    else
      printf '# created by Prism Minimal install.sh\ntimeout 20\n' > "$conf"
      ok "created a minimal refind.conf"
    fi
  fi

  tmp="$(mktemp)"
  body="$(strip_block "$conf")"
  {
    [ -n "$body" ] && printf '%s\n\n' "$body"
    printf '%s\n%s\n%s\n' "$MARKER_BEGIN" "$INCLUDE_LINE" "$MARKER_END"
  } > "$tmp"

  if cmp -s "$tmp" "$conf"; then
    rm -f "$tmp"
    ok "refind.conf already up to date"
  elif [ "$conf_created" -eq 1 ]; then
    cat "$tmp" > "$conf"
    rm -f "$tmp"
    ok "refind.conf written (include line added)"
  else
    backup="$(unique_path "${conf}.prism-minimal-backup")"
    cp "$conf" "$backup"
    cat "$tmp" > "$conf"      # write in place — keeps the FAT file's identity
    rm -f "$tmp"
    ok "refind.conf updated (backup: $backup)"
  fi

  trap - EXIT
  step "done"
  ok "Prism Minimal installed · colour: $COLOR"
  info "reboot to see it. Change colour any time:  sudo $SELF --color <name>"
  info "remove it entirely:                        sudo $SELF --uninstall"
}

# ----------------------------------------------------------- uninstall --

do_uninstall() {
  local refind_dir conf target backup

  step "locating rEFInd"
  resolve_refind_dir
  refind_dir="$REFIND_DIR"
  conf="$refind_dir/refind.conf"
  target="$refind_dir/$THEME_SUBDIR"
  ok "rEFInd dir: $refind_dir"

  if [ "$DRY_RUN" -eq 1 ]; then
    warn "dry run — would remove $target and the managed block from $conf."
    return 0
  fi

  ensure_writable "$refind_dir"

  step "removing"
  if [ -f "$conf" ] && grep -qF "$MARKER_BEGIN" "$conf"; then
    local body
    body="$(strip_block "$conf")"   # $(...) also trims the now-trailing blank line
    backup="$(unique_path "${conf}.prism-minimal-backup")"
    cp "$conf" "$backup"
    printf '%s\n' "$body" > "$conf"
    ok "managed block removed from refind.conf (backup: $backup)"
  else
    info "no managed block in refind.conf — leaving it alone"
  fi

  # Guard the rm: only ever our own exact paths, never anything else.
  if [ "$target" = "$refind_dir/$THEME_SUBDIR" ] && [ -d "$target" ]; then
    rm -rf "$target"
    ok "removed $target"
  else
    info "$target not present — nothing to remove"
  fi
  if [ -d "$target.previous" ]; then
    rm -rf "$target.previous"
    ok "removed $target.previous"
  fi
  # tidy the themes/ parent, but only if empty (the user may keep other themes)
  if rmdir "$refind_dir/themes" 2>/dev/null; then
    info "removed now-empty themes/"
  fi

  trap - EXIT
  step "done"
  ok "Prism Minimal uninstalled"
  info "refind.conf backups (*.prism-minimal-backup-*) were left for you to delete"
}

# ------------------------------------------------------------- parsing --

while [ $# -gt 0 ]; do
  case "$1" in
    --color)         COLOR="$(normalise_color "${2:-}")"; shift 2 ;;
    --color=*)       COLOR="$(normalise_color "${1#*=}")"; shift ;;
    --refind-dir)    REFIND_DIR_OVERRIDE="${2:-}"; shift 2 ;;
    --refind-dir=*)  REFIND_DIR_OVERRIDE="${1#*=}"; shift ;;
    --dry-run)       DRY_RUN=1; shift ;;
    --yes | -y)      ASSUME_YES=1; shift ;;
    --deploy-refind) DEPLOY_REFIND=1; shift ;;
    --uninstall)     UNINSTALL=1; shift ;;
    --list-colors)   LIST_COLORS=1; shift ;;
    -h | --help)     usage; trap - EXIT; exit 0 ;;
    *)               die "unknown option: $1  (see --help)" ;;
  esac
done

if [ "$LIST_COLORS" -eq 1 ]; then
  printf '%savailable colours%s  (use with --color)\n\n' "$_b" "$_x"
  while IFS= read -r c; do printf '  %-16s %s\n' "$c" "$(color_note "$c")"; done < <(available_colors)
  trap - EXIT
  exit 0
fi

# A cheap sanity check on the checkout before we bother escalating — but the
# authoritative validate_source() call is inside do_install (post-sudo).
if [ "$UNINSTALL" -ne 1 ] && [ ! -d "$SCRIPT_DIR/colors" ]; then
  die "no colors/ dir here — run this from inside the refind-prism-minimal checkout."
fi

escalate_if_needed

if [ "$UNINSTALL" -eq 1 ]; then
  do_uninstall
else
  do_install
fi
