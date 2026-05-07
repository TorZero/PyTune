cmake_minimum_required(VERSION 3.20)
project(pytune_hfplus_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

option(PYTUNE_BUILD_QT_WIDGET "Build the native Qt FFTSpectrumWidget library" ON)
option(PYTUNE_BUILD_NATIVE_FFT "Build the CPython native FFT analyzer module" ON)
option(PYTUNE_WITH_FFTW "Enable native FFTW3f if available" ON)
option(PYTUNE_WITH_KISSFFT "Enable bundled KissFFT-compatible native mode" ON)
option(PYTUNE_WITH_PFFT "Enable local native PFFT-mode label/path" ON)

if(PYTUNE_BUILD_QT_WIDGET)
    set(CMAKE_AUTOMOC ON)
    find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets)
    add_library(pytune_hfplus_widget STATIC
        src/FFTSpectrumWidget.cpp
        include/FFTSpectrumWidget.h
    )
    target_include_directories(pytune_hfplus_widget PUBLIC include)
    target_link_libraries(pytune_hfplus_widget PUBLIC Qt6::Core Qt6::Gui Qt6::Widgets)
endif()

if(PYTUNE_BUILD_NATIVE_FFT)
    find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module)
    Python3_add_library(pytune_hfplus_native_fft MODULE src/native_fft_module.cpp)
    target_compile_definitions(pytune_hfplus_native_fft PRIVATE
        $<$<BOOL:${PYTUNE_WITH_KISSFFT}>:PYTUNE_WITH_KISSFFT>
        $<$<BOOL:${PYTUNE_WITH_PFFT}>:PYTUNE_WITH_PFFT>
    )

    if(PYTUNE_WITH_FFTW)
        find_package(PkgConfig QUIET)
        if(PkgConfig_FOUND)
            pkg_check_modules(FFTW3F QUIET fftw3f)
        endif()
        if(FFTW3F_FOUND)
            target_compile_definitions(pytune_hfplus_native_fft PRIVATE PYTUNE_HAVE_FFTW)
            target_include_directories(pytune_hfplus_native_fft PRIVATE ${FFTW3F_INCLUDE_DIRS})
            target_link_directories(pytune_hfplus_native_fft PRIVATE ${FFTW3F_LIBRARY_DIRS})
            target_link_libraries(pytune_hfplus_native_fft PRIVATE ${FFTW3F_LIBRARIES})
            message(STATUS "Native FFTW3f enabled via pkg-config")
        else()
            message(STATUS "Native FFTW3f not found; internal C++ FFT remains active")
        endif()
    endif()

    set_target_properties(pytune_hfplus_native_fft PROPERTIES
        PREFIX ""
        OUTPUT_NAME "pytune_hfplus_native_fft"
    )
endif()
