#!/usr/bin/env bash
# Pytune HF+ — one-command installer for Ubuntu / Debian / Linux Mint
# Usage: ./install.sh [--no-system-deps] [--no-desktop] [--dev]
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"

INSTALL_DIR="$(pwd)"
PYTHON_BIN="${PYTUNE_PYTHON:-$(command -v python3)}"
SKIP_SYSTEM=0
SKIP_DESKTOP=0
DEV_MODE=0

for arg in "$@"; do
    case "$arg" in
        --no-system-deps) SKIP_SYSTEM=1 ;;
        --no-desktop)     SKIP_DESKTOP=1 ;;
        --dev)            DEV_MODE=1 ;;
        --help|-h)
            cat <<'EOF'
Usage: ./install.sh [options]

Options:
  --no-system-deps   Skip apt install (if you already have mpv/ffmpeg/build-essential)
  --no-desktop       Skip creating the .desktop launcher shortcut
  --dev              Also install development tools (pyFFTW, etc.)
  --help             Show this message

Environment:
  PYTUNE_PYTHON=python3.11   Override the Python interpreter used
EOF
            exit 0 ;;
    esac
done

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

step() { echo -e "\n${BOLD}▶ $1${NC}"; }
ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }

echo ""
echo -e "${BOLD}Pytune HF+ V16r2 — Installer${NC}"
echo "Install directory: $INSTALL_DIR"
echo "Python:            $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"
echo ""

# ── 1. System packages ──────────────────────────────────────────────────────
if [[ $SKIP_SYSTEM -eq 0 ]]; then
    step "Installing system packages"
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update -qq
        sudo apt-get install -y \
            mpv libmpv2 ffmpeg \
            python3-dev build-essential cmake \
            libfftw3-dev \
            qt6-base-dev qt6-base-dev-tools 2>/dev/null || \
        sudo apt-get install -y \
            mpv libmpv2 ffmpeg \
            python3-dev build-essential cmake \
            libfftw3-dev
        ok "System packages installed"
    else
        warn "apt-get not found; skipping system packages (Fedora/Arch: install mpv ffmpeg python3-devel gcc-c++ cmake fftw-devel)"
    fi
else
    warn "Skipping system packages (--no-system-deps)"
fi

# ── 2. Python dependencies ───────────────────────────────────────────────────
step "Installing Python dependencies"
if "$PYTHON_BIN" -m pip install --quiet --upgrade pip; then
    ok "pip upgraded"
fi
"$PYTHON_BIN" -m pip install --quiet -r requirements.txt
ok "Python dependencies installed"

if [[ $DEV_MODE -eq 1 ]]; then
    "$PYTHON_BIN" -m pip install --quiet "pyFFTW>=0.13" || warn "pyFFTW optional — skipped"
fi

# ── 3. Native C++ FFT core ───────────────────────────────────────────────────
step "Building native C++ FFT core"
if PYTUNE_PYTHON="$PYTHON_BIN" ./native/build_native.sh --core-only; then
    ok "Native FFT module built: pytune_hfplus_native_fft.so"
else
    fail "Native FFT build failed"
    echo "  Install build deps: sudo apt install build-essential python3-dev"
    echo "  Then retry:         cd native && ./build_native.sh --core-only"
    echo "  Or run without native FFT: PYTUNE_REQUIRE_NATIVE=0 ./run_pytune_hfplus_v16r2.sh"
fi

# ── 4. Validate ──────────────────────────────────────────────────────────────
step "Running validation"
if PYTHONPATH="$INSTALL_DIR" "$PYTHON_BIN" tools/validate_native_fft.py >/dev/null 2>&1; then
    ok "native FFT smoke-test passed"
else
    warn "native FFT smoke-test failed (app will fall back to NumPy)"
fi

if PYTHONPATH="$INSTALL_DIR" "$PYTHON_BIN" tools/validate_fft_backends.py 2>&1 | grep -q "ALL BACKENDS PASS"; then
    ok "all FFT backend comparisons passed"
else
    warn "FFT backend comparison had warnings — run manually: PYTHONPATH=. python3 tools/validate_fft_backends.py"
fi

# ── 5. Desktop shortcut ──────────────────────────────────────────────────────
if [[ $SKIP_DESKTOP -eq 0 ]]; then
    step "Installing desktop shortcut"
    DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    mkdir -p "$DESKTOP_DIR"
    ICON_PATH="$INSTALL_DIR/pytune_hfplus.png"
    # Use a generic audio icon if our icon isn't present
    if [[ ! -f "$ICON_PATH" ]]; then
        ICON_PATH="audio-player"
    fi
    cat > "$DESKTOP_DIR/pytune_hfplus.desktop" <<DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Pytune HF+
GenericName=Audio Player
Comment=Professional Linux audio player with real-time FFT spectrum analyzer
Exec=bash -c 'cd "$INSTALL_DIR" && ./run_pytune_hfplus_v16r2.sh'
Icon=$ICON_PATH
Terminal=false
Categories=AudioVideo;Audio;Player;
MimeType=audio/mpeg;audio/flac;audio/ogg;audio/x-wav;audio/mp4;audio/aac;
Keywords=music;player;spectrum;analyzer;equalizer;fft;
StartupNotify=true
DESKTOP
    chmod +x "$DESKTOP_DIR/pytune_hfplus.desktop"
    # Refresh desktop database if available
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    ok "Desktop shortcut: $DESKTOP_DIR/pytune_hfplus.desktop"
else
    warn "Skipping desktop shortcut (--no-desktop)"
fi

# ── 6. Make launchers executable ─────────────────────────────────────────────
chmod +x run_pytune_hfplus_v16r2.sh run_pytune_hfplus_v15r1.sh 2>/dev/null || true

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}Installation complete.${NC}"
echo ""
echo "Launch Pytune HF+:"
echo "  ./run_pytune_hfplus_v16r2.sh"
echo ""
echo "Or open from your application menu: Pytune HF+"
echo ""
