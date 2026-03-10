#!/usr/bin/env bash
# setup-wsl-dev.sh
#
# Run `uv sync` in WSL without touching the Windows .venv.
#
# Problem: The project's default .venv is a Windows virtualenv managed by
# PowerShell. When `uv sync` runs in WSL it would overwrite that venv with a
# Linux one, breaking the Windows workflow.
#
# Solution: Set UV_PROJECT_ENVIRONMENT=.venv-linux so uv writes to a separate,
# WSL-only venv. .venv-linux is listed in .gitignore and is never committed.
#
# Usage (from the project root inside WSL):
#   ./scripts/setup-wsl-dev.sh
#
# Agents and CI running in WSL should call this script instead of bare `uv sync`.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Guard: refuse to run on Windows (outside WSL)
if [[ -z "${WSL_DISTRO_NAME:-}" && "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: This script is for WSL only. On Windows, use: uv sync" >&2
    exit 1
fi

export UV_PROJECT_ENVIRONMENT=".venv-linux"

echo "WSL dev setup: using venv at ${PROJECT_ROOT}/.venv-linux"
echo "The Windows .venv will not be touched."
echo ""

cd "$PROJECT_ROOT"
uv sync "$@"

echo ""
echo "Done. Activate with:"
echo "  source .venv-linux/bin/activate"
