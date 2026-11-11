#!/usr/bin/env bash
# Installs everything the 3d-short skill needs: Blender (>= 4.2), ffmpeg, a Python venv with the engine's packages,
# and the free Piper voice model.  macOS (Homebrew) and Linux (apt) are supported; Windows uses install.ps1.
#
#   bash engine/setup/install.sh          # asks once before installing anything
#   bash engine/setup/install.sh --yes    # no question
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
YES=0; [[ "${1:-}" == "--yes" ]] && YES=1
OS="$(uname -s)"

say() { printf '\n== %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

blender_ok() {
  local b="${BLENDER:-}"
  [[ -z "$b" ]] && b="$(command -v blender || true)"
  [[ -z "$b" && -x /Applications/Blender.app/Contents/MacOS/Blender ]] && b=/Applications/Blender.app/Contents/MacOS/Blender
  [[ -z "$b" ]] && b="$(ls -d "$HOME"/.local/blender/*/blender 2>/dev/null | tail -1 || true)"
  [[ -n "$b" && -x "$b" ]] || return 1
  local v; v="$("$b" --version 2>/dev/null | head -1 | sed -E 's/[^0-9]*([0-9]+)\.([0-9]+).*/\1 \2/')"
  set -- $v
  [[ "${1:-0}" -gt 4 || ( "${1:-0}" -eq 4 && "${2:-0}" -ge 2 ) ]]
}

PY=""
for c in python3.12 python3.13 python3.11 python3; do have "$c" && { PY="$c"; break; }; done

todo=()
blender_ok || todo+=("Blender (4.2 or newer)")
have ffmpeg || todo+=("ffmpeg")
[[ -n "$PY" ]] || todo+=("Python 3.10+")
[[ -d .venv ]] || todo+=("Python packages in ./.venv (numpy, scipy, pillow, piper-tts)")
[[ -f assets/voices/en_US-libritts_r-medium.onnx ]] || todo+=("Piper voice model en_US-libritts_r-medium (~75 MB, CC BY 4.0)")

if [[ ${#todo[@]} -eq 0 ]]; then
  say "Nothing to install."
else
  say "This will install:"; printf '  - %s\n' "${todo[@]}"
  if [[ $YES -eq 0 ]]; then
    read -r -p "Go ahead? [y/N] " a
    [[ "$a" =~ ^[Yy] ]] || { echo "Cancelled."; exit 1; }
  fi
fi

# ---- Blender + ffmpeg + Python
if [[ "$OS" == "Darwin" ]]; then
  have brew || { echo "Homebrew is required on macOS: https://brew.sh"; exit 1; }
  blender_ok || brew install --cask blender
  have ffmpeg || brew install ffmpeg
  [[ -n "$PY" ]] || { brew install python@3.12; PY=python3.12; }
elif [[ "$OS" == "Linux" ]]; then
  if ! have ffmpeg || [[ -z "$PY" ]]; then
    have apt-get || { echo "Install ffmpeg and python3 (with venv) with your package manager, then re-run."; exit 1; }
    sudo apt-get update && sudo apt-get install -y ffmpeg python3 python3-venv python3-pip
    PY=python3
  fi
  if ! blender_ok; then
    VER=4.5.3; SERIES=4.5
    DIR="$HOME/.local/blender"; mkdir -p "$DIR"
    URL="https://download.blender.org/release/Blender${SERIES}/blender-${VER}-linux-x64.tar.xz"
    say "Downloading Blender ${VER} to ${DIR}"
    curl -fL "$URL" -o "$DIR/blender.tar.xz"
    tar -xf "$DIR/blender.tar.xz" -C "$DIR" && rm "$DIR/blender.tar.xz"
    mv "$DIR/blender-${VER}-linux-x64" "$DIR/${VER}" 2>/dev/null || true
    echo "Blender installed in $DIR/${VER}"
  fi
else
  echo "Unsupported OS ($OS). On Windows run: powershell -ExecutionPolicy Bypass -File engine\\setup\\install.ps1"; exit 1
fi

# ---- Python venv
say "Python packages"
[[ -d .venv ]] || "$PY" -m venv .venv
echo "(installing numpy, scipy, pillow, piper-tts - this takes a few minutes)"
.venv/bin/python -m pip install --upgrade pip | tail -1
.venv/bin/python -m pip install -r engine/requirements.txt | grep -E "^(Collecting|Successfully)" || true

# ---- Piper voice (not stored in git)
mkdir -p assets/voices
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium"
for f in en_US-libritts_r-medium.onnx en_US-libritts_r-medium.onnx.json; do
  [[ -f "assets/voices/$f" ]] || { say "Downloading voice $f"; curl -fL "$BASE/$f?download=true" -o "assets/voices/$f"; }
done

say "Checking the install"
.venv/bin/python engine/setup/doctor.py
