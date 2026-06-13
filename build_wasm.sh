#!/usr/bin/env bash
# Backward-compatible entry point; implementation lives in bindings/wasm/.
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/bindings/wasm/build_wasm.sh" "$@"
