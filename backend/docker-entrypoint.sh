#!/bin/sh
# Apply migrations, create categories + demo data (idempotent), then serve with gunicorn.
set -e
flask db upgrade
if [ "${SEED_DEMO:-true}" = "true" ]; then
  flask seed
fi
exec gunicorn --bind 0.0.0.0:5000 --workers "${GUNICORN_WORKERS:-2}" --timeout 120 \
  --access-logfile - run:app
