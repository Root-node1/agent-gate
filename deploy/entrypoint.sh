#!/usr/bin/env sh
set -eu

# Collect static files (idempotent; safe to run on every web start).
python manage.py collectstatic --noinput

exec "$@"
