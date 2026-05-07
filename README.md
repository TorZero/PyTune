# Pytune HF+ V16r2

Professional Linux desktop audio player with real-time FFT spectrum analyzer.

- **mpv/libmpv** playback backend
- **Native C++ FFT** engine (KissFFT-compatible radix-2, optional FFTW3f)
- **21 spectrum visual modes** including Waterfall Cinema, Segmented LED, DAW Analyzer, and more
- **PySide6 / Qt6** UI — dark themed, keyboard shortcut driven
- **Playlist**: local files + streaming URLs, Save/Load JSON playlists, drag-and-drop
- Stream reconnect with automatic retry (up to 5 attempts, backoff)

---

## Quick install (Ubuntu / Debian)

```bash
git clone <repo-url> pytune_hfplus
cd pytune_hfplus
./install.sh
```

`install.sh` handles everything: system packages, Python deps, native FFT build, and optional desktop shortcut.

---

## Manual install

### 1 — System packages
```bash
./install_ubuntu_deps.sh
```
Installs: `mpv libmpv2 ffmpeg python3-dev build-essential cmake libfftw3-dev`

### 2 — Python dependencies
```bash
pip install -r requirements.txt
```

### 3 — Build native FFT core
```bash
cd native && ./build_native.sh --core-only
```
Outputs `pytune_hfplus_native_fft.so` next to the Python app.  
Requires only `g++` and Python headers — no cmake needed for `--core-only`.

### 4 — Launch
```bash
./run_pytune_hfplus_v16r2.sh
```

The launcher auto-rebuilds the native `.so` if it is missing or older than the source.

---

## FFT backends

| UI selector | Runtime path |
|---|---|
| Auto Native C++ | Native C++ module first, then pyFFTW, then NumPy |
| NumPy rFFT | Python NumPy — always available |
| FFTW | pyFFTW first; native C++ FFTW3f if linked; NumPy fallback |
| KissFFT-compatible | Native C++ radix-2 |
| Native Parallel (local C++ experimental) | Same native radix-2 path, labelled experimental |

All backends return raw linear FFT magnitudes. Display normalization is applied once in Python.

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| Space | Play / Resume |
| M | Mute toggle |
| +  / - | Volume +5 / -5 |
| F / F11 | Fullscreen toggle |
| R | Repeat All toggle |
| S | Shuffle toggle |
| Delete | Remove selected playlist tracks |
| Left / Right arrow | Seek -5 / +5 seconds |

Click the elapsed time label to toggle remaining time display.

---

## Playlist JSON format

Save/Load playlists are plain JSON. You can hand-edit them:

```json
{
  "pytune_playlist_version": 1,
  "created": "2026-05-07T12:00:00",
  "tracks": [
    { "source": "/home/user/music/track.flac", "title": "Track Name", "kind": "file", "duration": 210.5 },
    { "source": "https://stream.example.com/live", "title": "Radio Name", "kind": "stream", "duration": null }
  ]
}
```

---

## Validate native FFT module

```bash
python3 -m py_compile pytune_hfplus_v16r2.py && echo "syntax OK"
cd native && ./build_native.sh --core-only --clean
PYTHONPATH=. python3 tools/validate_native_fft.py
PYTHONPATH=. python3 tools/validate_fft_backends.py
```

---

## Structure

```
pytune_hfplus_v16r2.py       active development version
pytune_hfplus_v15r1.py       locked baseline (do not modify)
run_pytune_hfplus_v16r2.sh   launcher
install.sh                   one-command installer
requirements.txt             Python dependencies

native/
  build_native.sh            C++ build script (--core-only or --all)
  src/native_fft_module.cpp  CPython FFT extension
  CMakeLists.txt             optional Qt widget build

tools/
  validate_native_fft.py     smoke-test the native module
  validate_fft_backends.py   compare all backends numerically
```

---

## License

MIT — see [LICENSE](LICENSE).
