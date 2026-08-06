#!/bin/sh
set -e
python manage.py migrate --noinput
exec gunicorn pw26.wsgi:application --bind "0.0.0.0:${PORT:-8080}"
