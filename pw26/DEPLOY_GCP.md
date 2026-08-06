# Deploy pw26 no Google Cloud

## Pré-requisito obrigatório

O projeto GCP precisa ter **faturamento ativo**. Sem isso, `gcloud services enable` e o deploy falham com `Billing must be enabled`.

1. Acesse [Console de faturamento](https://console.cloud.google.com/billing)
2. Vincule uma conta de faturamento ao projeto (ex.: `pw26-ifpr-jair` na nova conta)
3. Confirme: `gcloud beta billing projects describe SEU_PROJECT_ID`

## Deploy automatizado

Na raiz do projeto (`pw26/`):

```bash
export GCP_PROJECT_ID=pw26-ifpr-jair
export GCP_DB_PASSWORD='senha-forte-aqui'
export GCP_SECRET_KEY='chave-django-longa-aleatoria'
# opcional:
export GEMINI_API_KEY='...'
export OPENROUTER_API_KEY='...'

./scripts/deploy-gcp.sh
```

O script habilita APIs, cria Cloud SQL (`pw26-db`), bucket `pw26-media-PROJETO`, faz deploy no Cloud Run, configura `CSRF_TRUSTED_ORIGINS` e IAM do bucket.

## Superusuário após o deploy

```bash
gcloud run jobs create pw26-admin \
  --image "$(gcloud run services describe pw26-django --region=southamerica-east1 --format='value(spec.template.spec.containers[0].image)')" \
  --region southamerica-east1 \
  --set-cloudsql-instances "${GCP_PROJECT_ID}:southamerica-east1:pw26-db" \
  --set-env-vars "DJANGO_SUPERUSER_PASSWORD=...,DJANGO_SUPERUSER_USERNAME=admin,DATABASE_URL=...,SECRET_KEY=...,DEBUG=False,GS_BUCKET_NAME=pw26-media-${GCP_PROJECT_ID}" \
  --command python \
  --args manage.py,create_deploy_admin

gcloud run jobs execute pw26-admin --region southamerica-east1 --wait
```

## Checklist pós-deploy

- [ ] URL do serviço abre sem `DisallowedHost`
- [ ] `/admin/` com CSS (WhiteNoise)
- [ ] Upload de PDF aparece no bucket GCS e persiste após restart
- [ ] Chat encontra texto do material

## Texto para relatório (TCC)

> O protótipo foi implantado no Google Cloud utilizando o serviço Cloud Run para execução da aplicação Django em ambiente serverless, com banco de dados PostgreSQL gerenciado pelo Cloud SQL e armazenamento de documentos (uploads) no Google Cloud Storage. Essa arquitetura permite escalabilidade, implantação simplificada via container e redução da administração de servidores, mantendo persistência dos dados e dos arquivos institucionais.
