#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[check] Compiling Python sources..."
python3 -m compileall -q zegar.py zegar_app tests

echo "[check] Running hardware-independent tests..."
python3 -m unittest discover -s tests -v

echo "[check] All checks passed."
