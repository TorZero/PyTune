#!/usr/bin/env bash
set -euo pipefail

sudo apt update
sudo apt install -y \
    mpv libmpv2 ffmpeg \
    python3-pip python3-venv python3-dev python3-numpy \
    build-essential cmake pkg-config \
    libfftw3-dev \
    qt6-base-dev qt6-base-dev-tools

python3 -m pip install --user -r requirements.txt

echo ""
echo "Dependencies installed. Build native core now with:"
echo "  cd $(pwd)"
echo "  ./native/build_native.sh --core-only"
echo "Then launch:"
echo "  ./run_pytune_hfplus_v14.sh"
