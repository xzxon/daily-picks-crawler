#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
ENV_FILE="${HERMES_HOME:-/opt/data}/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "缺少 Hermes 环境文件: $ENV_FILE" >&2
  exit 1
fi

cd "$PROJECT_DIR"
# Use the project venv for dependencies; Python code loads the same canonical env file.
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="/usr/bin/python3"
fi
exec "$PYTHON_BIN" daily_run.py "$@"
