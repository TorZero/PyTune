# Shiboken/PySide6 binding scaffold

The V5 runtime can optionally import when PYTUNE_USE_NATIVE_WIDGET=1:

```python
import pytune_hfplus_native
widget = pytune_hfplus_native.FFTSpectrumWidget(parent)
```

This folder contains the minimal type-system metadata for generating that binding.
The native Qt widget implementation is already in:

```text
native/include/FFTSpectrumWidget.h
native/src/FFTSpectrumWidget.cpp
```

Recommended route for the next build pass:

1. Use the same PySide6 version as the Python runtime.
2. Locate PySide6/Shiboken include folders from `python3 -m pip show PySide6 shiboken6`.
3. Generate wrappers with `shiboken6` using `typesystem_pytune_hfplus_native.xml`.
4. Build a CPython extension named `pytune_hfplus_native` linked against Qt6 Widgets and the generated Shiboken wrappers.

The app is intentionally safe before this binding exists: it falls back to the Python Qt analyzer panel, while `native/build_native.sh` already builds the C++ widget library and the separate native FFT bridge.
