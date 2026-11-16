#!/usr/bin/env bash
# Publica o ChatIFPR no App Engine Standard.
# Lê .env na raiz do projeto e não grava segredo no repositório.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROJECT_ID="${GCP_PROJECT_ID:-chatifpr}"
REGION="${GCP_REGION:-southamerica-east1}"
PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

if [[ ! -f .env ]]; then
  echo "Crie o .env com DATABASE_URL antes do deploy."
  exit 1
fi

echo "==> Projeto: ${PROJECT_ID} | Região: ${REGION}"

if ! gcloud app describe --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "==> Criando aplicação App Engine..."
  gcloud app create --project="$PROJECT_ID" --region="$REGION" --quiet
fi

TMP="${ROOT}/app.deploy.yaml"
cleanup() { rm -f "$TMP"; }
trap cleanup EXIT

"$PYTHON" - "$TMP" <<'PY'
import os
import secrets
import sys
from pathlib import Path

from dotenv import dotenv_values

base = Path("app.yaml").read_text().rstrip() + "\n"
env = dotenv_values(".env")
secret = (
    os.environ.get("SECRET_KEY")
    or os.environ.get("GCP_SECRET_KEY")
    or env.get("SECRET_KEY")
    or secrets.token_urlsafe(50)
)
database_url = os.environ.get("DATABASE_URL") or env.get("DATABASE_URL") or ""
if not database_url:
    raise SystemExit("DATABASE_URL ausente.")

values = {
    "SECRET_KEY": secret,
    "DATABASE_URL": database_url,
    "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY") or env.get("GEMINI_API_KEY") or "",
    "GEMINI_MODEL": os.environ.get("GEMINI_MODEL") or env.get("GEMINI_MODEL") or "gemini-3.8-flash",
    "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY") or env.get("OPENROUTER_API_KEY") or "",
    "OPENROUTER_MODEL": os.environ.get("OPENROUTER_MODEL") or env.get("OPENROUTER_MODEL") or "",
}
lines = []
for key, value in values.items():
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    lines.append(f'  {key}: "{escaped}"')
Path(sys.argv[1]).write_text(base + "\n".join(lines) + "\n")
PY

echo "==> Publicando..."
gcloud app deploy "$TMP" --project="$PROJECT_ID" --quiet --version=chatifpr

echo "==> URL:"
gcloud app describe --project="$PROJECT_ID" --format="value(defaultHostname)"
