#!/usr/bin/env bash
set -euo pipefail

STUDY_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FORGE_BIN="${FORGE_BIN:-forge}"

(cd "$STUDY_DIR/v4-core" && "$FORGE_BIN" build src/PoolManager.sol --offline)
(cd "$STUDY_DIR/quote-harness" && "$FORGE_BIN" test --offline -vv)
