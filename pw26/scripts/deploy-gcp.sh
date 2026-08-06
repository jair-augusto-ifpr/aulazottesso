#!/usr/bin/env bash
# Deploy pw26 no Google Cloud (Cloud Run + Cloud SQL + GCS).
# Pré-requisito: faturamento ativo no projeto GCP.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-pw26-ifpr-jair}"
REGION="${GCP_REGION:-southamerica-east1}"
SQL_INSTANCE="${GCP_SQL_INSTANCE:-pw26-db}"
DB_NAME="${GCP_DB_NAME:-pw26_database}"
DB_USER="${GCP_DB_USER:-pw26_user}"
SERVICE_NAME="${GCP_SERVICE_NAME:-pw26-django}"
BUCKET_NAME="${GCP_BUCKET_NAME:-pw26-media-${PROJECT_ID}}"

if [[ -z "${GCP_DB_PASSWORD:-}" ]]; then
  echo "Defina GCP_DB_PASSWORD antes de rodar este script."
  exit 1
fi
if [[ -z "${GCP_SECRET_KEY:-}" ]]; then
  echo "Defina GCP_SECRET_KEY (django secret) antes de rodar."
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Projeto: $PROJECT_ID | Região: $REGION"
gcloud config set project "$PROJECT_ID"

echo "==> Habilitando APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  storage.googleapis.com

echo "==> Cloud SQL..."
if ! gcloud sql instances describe "$SQL_INSTANCE" --project="$PROJECT_ID" &>/dev/null; then
  gcloud sql instances create "$SQL_INSTANCE" \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region="$REGION" \
    --project="$PROJECT_ID"
fi

gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE" --project="$PROJECT_ID" 2>/dev/null || true
gcloud sql users create "$DB_USER" \
  --instance="$SQL_INSTANCE" \
  --password="$GCP_DB_PASSWORD" \
  --project="$PROJECT_ID" 2>/dev/null || \
gcloud sql users set-password "$DB_USER" \
  --instance="$SQL_INSTANCE" \
  --password="$GCP_DB_PASSWORD" \
  --project="$PROJECT_ID"

CLOUDSQL_CONN="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"
ENC_PASS="$(python3 -c "import urllib.parse; print(urllib.parse.quote_plus('''${GCP_DB_PASSWORD}'''))")"
DATABASE_URL="postgresql://${DB_USER}:${ENC_PASS}@/${DB_NAME}?host=/cloudsql/${CLOUDSQL_CONN}"

echo "==> Bucket GCS..."
if ! gcloud storage buckets describe "gs://${BUCKET_NAME}" --project="$PROJECT_ID" &>/dev/null; then
  gcloud storage buckets create "gs://${BUCKET_NAME}" \
    --location="$REGION" \
    --uniform-bucket-level-access \
    --project="$PROJECT_ID"
fi

echo "==> Deploy Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region="$REGION" \
  --allow-unauthenticated \
  --quiet \
  --add-cloudsql-instances "$CLOUDSQL_CONN" \
  --set-env-vars "\
SECRET_KEY=${GCP_SECRET_KEY},\
DEBUG=False,\
DATABASE_URL=${DATABASE_URL},\
GS_BUCKET_NAME=${BUCKET_NAME},\
ALLOWED_HOSTS=*,\
GEMINI_API_KEY=${GEMINI_API_KEY:-},\
OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}"

SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" \
  --region="$REGION" \
  --format='value(status.url)')"
echo "URL: $SERVICE_URL"

echo "==> CSRF_TRUSTED_ORIGINS..."
gcloud run services update "$SERVICE_NAME" \
  --region="$REGION" \
  --update-env-vars "CSRF_TRUSTED_ORIGINS=${SERVICE_URL}"

RUN_SA="$(gcloud run services describe "$SERVICE_NAME" \
  --region="$REGION" \
  --format='value(spec.template.spec.serviceAccountName)')"
echo "==> IAM bucket para $RUN_SA"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member="serviceAccount:${RUN_SA}" \
  --role="roles/storage.objectAdmin" \
  --project="$PROJECT_ID"

echo "==> Leitura pública de objetos (TCC / protótipo)..."
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member=allUsers \
  --role=roles/storage.objectViewer \
  --project="$PROJECT_ID" 2>/dev/null || echo "(IAM público já configurado ou bloqueado pela org)"

if [[ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]]; then
  IMAGE="$(gcloud run services describe "$SERVICE_NAME" \
    --region="$REGION" \
    --format='value(spec.template.spec.containers[0].image)')"
  JOB_NAME="${SERVICE_NAME}-admin"
  gcloud run jobs delete "$JOB_NAME" --region="$REGION" --quiet 2>/dev/null || true
  gcloud run jobs create "$JOB_NAME" \
    --image="$IMAGE" \
    --region="$REGION" \
    --set-cloudsql-instances "$CLOUDSQL_CONN" \
    --set-env-vars "\
SECRET_KEY=${GCP_SECRET_KEY},\
DEBUG=False,\
DATABASE_URL=${DATABASE_URL},\
GS_BUCKET_NAME=${BUCKET_NAME},\
DJANGO_SUPERUSER_PASSWORD=${DJANGO_SUPERUSER_PASSWORD},\
DJANGO_SUPERUSER_USERNAME=${DJANGO_SUPERUSER_USERNAME:-admin}" \
    --command python \
    --args manage.py,create_deploy_admin
  gcloud run jobs execute "$JOB_NAME" --region="$REGION" --wait
fi

echo ""
echo "Deploy concluído: $SERVICE_URL"
echo "Admin: ${SERVICE_URL}/admin/"
