# Deploy

## App Engine

Projeto GCP: `chatifpr`. Região: `southamerica-east1`.

```bash
./scripts/deploy-gae.sh
```

`app.yaml` deixa `DEBUG` desligado e aceita host `.appspot.com`. O script lê `.env`, gera um YAML temporário com `SECRET_KEY` e `DATABASE_URL` e apaga esse arquivo ao terminar. Não commitar esse YAML.

Antes do POST em produção, `chatifpr/settings.py` liga `SECURE_PROXY_SSL_HEADER` quando existe `GAE_APPLICATION` ou `K_SERVICE`.

## Cloud Run

```bash
./scripts/deploy-gcp.sh
```

Exige `GCP_SECRET_KEY` e `DATABASE_URL` no ambiente. O serviço já publicado responde em `https://chatifpr-django-664553333725.southamerica-east1.run.app/`.
