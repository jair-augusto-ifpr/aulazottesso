FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DJANGO_SETTINGS_MODULE=chatifpr.settings
ENV DEBUG=False
# O banco real entra só no Cloud Run. Este valor existe para o collectstatic
# conseguir importar settings durante o build.
RUN DATABASE_URL=postgresql://build:build@127.0.0.1:5432/build \
    python manage.py collectstatic --noinput

RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
