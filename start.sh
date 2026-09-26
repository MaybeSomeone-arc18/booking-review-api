#!/bin/sh
# Render start command: migrate, seed, run the queue worker in-process, serve.
# Render's free tier has no background-worker service type, so the worker runs
# as a background process next to uvicorn; locally, compose keeps them separate.
set -e
alembic upgrade head
python -m app.seed
python worker.py &
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
