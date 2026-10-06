#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
task_cache_dir="${AUDITFLOW_CACHE_DIR:-$PWD/.cache}"
mkdir -p "$task_cache_dir/npm" "$task_cache_dir/uv"

node -e "const [major, minor] = process.versions.node.split('.').map(Number); if (major < 22 || major === 22 && minor < 12) { throw new Error('AuditFlow requires Node 22.12+; Node 24 is recommended.'); }"
command -v uv >/dev/null || { echo 'Install uv from https://docs.astral.sh/uv/getting-started/installation/.' >&2; exit 1; }
command -v tesseract >/dev/null || { echo 'Install Tesseract OCR and the English language pack (Ubuntu: apt-get install tesseract-ocr tesseract-ocr-eng).' >&2; exit 1; }
if [[ ! -x .venv/bin/python ]]; then
  uv venv --python 3.12 --cache-dir "$task_cache_dir/uv" .venv
fi
if ! tesseract --list-langs 2>/dev/null | .venv/bin/python -c 'import sys; sys.exit("eng" not in sys.stdin.read().splitlines())'; then
  echo 'The Tesseract English language pack is required.' >&2
  exit 1
fi
uv pip sync --python .venv/bin/python --cache-dir "$task_cache_dir/uv" --require-hashes requirements.lock
npm ci --cache "$task_cache_dir/npm" --no-audit --no-fund
npm run build
# The reference benchmark always uses the key-free baseline, even if a provider
# is configured for real uploads. It is not a measurement of provider accuracy.
AUDITFLOW_AI_ENABLED=false npm run evaluate
