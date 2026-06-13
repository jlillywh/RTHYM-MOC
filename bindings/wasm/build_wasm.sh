#!/usr/bin/env bash
# build_wasm.sh
# Maintainer/internal Emscripten build for WASM binding validation.
#
# Outputs (default):
#   build/wasm/rthym_moc.js
#   build/wasm/rthym_moc.wasm
#
# Environment:
#   EMSDK_DIR            Optional path to an emsdk checkout (sources emsdk_env.sh)
#   RTHYM_WASM_BUILD_DIR CMake build directory (default: build_wasm)
#   RTHYM_WASM_OUT_DIR   Artifact output directory (default: build/wasm)
#   RTHYM_WASM_COPY_DIR  Optional local-only copy target for maintainer workflows

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="${RTHYM_WASM_BUILD_DIR:-${REPO_ROOT}/build_wasm}"
OUT_DIR="${RTHYM_WASM_OUT_DIR:-${REPO_ROOT}/build/wasm}"

ensure_emscripten() {
    if command -v emcmake >/dev/null 2>&1; then
        return 0
    fi

    if [[ -z "${EMSDK_DIR:-}" && -f "${HOME}/emsdk/emsdk_env.sh" ]]; then
        EMSDK_DIR="${HOME}/emsdk"
    fi

    if [[ -n "${EMSDK_DIR:-}" && -f "${EMSDK_DIR}/emsdk_env.sh" ]]; then
        # shellcheck source=/dev/null
        source "${EMSDK_DIR}/emsdk_env.sh"
    fi

    if command -v emcmake >/dev/null 2>&1; then
        return 0
    fi

    cat >&2 <<'EOF'
error: emcmake not found.

Install Emscripten and ensure emcmake is on PATH, or set EMSDK_DIR to an emsdk
checkout before running this script:

  export EMSDK_DIR=/path/to/emsdk
  source "$EMSDK_DIR/emsdk_env.sh"
  bash build_wasm.sh

See: https://emscripten.org/docs/getting_started/downloads.html
EOF
    exit 1
}

ensure_emscripten
mkdir -p "${OUT_DIR}"

echo "Configuring RTHYM-MOC WebAssembly build via emcmake..."
emcmake cmake -S "${REPO_ROOT}" -B "${BUILD_DIR}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DRTHYM_WASM_OUTPUT_DIR="${OUT_DIR}"

echo "Building rthym_moc_wasm..."
cmake --build "${BUILD_DIR}" --target rthym_moc_wasm -j

if [[ -n "${RTHYM_WASM_COPY_DIR:-}" ]]; then
    mkdir -p "${RTHYM_WASM_COPY_DIR}"
    cp "${OUT_DIR}/rthym_moc.js" "${OUT_DIR}/rthym_moc.wasm" "${RTHYM_WASM_COPY_DIR}/"
    echo "Copied artifacts to ${RTHYM_WASM_COPY_DIR}"
fi

echo "WASM build complete:"
echo "  ${OUT_DIR}/rthym_moc.js"
echo "  ${OUT_DIR}/rthym_moc.wasm"
