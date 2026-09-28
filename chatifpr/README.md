# ChatIFPR — Assistente Virtual Acadêmico-Administrativo (IFPR Paranavaí)

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

## Arquitetura e RAG Econômico

```
Navegador → Django CBVs → IA 1 (Roteador JSON) → Recuperação Híbrida (Lexical + Vetorial / RRF)
                ↓                                               ↓
        LLMCallLog (Auditoria)                     IA 2 (Gerador Delimitado [F1]...[Fn])
                ↓                                               ↓
         Neon (PostgreSQL) + GCS                Message + Fontes Enriquecidas
```

---

## Modelo de dados

```
User (Django) ──1:1── Professor ──1:1── ProfessorConfig (rag_mode, router_model, embedding_model)
                      Professor ──1:N── Material ──1:N── MaterialChunk (~450 tokens)
                                ──1:N── ChatBot
              └──1:1── Student ──1:N── Conversation ──1:N── Message (fontes, tokens)
                               ──1:N── LLMCallLog (auditoria independente)
Course ──N:N── Professor, Student, Material, ChatBot
```

`Message` guarda o conteúdo, o provedor, o modelo e as fontes com procedência exata ([F1], página/seção, link de download autorizado). `LLMCallLog` rastreia cada chamada das etapas (roteador, gerador, embeddings), preservando o consumo de tokens mesmo se a conversa for excluída.

---

## Como o chat funciona

1. **Início da conversa** — o aluno pode iniciar uma nova conversa ou ela é criada automaticamente no primeiro envio.
2. **IA 1 (Roteamento e Classificação)** — o classificador analisa a pergunta e a memória curta, retornando intenção, categorias documentais e termos de busca com validação de esquema estrita. Se `router_model` estiver vazio e o modelo principal for caro, esta etapa usa um modelo barato; se o principal já for Flash ou gratuito, o roteador reutiliza o principal.
3. **Recuperação Híbrida Persistida** — busca lexical (token inteiro, sem stopwords) e vetorial sobre `MaterialChunk` dos materiais já indexados do chatbot, combinados via *Reciprocal Rank Fusion* (RRF) com orçamento documental controlado (até 2.400 tokens). Sem correspondência, nenhum trecho é enviado ao gerador.
4. **IA 2 (Geração com Citações)** — o gerador recebe os trechos delimitados como dados, a data real calculada no servidor e histórico recente (até 500 tokens), citando fontes com badges `[F1]`, `[F2]`.
5. **Download Autorizado** — o aluno pode baixar os documentos citados via endpoint seguro que revalida o vínculo do estudante ao curso/chatbot do material.
6. **Limite de tokens** — cada professor define um limite de tokens por aluno e um período (dias); o consumo total auditado é debitado com base em `LLMCallLog`.
7. **Modos de Operação do RAG** — configuráveis pelo professor em `/professor/configuracao/`:
   - `two_stage`: Duas etapas (Roteador + Recuperação Híbrida + Gerador) [Padrão]
   - `direct`: RAG Direto (Recuperação Híbrida + Gerador)
   - `baseline`: Baseline comparativo (até 8 prefixos de 20.000 caracteres)

### Comandos de Gestão e Avaliação

```bash
# Reextrai texto e particiona chunks de materiais (suporta --dry-run, --material-id, --force):
python manage.py reextract_materials

# Executa benchmark comparativo sistemático entre estratégias A, B e C:
python manage.py evaluate_rag
```

> Nota de segurança: no protótipo a chave de API fica em texto puro no banco. Em produção, considere criptografar ou usar um cofre de segredos.

---

## Ambiente local

```bash
cd chatifpr
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
