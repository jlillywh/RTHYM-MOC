add_executable(rthym_moc wasm_bindings.cpp)
target_link_libraries(rthym_moc PRIVATE rthym_core)

target_compile_options(rthym_moc PRIVATE -O3)

set_target_properties(rthym_moc PROPERTIES SUFFIX ".js")

target_link_options(rthym_moc PRIVATE
    "-s" "WASM=1"
    "-s" "ALLOW_MEMORY_GROWTH=1"
    "-s" "MODULARIZE=1"
    "-s" "EXPORT_NAME=createRthymMOC"
    "-s" "EXPORT_ES6=0"
    "-s" "ENVIRONMENT=web,worker,node"
    "--bind"
)
