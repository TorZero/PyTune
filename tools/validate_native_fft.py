#!/usr/bin/env python3
"""Validate Pytune HF+ native FFT module import, smoke-test, and basic timing."""
from __future__ import annotations

import importlib
import math
import time

try:
    import numpy as np
except Exception as exc:
    raise SystemExit(f"NumPy is required for validation: {exc}")

native = importlib.import_module("pytune_hfplus_native_fft")
print("backend kissfft:", native.backend_name("kissfft"))
print("backend fftw:", native.backend_name("fftw"))
print("backend pfft:", native.backend_name("pfft"))
if hasattr(native, "engine_info"):
    print("engine_info:", native.engine_info())
if hasattr(native, "self_test"):
    print("self_test:", native.self_test())

n = 4096
sr = 44100.0
freq = 1000.0
x = np.sin(2.0 * math.pi * freq * np.arange(n, dtype=np.float32) / sr).astype(np.float32)

# Warm up
native.rfft_magnitude(x, "kissfft")

loops = 120
t0 = time.perf_counter()
for _ in range(loops):
    y = native.rfft_magnitude(x, "kissfft")
t1 = time.perf_counter()
print(f"native kissfft-compatible: {(t1-t0)*1000/loops:.3f} ms/frame, bins={len(y)}")

t0 = time.perf_counter()
for _ in range(loops):
    z = np.abs(np.fft.rfft(x)) / n
t1 = time.perf_counter()
print(f"numpy rfft:              {(t1-t0)*1000/loops:.3f} ms/frame, bins={len(z)}")
