#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTUNE_PYTHON:-$(command -v python3)}"
MODE="all"
CLEAN=0
EXTRA_CMAKE_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --core-only|--core)
            MODE="core"
            shift
            ;;
        --all)
            MODE="all"
            shift
            ;;
        --clean)
            CLEAN=1
            shift
            ;;
        --help|-h)
            cat <<'EOF'
Usage: ./build_native.sh [--core-only|--all] [--clean] [extra cmake args]

Builds the required Pytune HF+ native FFT CPython module directly with g++/c++.
The result is copied next to the Python app as pytune_hfplus_native_fft.so.

--core-only  Build only the native FFT engine. This is the required runtime core.
--all        Build native FFT engine and attempt the optional Qt widget library.
--clean      Remove old native build folders/modules first.
EOF
            exit 0
            ;;
        *)
            EXTRA_CMAKE_ARGS+=("$1")
            shift
            ;;
    esac
done

if [[ $CLEAN -eq 1 ]]; then
    rm -rf build_core build_widget build
    rm -f ../pytune_hfplus_native_fft*.so
fi

CXX_BIN="${CXX:-}"
if [[ -z "$CXX_BIN" ]]; then
    if command -v c++ >/dev/null 2>&1; then
        CXX_BIN="$(command -v c++)"
    elif command -v g++ >/dev/null 2>&1; then
        CXX_BIN="$(command -v g++)"
    else
        echo "ERROR: C++ compiler is missing. Install: sudo apt install build-essential" >&2
        exit 2
    fi
fi

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import sysconfig
raise SystemExit(0 if sysconfig.get_paths().get('include') else 1)
PY
then
    echo "ERROR: Python development headers are missing. Install: sudo apt install python3-dev" >&2
    exit 2
fi

PY_INCLUDE="$($PYTHON_BIN - <<'PY'
import sysconfig
print(sysconfig.get_paths()['include'])
PY
)"
PY_PLAT_INCLUDE="$($PYTHON_BIN - <<'PY'
import sysconfig
print(sysconfig.get_paths().get('platinclude') or sysconfig.get_paths()['include'])
PY
)"

FFTW_CFLAGS=""
FFTW_LIBS=""
if command -v pkg-config >/dev/null 2>&1 && pkg-config --exists fftw3f; then
    FFTW_CFLAGS="$(pkg-config --cflags fftw3f) -DPYTUNE_HAVE_FFTW"
    FFTW_LIBS="$(pkg-config --libs fftw3f)"
    echo "[native] FFTW3f detected and enabled."
else
    echo "[native] FFTW3f not found. Internal native C++ FFT remains active."
fi

mkdir -p build_core
set -x
"$CXX_BIN" -O3 -DNDEBUG -std=c++17 -fPIC -shared \
    -I"$PY_INCLUDE" -I"$PY_PLAT_INCLUDE" \
    $FFTW_CFLAGS \
    src/native_fft_module.cpp \
    -o build_core/pytune_hfplus_native_fft.so \
    $FFTW_LIBS -lm
set +x
cp -v build_core/pytune_hfplus_native_fft.so ../pytune_hfplus_native_fft.so

PYTHONPATH="..:${PYTHONPATH:-}" "$PYTHON_BIN" - <<'PY'
import importlib
m = importlib.import_module('pytune_hfplus_native_fft')
print('[native] loaded:', m.backend_name('kissfft'))
print('[native] info:', m.engine_info() if hasattr(m, 'engine_info') else 'no engine_info')
if hasattr(m, 'self_test') and not m.self_test():
    raise SystemExit('native self_test failed')
print('[native] self-test: OK')
PY

if [[ "$MODE" == "all" ]]; then
    echo "[native] Attempting optional Qt FFTSpectrumWidget CMake build..."
    if ! command -v cmake >/dev/null 2>&1; then
        echo "[native] Optional Qt widget skipped: cmake not installed." >&2
    else
        set +e
        cmake -S . -B build_widget \
            -DCMAKE_BUILD_TYPE=Release \
            -DPYTUNE_BUILD_QT_WIDGET=ON \
            -DPYTUNE_BUILD_NATIVE_FFT=OFF \
            -DPython3_EXECUTABLE="$PYTHON_BIN" \
            "${EXTRA_CMAKE_ARGS[@]}"
        CFG_STATUS=$?
        if [[ $CFG_STATUS -eq 0 ]]; then
            cmake --build build_widget -j"$(nproc)"
            WIDGET_STATUS=$?
        else
            WIDGET_STATUS=$CFG_STATUS
        fi
        set -e
        if [[ $WIDGET_STATUS -ne 0 ]]; then
            echo "[native] Optional Qt widget skipped. Install Qt6 dev packages to build it:" >&2
            echo "         sudo apt install qt6-base-dev qt6-base-dev-tools" >&2
        else
            echo "[native] Optional Qt widget build completed."
        fi
    fi
fi

echo "[native] Native FFT core is ready."
