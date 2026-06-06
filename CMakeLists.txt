cmake_minimum_required(VERSION 3.15)

file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/rthym_moc/_version.py" RTHYM_VERSION_LINE
    REGEX "__version__ = \"[0-9]+\.[0-9]+\.[0-9]+\"")
string(REGEX REPLACE ".*\"([0-9]+\.[0-9]+\.[0-9]+)\".*" "\\1" RTHYM_PROJECT_VERSION "${RTHYM_VERSION_LINE}")

project(rthym_moc VERSION ${RTHYM_PROJECT_VERSION} LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ── Pure C++17 solver core (no pybind11, no Emscripten) ───────────────────────
add_library(rthym_core STATIC src/solver/moc_solver.cpp)
set_target_properties(rthym_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(rthym_core PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/src/solver"
)

target_compile_options(rthym_core PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-O3 -funroll-loops>
    $<$<CXX_COMPILER_ID:MSVC>:/O2 /EHsc>
)
if("$ENV{RTHYM_MOC_NATIVE_OPT}" STREQUAL "1")
    target_compile_options(rthym_core PRIVATE
        $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-march=native>
    )
endif()

# ── Binding layers (mutually exclusive toolchains) ────────────────────────────
if(EMSCRIPTEN)
    add_subdirectory(bindings/wasm)
else()
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

# ── Optional: standalone CLI test executable ──────────────────────────────────
option(BUILD_TESTS "Build the standalone C++ unit-test binary" OFF)
if(BUILD_TESTS)
    add_executable(moc_test tests/test_waterhammer.cpp)
    target_link_libraries(moc_test PRIVATE rthym_core)
    target_compile_options(moc_test PRIVATE
        $<$<CXX_COMPILER_ID:GNU,Clang>:-O2 -Wall -Wextra>
    )
endif()
