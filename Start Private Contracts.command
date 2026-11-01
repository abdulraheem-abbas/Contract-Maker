#!/bin/zsh
set -eu
TASK_APP_DIR="${0:A:h}"
if [[ -d "$TASK_APP_DIR/Private Contracts.app" ]]; then
  /usr/bin/open "$TASK_APP_DIR/Private Contracts.app"
else
  exec "$TASK_APP_DIR/.venv/bin/python" "$TASK_APP_DIR/run.py"
fi
