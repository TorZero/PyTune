// Pytune HF+ — native C++ FFT bridge
//
// CPython extension that takes float32/float64 PCM buffers and returns RFFT
// magnitudes as a Python list. Kept separate from the Qt widget so it can be
// built without Qt installed.
//
// Backends:
//   fftw    — uses FFTW3f when available at compile time (pkg-config fftw3f),
//             otherwise falls back to the internal radix-2 engine below.
//   kissfft — internal radix-2 path, KissFFT-compatible behaviour.
//   pfft    — same internal engine, labelled as local parallel-mode (experimental).
//             Not linked to external MPI PFFT.

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#if defined(PYTUNE_HAVE_FFTW)
#include <fftw3.h>
#endif

using cd = std::complex<double>;

static bool is_power_of_two(std::size_t n) {
    return n && ((n & (n - 1)) == 0);
}

static std::size_t floor_power_of_two(std::size_t n) {
    if (n == 0) return 0;
    std::size_t p = 1;
    while ((p << 1) > p && (p << 1) <= n) p <<= 1;
    return p;
}

static void fft_radix2(std::vector<cd> &a) {
    const std::size_t n = a.size();
    for (std::size_t i = 1, j = 0; i < n; ++i) {
        std::size_t bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) std::swap(a[i], a[j]);
    }
    for (std::size_t len = 2; len <= n; len <<= 1) {
        const double ang = -2.0 * M_PI / static_cast<double>(len);
        const cd wlen(std::cos(ang), std::sin(ang));
        for (std::size_t i = 0; i < n; i += len) {
            cd w(1.0, 0.0);
            for (std::size_t j = 0; j < len / 2; ++j) {
                const cd u = a[i + j];
                const cd v = a[i + j + len / 2] * w;
                a[i + j] = u + v;
                a[i + j + len / 2] = u - v;
                w *= wlen;
            }
        }
    }
}

static PyObject *make_magnitude_list_internal(const std::vector<double> &samples, std::size_t n) {
    std::vector<cd> a(n);
    for (std::size_t i = 0; i < n; ++i) a[i] = cd(samples[i], 0.0);
    fft_radix2(a);

    const std::size_t out_count = n / 2 + 1;
    PyObject *out = PyList_New(static_cast<Py_ssize_t>(out_count));
    if (!out) return nullptr;
    for (std::size_t i = 0; i < out_count; ++i) {
        PyList_SET_ITEM(out, static_cast<Py_ssize_t>(i), PyFloat_FromDouble(std::abs(a[i])));
    }
    return out;
}

#if defined(PYTUNE_HAVE_FFTW)
static PyObject *make_magnitude_list_fftw(const std::vector<double> &samples, std::size_t n) {
    std::vector<float> in(n, 0.0f);
    for (std::size_t i = 0; i < n; ++i) in[i] = static_cast<float>(samples[i]);

    const std::size_t out_count = n / 2 + 1;
    std::vector<fftwf_complex> outbuf(out_count);
    fftwf_plan plan = fftwf_plan_dft_r2c_1d(static_cast<int>(n), in.data(), outbuf.data(), FFTW_ESTIMATE);
    if (!plan) {
        PyErr_SetString(PyExc_RuntimeError, "fftwf_plan_dft_r2c_1d failed");
        return nullptr;
    }
    fftwf_execute(plan);
    fftwf_destroy_plan(plan);

    PyObject *out = PyList_New(static_cast<Py_ssize_t>(out_count));
    if (!out) return nullptr;
    for (std::size_t i = 0; i < out_count; ++i) {
        const double re = static_cast<double>(outbuf[i][0]);
        const double im = static_cast<double>(outbuf[i][1]);
        PyList_SET_ITEM(out, static_cast<Py_ssize_t>(i), PyFloat_FromDouble(std::sqrt(re * re + im * im)));
    }
    return out;
}
#endif

static PyObject *backend_name(PyObject *, PyObject *args) {
    const char *requested = "native";
    if (!PyArg_ParseTuple(args, "s", &requested)) return nullptr;
    std::string req(requested ? requested : "native");
    std::transform(req.begin(), req.end(), req.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });

    if (req == "fftw") {
#if defined(PYTUNE_HAVE_FFTW)
        return PyUnicode_FromString("Native FFTW3f C++ backend");
#else
        return PyUnicode_FromString("Native C++ FFT backend (FFTW-compatible fallback; libfftw3f not linked)");
#endif
    }
    if (req == "kissfft") return PyUnicode_FromString("Native KissFFT-compatible C++ radix-2 backend");
    if (req == "pfft") return PyUnicode_FromString("Native Parallel FFT/PFFT-mode C++ backend");
    return PyUnicode_FromString("Native C++ radix-2 FFT backend");
}

