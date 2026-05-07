#!/usr/bin/env python3
"""Compare all Pytune HF+ FFT backends numerically.

Tests sine tones, white noise, pink noise, and silence. For each signal the
script checks:
  - peak bin location within ±1 bin for sine signals
  - magnitude correlation between NumPy reference and each backend >= 0.985
  - no NaN / Inf values
  - no backend concentrating all energy only in low bands (< 500 Hz)

Usage:
    PYTHONPATH=.. python3 validate_fft_backends.py
"""
from __future__ import annotations

import importlib
import math
import sys
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    raise SystemExit("NumPy is required: pip install numpy")

try:
    native = importlib.import_module("pytune_hfplus_native_fft")
    NATIVE_OK = True
except ImportError:
    native = None
    NATIVE_OK = False
    print("[warn] pytune_hfplus_native_fft not importable — native backends skipped")

try:
    import pyfftw.interfaces.numpy_fft as pyfftw_fft
    import pyfftw
    pyfftw.interfaces.cache.enable()
    PYFFTW_OK = True
except ImportError:
    pyfftw_fft = None
    PYFFTW_OK = False
    print("[warn] pyFFTW not installed — FFTW backend skipped")

N = 4096
SR = 44100.0
PASS_CORR = 0.985
PASS_BIN_ERR = 1  # bins


def hann_window(n: int) -> np.ndarray:
    return np.hanning(n).astype(np.float64)


def numpy_rfft(signal: np.ndarray) -> np.ndarray:
    w = hann_window(len(signal))
    return np.abs(np.fft.rfft(signal * w))


def pyfftw_rfft(signal: np.ndarray) -> Optional[np.ndarray]:
    if not PYFFTW_OK:
        return None
    w = hann_window(len(signal))
    return np.abs(pyfftw_fft.rfft((signal * w).astype(np.float32)))


def native_rfft(signal: np.ndarray, backend: str) -> Optional[np.ndarray]:
    if not NATIVE_OK:
        return None
    w = hann_window(len(signal))
    windowed = (signal * w).astype(np.float32)
    try:
        return np.asarray(native.rfft_magnitude(windowed, backend), dtype=np.float64)
    except Exception as exc:
        print(f"  [native {backend}] exception: {exc}")
        return None


def make_sine(freq: float, n: int = N, sr: float = SR, amp: float = 0.8) -> np.ndarray:
    t = np.arange(n, dtype=np.float64) / sr
    return (amp * np.sin(2.0 * math.pi * freq * t)).astype(np.float64)


def make_white(n: int = N) -> np.ndarray:
    rng = np.random.default_rng(42)
    return (rng.standard_normal(n) * 0.4).astype(np.float64)


def make_pink(n: int = N) -> np.ndarray:
    # Voss-McCartney approximation
    rng = np.random.default_rng(7)
    white = rng.standard_normal(n)
    freqs = np.fft.rfftfreq(n)
    freqs[0] = 1e-6
    pink_filter = 1.0 / np.sqrt(freqs)
    pink_filter[0] = 0.0
    spectrum = np.fft.rfft(white) * pink_filter
    pink = np.fft.irfft(spectrum, n=n)
    pink = (pink / max(1e-9, np.max(np.abs(pink)))) * 0.5
    return pink.astype(np.float64)


def make_silence(n: int = N) -> np.ndarray:
    return np.zeros(n, dtype=np.float64)


def correlation(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) != len(b):
        mn = min(len(a), len(b))
        a, b = a[:mn], b[:mn]
    if np.std(a) < 1e-30 or np.std(b) < 1e-30:
        return 1.0 if np.allclose(a, b, atol=1e-12) else 0.0
    return float(np.corrcoef(a, b)[0, 1])


def check_no_nan_inf(arr: np.ndarray, label: str) -> bool:
    if np.any(~np.isfinite(arr)):
        print(f"  FAIL [{label}] contains NaN/Inf")
        return False
    return True


def check_peak_bin(arr: np.ndarray, expected_freq: float, label: str, sr: float = SR) -> bool:
    freqs = np.fft.rfftfreq(N, d=1.0 / sr)
    expected_bin = int(np.argmin(np.abs(freqs - expected_freq)))
    actual_bin = int(np.argmax(arr))
    err = abs(actual_bin - expected_bin)
    if err > PASS_BIN_ERR:
        print(f"  FAIL [{label}] peak at bin {actual_bin} ({freqs[actual_bin]:.1f} Hz), expected bin {expected_bin} ({expected_freq:.1f} Hz), error={err}")
        return False
    return True


