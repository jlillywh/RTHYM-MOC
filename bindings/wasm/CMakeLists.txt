if(NOT DEFINED RTHYM_WASM_OUTPUT_DIR)
    set(RTHYM_WASM_OUTPUT_DIR "${CMAKE_BINARY_DIR}/wasm" CACHE PATH
        "Directory for generated rthym_moc.js / rthym_moc.wasm artifacts")
endif()

add_executable(rthym_moc_wasm
    wasm_bindings.cpp
    "${RTHYM_SOLVER_SOURCE}"
)

target_link_libraries(rthym_moc_wasm PRIVATE rthym_core)

target_compile_options(rthym_moc_wasm PRIVATE -O3)

set_target_properties(rthym_moc_wasm PROPERTIES
    SUFFIX ".js"
    OUTPUT_NAME "rthym_moc"
    RUNTIME_OUTPUT_DIRECTORY "${RTHYM_WASM_OUTPUT_DIR}"
)

target_link_options(rthym_moc_wasm PRIVATE
    "SHELL:-s WASM=1"
    "SHELL:-s ALLOW_MEMORY_GROWTH=1"
    "SHELL:-s MODULARIZE=1"
    "SHELL:-s EXPORT_NAME=createRthymMOC"
    "SHELL:-s EXPORT_ES6=0"
    "SHELL:-s ENVIRONMENT=web,worker,node"
    "SHELL:--bind"
)
