#!/bin/bash
# build_wasm.sh
# Portably build WASM target from C++ source code.
# Installs Emscripten SDK locally under /home/jason/emsdk if not found on PATH.

set -e

EMSDK_DIR="/home/jason/emsdk"

# Check if emcc is on path
if command -v emcc >/dev/null 2>&1; then
    echo "Found emcc in environment."
else
    if [ ! -d "$EMSDK_DIR" ]; then
        echo "Emscripten SDK not found. Installing into $EMSDK_DIR..."
        git clone https://github.com/emscripten-core/emsdk.git "$EMSDK_DIR"
        cd "$EMSDK_DIR"
        ./emsdk install latest
        ./emsdk activate latest
        cd -
    fi
    echo "Sourcing emsdk environment..."
    source "$EMSDK_DIR/emsdk_env.sh"
fi

cd /home/jason/RTHYM-MOC

echo "Compiling RTHYM-MOC to WebAssembly..."
emcc -O3 -std=c++17 \
     -I./src \
     -DEMSCRIPTEN \
     src/moc_solver.cpp \
     src/wasm_bindings.cpp \
     -o src/rthym_moc.js \
     -s WASM=1 \
     -s ALLOW_MEMORY_GROWTH=1 \
     -s MODULARIZE=1 \
     -s EXPORT_NAME="createRthymMOC" \
     -s ENVIRONMENT="web,worker,node" \
     --bind

echo "Copying compiled output to web app directory..."
TARGET_DIR="/home/jason/Lillywhite_Consulting/lillywhite_web/digital_twin/static/digital_twin/js/simulation"
mkdir -p "$TARGET_DIR"
cp src/rthym_moc.js "$TARGET_DIR/"
cp src/rthym_moc.wasm "$TARGET_DIR/"

echo "WASM compilation and copy complete!"