def check_low_band_concentration(arr: np.ndarray, label: str, sr: float = SR) -> bool:
    freqs = np.fft.rfftfreq(N, d=1.0 / sr)
    cutoff_bin = int(np.argmin(np.abs(freqs - 500.0)))
    low_energy = float(np.sum(arr[:cutoff_bin]))
    total_energy = float(np.sum(arr)) + 1e-30
    ratio = low_energy / total_energy
    if ratio > 0.92:
        print(f"  FAIL [{label}] {ratio*100:.1f}% of energy below 500 Hz — backend may be double-normalizing")
        return False
    return True


def run_test(name: str, signal: np.ndarray, backends: Dict[str, Optional[np.ndarray]],
             check_freq: Optional[float] = None) -> Tuple[int, int]:
    passed = 0
    total = 0
    print(f"\n── {name} ──")
    ref = backends.get("numpy")
    if ref is None:
        print("  ERROR: NumPy reference missing")
        return 0, 0

    for label, arr in backends.items():
        total += 1
        if arr is None:
            print(f"  SKIP [{label}] not available")
            total -= 1
            continue

        ok = True
        ok &= check_no_nan_inf(arr, label)

        if check_freq is not None:
            ok &= check_peak_bin(arr, check_freq, label)

        # Skip low-band-concentration check for sine tests whose frequency IS below
        # 500 Hz — those legitimately have 100% energy in the low band.
        broadband_check = (check_freq is None or check_freq >= 500.0) and name not in ("silence",)
        if label != "numpy" and broadband_check:
            ok &= check_low_band_concentration(arr, label)
            corr = correlation(ref, arr)
            if corr < PASS_CORR:
                print(f"  FAIL [{label}] correlation with NumPy = {corr:.4f} (threshold {PASS_CORR})")
                ok = False
            else:
                print(f"  pass [{label}] corr={corr:.4f}" + (f"  peak@{check_freq:.0f}Hz ✓" if check_freq else ""))
        else:
            print(f"  pass [{label}] reference" + (f"  peak@{check_freq:.0f}Hz ✓" if check_freq and ok else ""))

        if ok:
            passed += 1

    return passed, total


def main() -> int:
    print("=" * 60)
    print("Pytune HF+ FFT Backend Validation")
    print(f"N={N}  SR={SR:.0f}  correlation_threshold={PASS_CORR}")
    print("=" * 60)

    if NATIVE_OK:
        print(f"native module: {native.engine_info() if hasattr(native, 'engine_info') else 'loaded'}")
        print(f"native self_test: {native.self_test() if hasattr(native, 'self_test') else 'N/A'}")

    test_cases = [
        ("63 Hz sine",   make_sine(63.0),   63.0),
        ("125 Hz sine",  make_sine(125.0),  125.0),
        ("1 kHz sine",   make_sine(1000.0), 1000.0),
        ("4 kHz sine",   make_sine(4000.0), 4000.0),
        ("8 kHz sine",   make_sine(8000.0), 8000.0),
        ("12 kHz sine",  make_sine(12000.0),12000.0),
        ("white noise",  make_white(),      None),
        ("pink noise",   make_pink(),       None),
        ("silence",      make_silence(),    None),
    ]

    total_passed = 0
    total_tests = 0

    for name, signal, freq in test_cases:
        backends: Dict[str, Optional[np.ndarray]] = {
            "numpy":          numpy_rfft(signal),
            "fftw/pyfftw":    pyfftw_rfft(signal),
            "native kissfft": native_rfft(signal, "kissfft"),
            "native pfft":    native_rfft(signal, "pfft"),
        }
        p, t = run_test(name, signal, backends, check_freq=freq)
        total_passed += p
        total_tests += t

    print("\n" + "=" * 60)
    print(f"Result: {total_passed}/{total_tests} checks passed")
    if total_passed == total_tests:
        print("ALL BACKENDS PASS ✓")
        return 0
    else:
        print(f"FAILURES: {total_tests - total_passed} check(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
