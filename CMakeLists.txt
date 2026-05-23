cmake_minimum_required(VERSION 3.15)

file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/rthym_moc/_version.py" RTHYM_VERSION_LINE
    REGEX "__version__ = \"[0-9]+\.[0-9]+\.[0-9]+\"")
string(REGEX REPLACE ".*\"([0-9]+\.[0-9]+\.[0-9]+)\".*" "\\1" RTHYM_PROJECT_VERSION "${RTHYM_VERSION_LINE}")

project(rthym_moc VERSION ${RTHYM_PROJECT_VERSION} LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ── Find or fetch pybind11 ────────────────────────────────────────────────────
find_package(pybind11 CONFIG QUIET)
if(NOT pybind11_FOUND)
    # Fall back to the pybind11 bundled with the Python package
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

# ── Build the extension module ────────────────────────────────────────────────
pybind11_add_module(_rthym_moc
    src/moc_solver.cpp
    src/bindings.cpp
)

target_include_directories(_rthym_moc PRIVATE src)

# Aggressive optimisation flags (release build)
target_compile_options(_rthym_moc PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang>:-O3 -march=native -ffast-math -funroll-loops>
    $<$<CXX_COMPILER_ID:MSVC>:/O2 /fp:fast>
)

# Install the extension into the Python package directory
install(TARGETS _rthym_moc DESTINATION rthym_moc)

# ── Optional: standalone CLI test executable ──────────────────────────────────
option(BUILD_TESTS "Build the standalone C++ unit-test binary" OFF)
if(BUILD_TESTS)
    add_executable(moc_test tests/test_waterhammer.cpp src/moc_solver.cpp)
    target_include_directories(moc_test PRIVATE src)
    target_compile_options(moc_test PRIVATE
        $<$<CXX_COMPILER_ID:GNU,Clang>:-O2 -Wall -Wextra>
    )
endif()