static PyObject *engine_info(PyObject *, PyObject *) {
    PyObject *d = PyDict_New();
    if (!d) return nullptr;
    PyDict_SetItemString(d, "module", PyUnicode_FromString("pytune_hfplus_native_fft"));
    PyDict_SetItemString(d, "cpp_standard", PyUnicode_FromString("C++17"));
#if defined(PYTUNE_HAVE_FFTW)
    PyObject *fftw_enabled = PyBool_FromLong(1);
#else
    PyObject *fftw_enabled = PyBool_FromLong(0);
#endif
    PyDict_SetItemString(d, "fftw3f", fftw_enabled);
    Py_DECREF(fftw_enabled);
    PyObject *kiss_enabled = PyBool_FromLong(1);
    PyDict_SetItemString(d, "kissfft_compatible", kiss_enabled);
    Py_DECREF(kiss_enabled);
    PyDict_SetItemString(d, "pfft_mode", PyUnicode_FromString("local native parallel-mode placeholder; no external MPI PFFT linked"));
    return d;
}

static PyObject *rfft_magnitude(PyObject *, PyObject *args) {
    PyObject *input = nullptr;
    const char *backend_c = "native";
    if (!PyArg_ParseTuple(args, "Os", &input, &backend_c)) return nullptr;
    std::string backend(backend_c ? backend_c : "native");
    std::transform(backend.begin(), backend.end(), backend.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });

    Py_buffer view{};
    if (PyObject_GetBuffer(input, &view, PyBUF_CONTIG_RO) != 0) {
        PyErr_SetString(PyExc_TypeError, "expected a contiguous float32/float64 buffer");
        return nullptr;
    }

    std::size_t count = 0;
    std::vector<double> samples;
    if (view.itemsize == 4) {
        count = static_cast<std::size_t>(view.len / 4);
        const float *ptr = static_cast<const float *>(view.buf);
        samples.reserve(count);
        for (std::size_t i = 0; i < count; ++i) samples.push_back(static_cast<double>(ptr[i]));
    } else if (view.itemsize == 8) {
        count = static_cast<std::size_t>(view.len / 8);
        const double *ptr = static_cast<const double *>(view.buf);
        samples.assign(ptr, ptr + count);
    } else {
        PyBuffer_Release(&view);
        PyErr_SetString(PyExc_TypeError, "buffer itemsize must be float32 or float64");
        return nullptr;
    }
    PyBuffer_Release(&view);

    if (count == 0) return PyList_New(0);
    std::size_t n = is_power_of_two(count) ? count : floor_power_of_two(count);
    if (n < 2) return PyList_New(0);

#if defined(PYTUNE_HAVE_FFTW)
    if (backend == "fftw") return make_magnitude_list_fftw(samples, n);
#endif
    return make_magnitude_list_internal(samples, n);
}

static PyObject *self_test(PyObject *, PyObject *) {
    const std::size_t n = 1024;
    std::vector<double> samples(n);
    for (std::size_t i = 0; i < n; ++i) {
        samples[i] = std::sin(2.0 * M_PI * 8.0 * static_cast<double>(i) / static_cast<double>(n));
    }
    PyObject *result = make_magnitude_list_internal(samples, n);
    if (!result) return nullptr;
    Py_ssize_t len = PyList_Size(result);
    if (len <= 8) {
        Py_DECREF(result);
        Py_RETURN_FALSE;
    }
    double bin8 = PyFloat_AsDouble(PyList_GetItem(result, 8));
    Py_DECREF(result);
    if (bin8 > 0.20) Py_RETURN_TRUE;
    Py_RETURN_FALSE;
}

static PyMethodDef Methods[] = {
    {"backend_name", backend_name, METH_VARARGS, "Return native backend label for requested backend."},
    {"engine_info", engine_info, METH_NOARGS, "Return native engine build details."},
    {"rfft_magnitude", rfft_magnitude, METH_VARARGS, "Return RFFT magnitudes for a float buffer."},
    {"self_test", self_test, METH_NOARGS, "Run a native FFT smoke test."},
    {nullptr, nullptr, 0, nullptr}
};

static struct PyModuleDef Module = {
    PyModuleDef_HEAD_INIT,
    "pytune_hfplus_native_fft",
    "Pytune HF+ native C++ FFT bridge",
    -1,
    Methods
};

PyMODINIT_FUNC PyInit_pytune_hfplus_native_fft(void) {
    return PyModule_Create(&Module);
}
