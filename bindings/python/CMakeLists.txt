# Compile solver sources in the extension module so pybind11 LTO applies across
# bindings.cpp and moc_solver.cpp (see LP-PERF-01 perf gate).
pybind11_add_module(_rthym_moc NO_EXTRAS
    bindings.cpp
    "${RTHYM_SOLVER_SOURCE}"
)

target_link_libraries(_rthym_moc PRIVATE rthym_core)

target_compile_options(_rthym_moc PRIVATE
    $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-O3 -funroll-loops>
    $<$<CXX_COMPILER_ID:MSVC>:/O2 /EHsc>
)
if("$ENV{RTHYM_MOC_NATIVE_OPT}" STREQUAL "1")
    target_compile_options(_rthym_moc PRIVATE
        $<$<CXX_COMPILER_ID:GNU,Clang,AppleClang>:-march=native>
    )
endif()

install(TARGETS _rthym_moc DESTINATION rthym_moc)
