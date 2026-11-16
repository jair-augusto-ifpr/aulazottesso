# AGENTS.md — ChatIFPR

Assistente virtual acadêmico do IFPR Campus Paranavaí. Estudantes conversam com chatbots dos cursos em que estão matriculados. Professores cadastram cursos, materiais e a própria chave de API.

## Onde está cada coisa

- `ia/` — assistente. RAG híbrido, embeddings, limite de tokens, views do chat e `ia/templates/chat.html`.
- `website/` — domínio (`models.py`), CRUD, autenticação, `filters.py`, `forms.py` e o restante da interface.
- `chatifpr/settings.py` — configuração. Exige `DATABASE_URL` (Neon). Sem `DEBUG` no ambiente, o padrão local é `True`.
- `skills/` — rotinas curtas para mexer no assistente, no RAG e no deploy.
- `contexto_projeto.md` — regras de negócio e perfis.
- `SPECS.md` — especificação completa.

Os models ficam em `website` porque as migrações já apontam para esse app. O app `ia` importa `website.models` e não duplica tabela.

## Como rodar

```bash
cp .env.example .env
make reset-db
make run
```

Testes: `python manage.py test website`.

## Regras para quem altera o código

- Preservar o isolamento: aluno só acessa chatbot do próprio curso ou chatbot global; professor só edita material e chatbot de que é dono.
- Não gravar `.env`, `app.secrets.yaml` nem chave de API no Git.
- A chave do professor continua em `ProfessorConfig.api_key` (protótipo, texto puro). Não espalhar a chave em log, template ou resposta JSON.
- O chat do aluno está em `ia/views.py` e `ia/urls.py`. O template servido é `chat.html`, arquivo `ia/templates/chat.html`.
- Busca de materiais e de conversas do professor passa por `website/filters.py`.
- Deploy App Engine: `./scripts/deploy-gae.sh` no projeto GCP `chatifpr`. Cloud Run continua em `./scripts/deploy-gcp.sh`.
