# PW26 — Assistente Virtual Acadêmico-Administrativo (IFPR Paranavaí)

Protótipo de pesquisa em Django que permite a estudantes tirarem dúvidas com base em **documentos institucionais** do curso. O sistema combina **busca por palavras-chave** nos materiais cadastrados e, opcionalmente, **IA generativa** (Google Gemini ou OpenRouter) para responder em linguagem natural.

Projeto alinhado ao **Plano de Atividades de Programação Web 2026** (3 trimestres) e à pesquisa FIciências / IFTECH / SIPEN.

---

## Sumário

1. [Visão geral](#visão-geral)
2. [Requisitos PW 2026 atendidos](#requisitos-pw-2026-atendidos)
3. [Arquitetura](#arquitetura)
4. [Modelo de dados](#modelo-de-dados)
5. [Como o chat funciona](#como-o-chat-funciona)
6. [Ambiente local](#ambiente-local)
7. [Dados de exemplo (seed)](#dados-de-exemplo-seed)
8. [Rotas principais](#rotas-principais)
9. [Tecnologias](#tecnologias)

---

## Visão geral

| Perfil | Autenticação | O que faz |
|--------|--------------|-----------|
| **Estudante** | RA + senha (Django auth, grupo `Aluno`) | Usa chatbots dos cursos matriculados; histórico persistido |
| **Professor** | SIAPE + senha (Django auth, grupo `Professor`) | CRUD de cursos, materiais e chatbots |
| **Administrador** | Django Admin (`/admin/`) | Gestão centralizada |

---

## Requisitos PW 2026 atendidos

### 1º trimestre
- Projeto Django configurado com página **Sobre** (descrição + diagramas de caso de uso e classes)
- **8 classes** (sem contar `User`): `Course`, `Professor`, `ProfessorConfig`, `Student`, `Material`, `ChatBot`, `Conversation`, `Message`
- CBVs: `CreateView`, `UpdateView`, `DeleteView`, `DetailView`, `ListView`
- Template `form.html` reutilizado para inserir/alterar

### 2º trimestre
- Login, logout e alteração de senha (`/conta/senha/alterar/`)
- `LoginRequiredMixin` + `GroupRequiredMixin` (django-braces)
- `form_valid()` / `get_queryset()` filtrando por dono (professor/aluno)
- `request.user.is_authenticated` e grupos no menu (`base.html`)
- Paginação (`paginate_by`) nas listas
- QuerySets na página inicial (estatísticas e últimos chatbots)
- Django Debug Toolbar em `DEBUG=True`
- `select_related` / `prefetch_related` em dashboards e listas

### 3º trimestre
- **Movimento**: chat persiste `Conversation` e `Message` no banco (não só sessão)
- Duas classes por usuário: `Material`/`ChatBot` (professor) e `Conversation`/`Message` (aluno)
- Filtro de pesquisa na lista de materiais (`?q=`)
- Plugins jQuery: **Mask** (RA/telefone no cadastro) e **DataTables** (materiais e conversas)
- Interface navegável com fluxo coerente

---

## Arquitetura

```
Navegador → Django CBVs → chat_service (RAG) → Gemini/OpenRouter
                ↓
         SQLite / PostgreSQL + media/GCS
```

---

## Modelo de dados

```
User (Django) ──1:1── Professor ──1:1── ProfessorConfig
                      Professor ──1:N── Material, ChatBot
              └──1:1── Student ──1:N── Conversation ──1:N── Message
Course ──N:N── Professor, Student, Material, ChatBot
```

`Message` guarda, além do conteúdo, o **provedor**, o **modelo** e as **estatísticas de tokens** (`tokens_prompt`, `tokens_completion`, `tokens_total`, `tokens_cached`).

---

## Como o chat funciona

1. **Iniciar/continuar conversa** — o aluno cria uma "Nova conversa" (ou seleciona uma anterior) antes de enviar; o campo de envio fica desativado até haver conversa ativa
2. **Recuperação** — tokenização e busca em `title` / `text_content` dos materiais do chatbot
3. **Geração** — usa **a API do próprio professor** (`ProfessorConfig`: Gemini ou OpenRouter). Sem API configurada, o envio é **bloqueado**
4. **Limite de tokens** — cada professor define um limite de tokens por aluno e um período (dias); ao atingir, o envio é bloqueado
5. **Persistência (AJAX)** — pergunta/resposta viram `Message`, com modelo e tokens exibidos em cada mensagem; envio/recebimento por AJAX com spinner e botão desabilitado durante a espera

### Configuração de API do professor

O professor acessa `/professor/configuracao/` e informa provedor, chave, modelo, limite de tokens por aluno e período. Ele também monitora (somente leitura) todas as conversas dos seus chatbots e o consumo por aluno em `/professor/conversas/`.

> Nota de segurança: no protótipo a chave de API fica em texto puro no banco. Em produção, considere criptografar ou usar um cofre de segredos.

---

## Ambiente local

```bash
cd pw26
cp .env.example .env
make reset-db   # migra + seed
make run
```

Abra [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## Dados de exemplo (seed)

| Perfil | Login | Senha |
|--------|-------|-------|
| Admin | `admin` | `admin123` |
| Professor | SIAPE `2074709` | `prof123` |
| Secretaria | SIAPE `1000001` | `sec123` |
| Aluno | RA `20233012578` | `aluno123` |

```bash
make seed
```

---

## Rotas principais

| URL | Descrição |
|-----|-----------|
| `/` | Página inicial com estatísticas |
| `/sobre/` | Projeto + diagramas |
| `/estudante/entrar/` | Login estudante |
| `/estudante/` | Painel do estudante |
| `/estudante/chat/<id>/` | Chat com assistente (iniciar/continuar conversa, AJAX) |
| `/estudante/conversas/` | Histórico (DataTables) |
| `/professor/entrar/` | Login professor |
| `/professor/` | Painel do professor |
| `/professor/configuracao/` | Configuração de API, limite de tokens e período |
| `/professor/conversas/` | Monitoramento (somente leitura) e uso de tokens por aluno |
| `/professor/materiais/` | CRUD materiais + filtro |
| `/professor/chatbots/` | CRUD chatbots |
| `/professor/cursos/` | CRUD cursos |
| `/conta/senha/alterar/` | Troca de senha |
| `/sair/` | Logout |
| `/admin/` | Django Admin |

Deploy em nuvem: [`DEPLOY_GCP.md`](DEPLOY_GCP.md)

---

## Tecnologias

Django 4.2+, django-braces, django-debug-toolbar, Gemini, OpenRouter, pypdf, python-docx, WhiteNoise, Gunicorn, Docker/GCP.

---

## Licença e contexto acadêmico

Projeto desenvolvido no IFPR Campus Paranavaí — Técnico em Informática Integrado / Pesquisa FIciências 2026.
