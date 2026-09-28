#!/bin/sh
set -e
python manage.py migrate --noinput
python manage.py seed
# Uma instância atende várias conversas ao mesmo tempo.
# O chat fica bloqueado na API do Gemini (E/S), então threads bastam.
# timeout 0: o limite de duração fica no Cloud Run (180s), não nos 30s padrão do Gunicorn.
exec gunicorn chatifpr.wsgi:application \
  --bind "0.0.0.0:${PORT:-8080}" \
  --workers "${WEB_CONCURRENCY:-1}" \
  --threads "${GUNICORN_THREADS:-30}" \
  --timeout 0 \
  --graceful-timeout 30 \
  --keep-alive 5
