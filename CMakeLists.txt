cmake_minimum_required(VERSION 3.15)

file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/rthym_moc/_version.py" RTHYM_VERSION_LINE
    REGEX "__version__ = \"[0-9]+\.[0-9]+\.[0-9]+\"")
string(REGEX REPLACE ".*\"([0-9]+\.[0-9]+\.[0-9]+)\".*" "\\1" RTHYM_PROJECT_VERSION "${RTHYM_VERSION_LINE}")

project(rthym_moc VERSION ${RTHYM_PROJECT_VERSION} LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(RTHYM_SOLVER_DIR "${CMAKE_CURRENT_SOURCE_DIR}/src/solver")
set(RTHYM_SOLVER_SOURCE "${RTHYM_SOLVER_DIR}/moc_solver.cpp")

# Shared compile settings for the pure C++17 solver core.
add_library(rthym_core INTERFACE)
target_include_directories(rthym_core INTERFACE "${RTHYM_SOLVER_DIR}")
target_compile_options(rthym_core INTERFACE
    $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-O3 -funroll-loops>
    $<$<CXX_COMPILER_ID:MSVC>:/O2 /EHsc>
)
if("$ENV{RTHYM_MOC_NATIVE_OPT}" STREQUAL "1")
    target_compile_options(rthym_core INTERFACE
        $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-march=native>
    )
endif()

option(RTHYM_BUILD_PYTHON "Build the pybind11 Python extension module" ON)
option(BUILD_TESTS "Build native C++ core tests (Doctest + CTest)" OFF)

# ── Binding layers (mutually exclusive toolchains) ────────────────────────────
if(EMSCRIPTEN)
    add_subdirectory(bindings/wasm)
elseif(RTHYM_BUILD_PYTHON)
    find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)

    find_package(pybind11 CONFIG QUIET)
    if(NOT pybind11_FOUND)
        execute_process(
            COMMAND "${Python_EXECUTABLE}" -c "import pybind11; print(pybind11.get_cmake_dir())"
            OUTPUT_VARIABLE _pb11_cmake_dir
            OUTPUT_STRIP_TRAILING_WHITESPACE
            RESULT_VARIABLE _pb11_result
        )
        if(_pb11_result EQUAL 0 AND EXISTS "${_pb11_cmake_dir}")
            set(pybind11_DIR "${_pb11_cmake_dir}")
            find_package(pybind11 CONFIG REQUIRED)
        else()
            message(FATAL_ERROR "pybind11 not found. Install via: pip install pybind11")
        endif()
    endif()

    add_subdirectory(bindings/python)
endif()

# ── Native C++ core tests (no Python, no Emscripten) ──────────────────────────
if(BUILD_TESTS AND NOT EMSCRIPTEN)
    enable_testing()
    add_subdirectory(tests/cpp)
endif()
