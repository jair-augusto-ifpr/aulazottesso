#!/usr/bin/env bash
# Deploy chatifpr no Google Cloud (Cloud Run + Neon Postgres + GCS opcional).
# Pré-requisito: faturamento ativo no projeto GCP.
# Banco: GCP_DATABASE_URL ou DATABASE_URL (Neon). Não cria Cloud SQL.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-gen-lang-client-0684518789}"
REGION="${GCP_REGION:-southamerica-east1}"
SERVICE_NAME="${GCP_SERVICE_NAME:-chatifpr-django}"
BUCKET_NAME="${GCP_BUCKET_NAME:-chatifpr-media-${PROJECT_ID}}"
export DATABASE_URL="${GCP_DATABASE_URL:-${DATABASE_URL:-}}"

if [[ -z "${GCP_SECRET_KEY:-}" ]]; then
  echo "Defina GCP_SECRET_KEY (django secret) antes de rodar."
  exit 1
fi
if [[ -z "${DATABASE_URL}" ]]; then
  echo "Defina GCP_DATABASE_URL ou DATABASE_URL (Postgres Neon) antes de rodar."
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Projeto: $PROJECT_ID | Região: $REGION | Banco: Neon (DATABASE_URL)"
gcloud config set project "$PROJECT_ID"

echo "==> Habilitando APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  storage.googleapis.com \
  generativelanguage.googleapis.com

export CHATIFPR_GS_BUCKET_NAME=""
echo "==> Bucket GCS..."
if gcloud storage buckets describe "gs://${BUCKET_NAME}" --project="$PROJECT_ID" &>/dev/null; then
  export CHATIFPR_GS_BUCKET_NAME="$BUCKET_NAME"
  echo "Bucket existente: gs://${BUCKET_NAME}"
elif gcloud storage buckets create "gs://${BUCKET_NAME}" \
    --location="$REGION" \
    --uniform-bucket-level-access \
    --project="$PROJECT_ID"; then
  export CHATIFPR_GS_BUCKET_NAME="$BUCKET_NAME"
  echo "Bucket criado: gs://${BUCKET_NAME}"
else
  echo "GCS indisponível (IAM). Deploy sem GS_BUCKET_NAME (uploads locais no container)."
fi

ENV_FILE="$(mktemp /tmp/chatifpr-cloudrun-env.XXXXXX.yaml)"
cleanup() { rm -f "$ENV_FILE"; }
trap cleanup EXIT

write_env_file() {
  python3 - "$ENV_FILE" "$1" <<'PY'
import json, os, sys

path, mode = sys.argv[1], sys.argv[2]
database_url = os.environ.get("GCP_DATABASE_URL") or os.environ["DATABASE_URL"]
if mode == "admin":
    vals = {
        "SECRET_KEY": os.environ["GCP_SECRET_KEY"],
        "DEBUG": "False",
        "DATABASE_URL": database_url,
        "DJANGO_SUPERUSER_PASSWORD": os.environ["DJANGO_SUPERUSER_PASSWORD"],
        "DJANGO_SUPERUSER_USERNAME": os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin"),
    }
else:
    vals = {
        "SECRET_KEY": os.environ["GCP_SECRET_KEY"],
        "DEBUG": "False",
        "ALLOWED_HOSTS": "*",
        "DATABASE_URL": database_url,
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
        "GEMINI_MODEL": os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
        "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", ""),
    }
gs = os.environ.get("CHATIFPR_GS_BUCKET_NAME", "")
if gs:
    vals["GS_BUCKET_NAME"] = gs
with open(path, "w", encoding="utf-8") as fh:
    for key, value in vals.items():
        fh.write(f"{key}: {json.dumps(value)}\n")
PY
}

write_env_file service

echo "==> Deploy Cloud Run..."
# 30 threads por instância, alinhado ao Gunicorn em entrypoint.sh.
# A segunda instância só sobe se passar de 30 requisições ao mesmo tempo.
DEPLOY_COMMON=(
  "$SERVICE_NAME"
  --region="$REGION"
  --allow-unauthenticated
  --quiet
  --concurrency=30
  --timeout=180
  --cpu=2
  --memory=2Gi
  --min-instances=1
  --max-instances=3
  --cpu-boost
  --env-vars-file="$ENV_FILE"
)
if [[ -n "${GCP_IMAGE:-}" ]]; then
  gcloud run deploy "${DEPLOY_COMMON[@]}" --image="$GCP_IMAGE"
else
  gcloud run deploy "${DEPLOY_COMMON[@]}" --source .
fi

SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" \
  --region="$REGION" \
  --format='value(status.url)')"
echo "URL: $SERVICE_URL"

echo "==> CSRF_TRUSTED_ORIGINS..."
gcloud run services update "$SERVICE_NAME" \
  --region="$REGION" \
  --update-env-vars "CSRF_TRUSTED_ORIGINS=${SERVICE_URL}" \
  --quiet

if [[ -n "${CHATIFPR_GS_BUCKET_NAME}" ]]; then
  RUN_SA="$(gcloud run services describe "$SERVICE_NAME" \
    --region="$REGION" \
    --format='value(spec.template.spec.serviceAccountName)')"
  echo "==> IAM bucket para $RUN_SA"
  gcloud storage buckets add-iam-policy-binding "gs://${CHATIFPR_GS_BUCKET_NAME}" \
    --member="serviceAccount:${RUN_SA}" \
    --role="roles/storage.objectAdmin" \
    --project="$PROJECT_ID" || echo "(IAM objectAdmin bloqueado)"
  echo "==> Leitura pública de objetos (TCC / protótipo)..."
  gcloud storage buckets add-iam-policy-binding "gs://${CHATIFPR_GS_BUCKET_NAME}" \
    --member=allUsers \
    --role=roles/storage.objectViewer \
    --project="$PROJECT_ID" 2>/dev/null || echo "(IAM público já configurado ou bloqueado pela org)"
fi

echo "==> Job de seed (dados de exemplo e config Gemini)..."
IMAGE="$(gcloud run services describe "$SERVICE_NAME" \
  --region="$REGION" \
  --format='value(spec.template.spec.containers[0].image)')"
SEED_JOB_NAME="${SERVICE_NAME}-seed"
gcloud run jobs delete "$SEED_JOB_NAME" --region="$REGION" --quiet 2>/dev/null || true
gcloud run jobs create "$SEED_JOB_NAME" \
  --image="$IMAGE" \
  --region="$REGION" \
  --env-vars-file="$ENV_FILE" \
  --command python \
  --args manage.py,seed
gcloud run jobs execute "$SEED_JOB_NAME" --region="$REGION" --wait

if [[ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]]; then
  JOB_NAME="${SERVICE_NAME}-admin"
  write_env_file admin
  gcloud run jobs delete "$JOB_NAME" --region="$REGION" --quiet 2>/dev/null || true
  gcloud run jobs create "$JOB_NAME" \
    --image="$IMAGE" \
    --region="$REGION" \
    --env-vars-file="$ENV_FILE" \
    --command python \
    --args manage.py,create_deploy_admin
  gcloud run jobs execute "$JOB_NAME" --region="$REGION" --wait
fi

echo ""
echo "Deploy concluído: $SERVICE_URL"
echo "Admin: ${SERVICE_URL}/admin/"
if [[ -z "${CHATIFPR_GS_BUCKET_NAME}" ]]; then
  echo "Media: filesystem local do container (GCS bloqueado por IAM)."
fi
echo "Banco: Neon (sem Cloud SQL)."
