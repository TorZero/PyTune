#!/usr/bin/env bash
# Launcher for Pytune HF+ V16r2 — active development branch.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTUNE_PYTHON:-$(command -v python3)}"
REQUIRE_NATIVE="${PYTUNE_REQUIRE_NATIVE:-1}"
AUTO_BUILD_NATIVE="${PYTUNE_AUTO_BUILD_NATIVE:-1}"
NATIVE_SO="pytune_hfplus_native_fft.so"

need_build=0
if [[ ! -f "$NATIVE_SO" ]]; then
    need_build=1
else
    if [[ native/src/native_fft_module.cpp -nt "$NATIVE_SO" || native/CMakeLists.txt -nt "$NATIVE_SO" || native/build_native.sh -nt "$NATIVE_SO" ]]; then
        need_build=1
    fi
fi

if [[ "$AUTO_BUILD_NATIVE" == "1" && "$need_build" == "1" ]]; then
    echo "[pytune] Native FFT module missing/outdated. Building C++ core before launch..."
    if ! PYTUNE_PYTHON="$PYTHON_BIN" ./native/build_native.sh --core-only; then
        echo "" >&2
        echo "[pytune] ERROR: Native FFT core failed to build." >&2
        echo "[pytune] Install build dependencies, then retry:" >&2
        echo "         ./install_ubuntu_deps.sh" >&2
        echo "         ./run_pytune_hfplus_v16r2.sh" >&2
        if [[ "$REQUIRE_NATIVE" == "1" ]]; then
            exit 10
        fi
    fi
fi

if [[ "$REQUIRE_NATIVE" == "1" && ! -f "$NATIVE_SO" ]]; then
    echo "[pytune] ERROR: $NATIVE_SO is missing and native core is required." >&2
    echo "[pytune] Run: ./native/build_native.sh --core-only" >&2
    exit 11
fi

exec "$PYTHON_BIN" ./pytune_hfplus_v16r2.py "$@"
