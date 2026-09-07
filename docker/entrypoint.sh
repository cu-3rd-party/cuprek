#!/bin/sh
set -e

echo "[entrypoint] applying database migrations..."
alembic upgrade head

echo "[entrypoint] starting: $*"
exec "$@"
