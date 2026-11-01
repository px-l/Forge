#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then cp .env.example .env; fi
uv sync
npm --prefix forge ci
npm --prefix forge run build
uv run uvicorn runner.main:app --host 127.0.0.1 --port 8011 &
runner_pid=$!
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8010 &
app_pid=$!
trap 'kill "$runner_pid" "$app_pid" 2>/dev/null || true' EXIT INT TERM
printf 'Forge 工作台：http://127.0.0.1:8010\n'
wait "$app_pid"
