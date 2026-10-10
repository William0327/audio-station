#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'ERROR: Python 3.10+ is required. On Ubuntu: sudo apt install python3' >&2
  exit 1
fi
exec python3 scripts/install.py "$@"
