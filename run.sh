#!/usr/bin/env bash
# TR-1: localhost only — never bind 0.0.0.0.
set -e
cd "$(dirname "$0")/backend"
# Invoke the venv's interpreter directly rather than `source .venv/bin/activate` —
# that script hardcodes an absolute path baked in at venv-creation time, which
# breaks silently (falls back to system Python) if this project folder is ever
# renamed or moved.
exec .venv/bin/python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
