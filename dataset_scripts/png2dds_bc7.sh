#!/usr/bin/env bash
#
# png2dds_bc7.sh - convert a folder of PNG images to BC7-compressed DDS files.
#
# Encoding is done by DirectXTex "texconv". Put it on PATH or point TEXCONV at
# the binary (a texconv.exe run through Wine also works).
#
set -euo pipefail

readonly PROG=${0##*/}

usage() {
  cat <<EOF
Usage: $PROG [options] [folder]

Convert every .png in <folder> (default: current directory) to a
BC7-compressed .dds file.

Options:
  -o, --out DIR       write .dds files to DIR (default: next to each .png)
  -r, --recursive     recurse into subfolders and mirror the tree under DIR
  -m, --mips [N]      generate mipmaps: all levels, or exactly N levels
  -s, --srgb          encode as BC7_UNORM_SRGB (color/albedo textures)
  -q, --quality MODE  BC7 effort: fast, normal (default), or max
  -f, --force         overwrite existing .dds files (default: skip them)
  -n, --dry-run       list what would be converted, run nothing
  -h, --help          show this help

Environment:
  TEXCONV             path to the texconv binary (default: search PATH)

Examples:
  $PROG textures/
  $PROG -r -o build/textures -s -m assets/
  TEXCONV=/opt/texconv/texconv $PROG -q max ui/
EOF
}

die()  { printf '%s: error: %s\n' "$PROG" "$*" >&2; exit 1; }
warn() { printf '%s: warning: %s\n' "$PROG" "$*" >&2; }
note() { printf '%s\n' "$*"; }

src=
out=
recursive=false
mips=1
srgb=false
quality=normal
force=false
dry_run=false

while (($#)); do
  case $1 in
    -o|--out)
      (($# >= 2)) || die "$1 requires a directory"
      out=$2
      shift 2
      ;;
    -r|--recursive)
      recursive=true
      shift
      ;;
    -m|--mips)
      mips=0
      if [[ ${2:-} =~ ^[0-9]+$ ]]; then
        mips=$2
        shift 2
      else
        shift
      fi
      ;;
    -s|--srgb)
      srgb=true
      shift
      ;;
    -q|--quality)
      (($# >= 2)) || die "$1 requires a mode (fast, normal, max)"
      quality=$2
      shift 2
      ;;
    -f|--force)
      force=true
      shift
      ;;
    -n|--dry-run)
      dry_run=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      die "unknown option '$1' (try --help)"
      ;;
    *)
      [[ -z $src ]] || die "only one source folder may be given"
      src=$1
      shift
      ;;
  esac
done

for arg in "$@"; do
  [[ -z $src ]] || die "only one source folder may be given"
  src=$arg
done

[[ -n $src ]] || src=.

case $quality in
  fast|normal|max) ;;
  *) die "invalid quality '$quality' (expected fast, normal, or max)" ;;
esac

[[ -d $src ]] || die "not a directory: $src"
src=$(realpath -- "$src")
[[ -n $out ]] || out=$src
out=$(realpath -m -- "$out")

find_texconv() {
  local c

  if [[ -n ${TEXCONV:-} ]]; then
    if [[ -x $TEXCONV ]]; then
      printf '%s\n' "$TEXCONV"
      return 0
    fi
    if command -v "$TEXCONV" >/dev/null 2>&1; then
      command -v "$TEXCONV"
      return 0
    fi
    die "TEXCONV is set to '$TEXCONV' but it is not executable"
  fi

  for c in texconv texconv.exe; do
    if command -v "$c" >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done

  cat >&2 <<'EOF'
texconv not found.

This script uses DirectXTex's texconv to encode BC7 DDS files.
Install it and put it on PATH, or set TEXCONV to its location:

  TEXCONV=/path/to/texconv png2dds_bc7.sh ...

Source: https://github.com/microsoft/DirectXTex
On Linux, a Windows texconv.exe also works when run through Wine.
EOF
  exit 1
}

texconv_bin=$(find_texconv)

conv_cmd=("$texconv_bin")
if [[ ${texconv_bin##*/} == *.exe ]]; then
  command -v wine >/dev/null 2>&1 || die "found $texconv_bin but wine is not installed"
  conv_cmd=(wine "$texconv_bin")
fi

fmt=BC7_UNORM
if $srgb; then
  fmt=BC7_UNORM_SRGB
fi

tex_args=(-nologo -y -nogpu -ft dds -f "$fmt" -m "$mips")
case $quality in
  fast) tex_args+=(-bcquick) ;;
  max)  tex_args+=(-bcmax) ;;
esac

converted=0
skipped=0
failed=0
planned=0
found=0

convert_dir() {
  local dir=$1 dest=$2
  local -a pngs=()
  local -a todo=()
  local f base target

  while IFS= read -r -d '' f; do
    pngs+=("$f")
  done < <(find "$dir" -maxdepth 1 -type f -iname '*.png' -print0 | sort -z)

  ((${#pngs[@]})) || return 0
  found=$((found + ${#pngs[@]}))

  for f in "${pngs[@]}"; do
    base=${f##*/}
    base=${base%.*}
    target=$dest/$base.dds
    if [[ -e $target ]] && ! $force; then
      note "skip  $target"
      skipped=$((skipped + 1))
      continue
    fi
    todo+=("$f")
  done

  ((${#todo[@]})) || return 0

  if $dry_run; then
    for f in "${todo[@]}"; do
      base=${f##*/}
      base=${base%.*}
      note "plan  $f -> $dest/$base.dds"
      planned=$((planned + 1))
    done
    return 0
  fi

  if ! mkdir -p -- "$dest"; then
    warn "cannot create output directory: $dest"
    failed=$((failed + ${#todo[@]}))
    return 0
  fi

  local chunk=128 i
  local -a batch
  for ((i = 0; i < ${#todo[@]}; i += chunk)); do
    batch=("${todo[@]:i:chunk}")
    if ! "${conv_cmd[@]}" "${tex_args[@]}" -o "$dest" "${batch[@]}"; then
      warn "texconv reported an error in $dir"
    fi
    for f in "${batch[@]}"; do
      base=${f##*/}
      base=${base%.*}
      if [[ -e $dest/$base.dds ]]; then
        converted=$((converted + 1))
      else
        failed=$((failed + 1))
      fi
    done
  done
}

if $recursive; then
  find_args=("$src" -type d)
  if [[ $out == "$src"/* ]]; then
    find_args+=(-not -path "$out" -not -path "$out/*")
  fi
  while IFS= read -r -d '' dir; do
    rel=${dir#"$src"}
    rel=${rel#/}
    if [[ -n $rel ]]; then
      convert_dir "$dir" "$out/$rel"
    else
      convert_dir "$dir" "$out"
    fi
  done < <(find "${find_args[@]}" -print0 | sort -z)
else
  convert_dir "$src" "$out"
fi

if ((found == 0)); then
  note "No .png files found under $src"
  exit 0
fi

if $dry_run; then
  note "Dry run: $planned file(s) would be converted, $skipped skipped."
  exit 0
fi

note "Converted: $converted   Skipped: $skipped   Failed: $failed"
((failed == 0)) || exit 1
