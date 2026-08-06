# Especificações do Projeto — PW26

**Assistente Virtual Acadêmico-Administrativo**  
IFPR Campus Paranavaí · Protótipo de pesquisa · Programação Web 2026

---

## 1. Visão geral

Sistema web em Django que permite a estudantes tirarem dúvidas com base em **documentos institucionais** dos seus cursos. Combina:

- **Recuperação textual (RAG simplificado)** — busca por palavras-chave em materiais cadastrados
- **IA generativa** — Google Gemini ou OpenRouter, usando a API configurada por cada professor

### 1.1 Contexto acadêmico

- Alinhado ao **Plano de Atividades PW 2026** (3 trimestres)
- Pesquisa **FIciências / IFTECH / SIPEN**
- Metodologia **Design Science Research (DSR)** documentada em `/sobre/`

### 1.2 Perfis de usuário

| Perfil | Autenticação | Grupo Django | Funções principais |
|--------|--------------|--------------|-------------------|
| **Estudante** | RA + senha | `Aluno` | Chat com assistentes dos cursos matriculados; histórico de conversas |
| **Professor** | SIAPE + senha | `Professor` | CRUD de cursos, materiais e chatbots; configuração de API; monitoramento |
| **Administrador** | Django Admin | `is_staff` | Gestão centralizada em `/admin/` |
| **Visitante** | — | — | Páginas públicas, login/cadastro |

---

## 2. Stack tecnológica

| Camada | Tecnologia |
|--------|------------|
| Backend | Django 4.2+ (compatível até Django 6) |
| Autenticação | `django.contrib.auth` + **django-braces** (`LoginRequiredMixin`, `GroupRequiredMixin`) |
| Banco (dev) | SQLite (`db.sqlite3`) |
| Banco (prod) | PostgreSQL via `DATABASE_URL` (ex.: Neon) |
| Arquivos (prod) | Google Cloud Storage (`django-storages`) |
| Servidor (prod) | Gunicorn + WhiteNoise |
| Frontend | Bootstrap 5.3, Bootstrap Icons, jQuery |
| Plugins UI | jQuery Mask (cadastro), DataTables (listas) |
| IA | `google-genai` (Gemini), HTTP OpenRouter |
| Documentos | `pypdf`, `python-docx` (extração de texto) |
| Debug | Django Debug Toolbar (`DEBUG=True`) |
| Deploy | Docker, Google Cloud Run — ver `DEPLOY_GCP.md` |

### 2.1 Variáveis de ambiente (`.env`)

| Variável | Descrição |
|----------|-----------|
| `SECRET_KEY` | Chave secreta Django |
| `DEBUG` | `True` / `False` |
| `ALLOWED_HOSTS` | Hosts permitidos (vírgula) |
| `DATABASE_URL` | PostgreSQL (opcional; sem ela usa SQLite) |
| `GEMINI_API_KEY` | Chave Gemini (seed e fallback global) |
| `GEMINI_MODEL` | Modelo Gemini (padrão: `gemini-2.5-flash`) |
| `OPENROUTER_API_KEY` | Chave OpenRouter |
| `OPENROUTER_MODEL` | Modelo OpenRouter |
| `GS_BUCKET_NAME` | Bucket GCS para uploads em produção |
| `CSRF_TRUSTED_ORIGINS` | Origens CSRF em produção |

---

## 3. Modelo de dados

### 3.1 Diagrama de relacionamentos

```
User (Django Auth)
  ├── 1:1 ── Professor ── 1:1 ── ProfessorConfig
  │              ├── 1:N ── Material
  │              └── 1:N ── ChatBot
  └── 1:1 ── Student ── 1:N ── Conversation ── 1:N ── Message

Course ──N:N── Professor, Student, Material, ChatBot
```

### 3.2 Entidades

#### `Course`
- `name` (CharField, 50)

#### `Professor`
- `user` (OneToOne → User)
- `name`, `siape` (único)
- `courses` (M2M → Course)

#### `ProfessorConfig`
- `professor` (OneToOne)
- `provider`: `gemini` | `openrouter`
- `api_key`, `model`
- `token_limit_per_student` (0 = ilimitado)
- `limit_period_days` (0 = acumulado total)
- Método `has_api()` — verifica se envio de chat está habilitado

#### `Student`
- `user` (OneToOne → User)
- `name`, `ra` (único), `phone`
- `courses` (M2M → Course)

#### `Material`
- `owner` (FK → Professor)
- `title`, `text_content`, `file` (upload `materiais/%Y/%m/`)
- `public` (Boolean)
- `courses` (M2M)
- Extração automática de texto de PDF/DOCX no cadastro (quando aplicável)

#### `ChatBot`
- `owner` (FK → Professor)
- `prompt` (até 2000 caracteres)
- `materials`, `courses` (M2M)
- Propriedade `assistant_title`: `"Assistente de {nome do professor}"` (ou `"Assistente da Secretaria"`)

#### `Conversation`
- `student`, `chatbot` (FK)
- `title` (gerado a partir da primeira mensagem)
- `created_at`, `updated_at`

#### `Message`
- `conversation` (FK)
- `role`: `user` | `assistant`
- `content`, `sources` (JSON — trechos recuperados)
- `provider`, `model_name`
- `tokens_prompt`, `tokens_completion`, `tokens_total`, `tokens_cached`
- `created_at`

### 3.3 Classes de domínio (requisito PW)

8 classes além de `User`: `Course`, `Professor`, `ProfessorConfig`, `Student`, `Material`, `ChatBot`, `Conversation`, `Message`.

---

## 4. Rotas e endpoints

### 4.1 Páginas públicas

| URL | Nome | Descrição |
|-----|------|-----------|
| `/` | `home` | Página inicial com estatísticas e CTA |
| `/sobre/` | `sobre` | Projeto, DSR, diagramas UML |
| `/contato/` | `contato` | Contato |
| `/sair/` | `logout` | Logout |
| `/conta/senha/alterar/` | `password_change` | Alterar senha (logado) |

### 4.2 Acesso (não autenticado)

| URL | Nome | Descrição |
|-----|------|-----------|
| `/estudante/entrar/` | `student_login` | Login estudante (RA) |
| `/estudante/cadastrar/` | `student_signup` | Cadastro estudante |
| `/professor/entrar/` | `professor_login` | Login professor (SIAPE) |
| `/professor/cadastrar/` | `professor_signup` | Cadastro professor |

**Menu Acesso (navbar):** dropdown com **Estudante** e **Professor**, cada um levando direto à tela de login (com link para criar conta).

### 4.3 Área do estudante

| URL | Nome | Descrição |
|-----|------|-----------|
| `/estudante/` | `student_dashboard` | Painel — cursos e assistentes |
| `/estudante/chat/<chatbot_id>/` | `student_chat` | Interface de chat (estilo assistente) |
| `/estudante/chat/<id>/send/` | `student_chat_send` | POST AJAX — enviar mensagem |
| `/estudante/chat/<id>/conversas/nova/` | `student_conversation_create` | POST AJAX — nova conversa vazia |
| `/estudante/chat/<id>/conversas/<conv_id>/mensagens/` | `student_conversation_messages` | GET AJAX — histórico da conversa |
| `/estudante/conversas/` | `student_conversation_list` | Histórico (DataTables) |
| `/estudante/conversas/<pk>/excluir/` | `student_conversation_delete` | Excluir conversa |

### 4.4 Área do professor

| URL | Nome | Descrição |
|-----|------|-----------|
| `/professor/` | `professor_dashboard` | Painel com resumo e atalhos |
| `/professor/configuracao/` | `professor_config` | API, modelo, limites de tokens |
| `/professor/conversas/` | `professor_conversation_list` | Monitoramento + uso por aluno |
| `/professor/conversas/<pk>/` | `professor_conversation_detail` | Detalhe somente leitura |
| `/professor/cursos/` | `professor_course_list` | Lista de cursos |
| `/professor/cursos/novo/` | `professor_course_new` | Criar curso |
| `/professor/cursos/<pk>/` | `professor_course_detail` | Detalhe |
| `/professor/cursos/<pk>/editar/` | `professor_course_edit` | Editar |
| `/professor/cursos/<pk>/excluir/` | `professor_course_delete` | Excluir |
| `/professor/materiais/` | `professor_material_list` | Lista + filtro `?q=` |
| `/professor/materiais/novo/` | `professor_material_new` | Criar material |
| `/professor/materiais/<pk>/` | `professor_material_detail` | Detalhe |
| `/professor/materiais/<pk>/editar/` | `professor_material_edit` | Editar |
| `/professor/materiais/<pk>/excluir/` | `professor_material_delete` | Excluir |
| `/professor/chatbots/` | `professor_chatbot_list` | Lista de chatbots |
| `/professor/chatbot/novo/` | `professor_chatbot_new` | Criar chatbot |
| `/professor/chatbots/<pk>/` | `professor_chatbot_detail` | Detalhe |
| `/professor/chatbot/<pk>/editar/` | `professor_chatbot_edit` | Editar |
| `/professor/chatbot/<pk>/excluir/` | `professor_chatbot_delete` | Excluir |

### 4.5 Admin

| URL | Descrição |
|-----|-----------|
| `/admin/` | Django Admin |

---

## 5. Regras de negócio

### 5.1 Autorização

- Estudante só acessa chatbots cujo curso intersecta os cursos do aluno (`_student_can_use_chatbot`).
- Professor só vê/edita registros próprios (`ProfessorOwnerQuerysetMixin`, `owner` field).
- Estudante só vê conversas próprias (`StudentOwnerQuerysetMixin`).
- Professor só monitora conversas dos chatbots que possui.

### 5.2 Chat e IA

1. **Recuperação** — `retrieve_snippets()` tokeniza a pergunta e pontua materiais do chatbot por match em `title` / `text_content`. Inclui materiais privados no contexto enviado à IA (`include_private=True` no envio).
2. **Geração** — `build_answer()` usa `ProfessorConfig` do dono do chatbot (Gemini ou OpenRouter).
3. **Bloqueios de envio** (`can_send()`):
   - Professor sem API configurada → mensagem de erro ao aluno
   - Limite de tokens do aluno atingido no período → bloqueio
4. **Conversa** — criada automaticamente no primeiro envio se não houver conversa ativa; também pode ser criada via botão **Novo chat** na sidebar.
5. **Título** — primeira mensagem do usuário vira título da conversa (até 120 caracteres).
6. **Data atual** — injetada no prompt para cálculos de calendário.
7. **Persistência** — cada troca gera `Message` com tokens, modelo e fontes (snippets).

### 5.3 Limites de tokens (`website/usage.py`)

- `consumed_tokens()` — soma `tokens_total` das respostas do assistente por aluno/professor
- `remaining_tokens()` — limite configurado menos consumo
- `usage_summary()` — exibido no chat do aluno e no monitoramento do professor
- Período: últimos N dias se `limit_period_days > 0`; senão acumulado total

### 5.4 Materiais

- Campo `public` controla visibilidade na recuperação pública (listagens/índice).
- Upload com extração automática de texto (`text_extraction.py`) quando `text_content` está vazio.
- Filtro na lista: `?q=` busca em título, texto e nome de curso.

---

## 6. Interface e UX

### 6.1 Identidade visual

- Tema **IFPR** (verde) sobre Bootstrap 5
- CSS principal: `static/css/style.css`
- Chat: `static/css/chat-gpt.css` (layout sidebar + área de mensagens)
- Navbar sticky com gradiente verde
- Cards, tabelas, botões e formulários padronizados

### 6.2 Templates reutilizáveis

| Arquivo | Uso |
|---------|-----|
| `website/base.html` | Layout base |
| `website/form.html` | Formulários genéricos (CRUD) |
| `website/confirm_delete.html` | Confirmação de exclusão |
| `website/includes/nav_menu.html` | Menu por perfil |
| `website/includes/page_back.html` | Botão voltar |
| `website/includes/form_field.html` | Campos Bootstrap (checkboxes M2M) |
| `website/includes/table_actions_dropdown.html` | Menu ⋯ nas listas |
| `website/includes/chat_bubbles.html` | Bolhas de mensagem |
| `website/pagination.html` | Paginação |

### 6.3 Navegação “Voltar” (`website/navigation.py`)

| Origem | Comportamento |
|--------|---------------|
| **Menu dropdown** do usuário | Links com `?from=/estudante/` ou `?from=/professor/` → volta ao **Painel** |
| **Links internos** | `nav_from_suffix` / `append_nav_from` → volta à **página anterior** |
| **Sem histórico** | Fallback configurado por view (`nav_back_url_name`) |

Tags de template: `navigation_tags` — `nav_from_suffix`, `nav_from_panel`, `append_nav_from`, `student_chat_open_url`.

**Painel do estudante** não exibe botão voltar (é a home logada do aluno).

### 6.4 Chat do estudante

- Sidebar: **← Painel**, Novo chat, busca, lista de conversas, chip do usuário, consumo de tokens
- Área principal: título do assistente (`Assistente de {professor}`)
- Campo de mensagem sempre habilitado (se API OK)
- Envio AJAX com spinner; Enter envia, Shift+Enter quebra linha
- Fontes recuperadas em `<details>` nas respostas
- Meta por mensagem: modelo e tokens

### 6.5 Listas do professor

- Paginação (`paginate_by = 10`)
- Coluna **Ações** com dropdown (Ver, Editar, Excluir)
- DataTables em materiais (estudante: conversas)

---

## 7. Views e mixins

### 7.1 Mixins (`website/mixins.py`)

| Mixin | Função |
|-------|--------|
| `ProfessorRequiredMixin` | Login + grupo Professor |
| `StudentRequiredMixin` | Login + grupo Aluno |
| `ProfessorOwnerQuerysetMixin` | Filtra por `owner` |
| `StudentOwnerQuerysetMixin` | Filtra por `student` |
| `NavBackMixin` | Injeta `back_url` / `back_label` |
| `FormTemplateMixin` | Template `form.html` + título dinâmico |

### 7.2 CBVs utilizadas

`TemplateView`, `ListView`, `DetailView`, `CreateView`, `UpdateView`, `DeleteView`, `LoginView`, `LogoutView`, `PasswordChangeView`, `View` (endpoints AJAX do chat).

---

## 8. Serviços

| Módulo | Responsabilidade |
|--------|------------------|
| `chat_service.py` | RAG, chamadas Gemini/OpenRouter, `AnswerResult` |
| `usage.py` | Consumo e limites de tokens |
| `navigation.py` | Lógica do botão voltar |
| `text_extraction.py` | Extração de PDF/DOCX |
| `context_processors.portal_user` | `is_student`, `is_professor`, perfis no template |

---

## 9. Formulários (`website/forms.py`)

| Formulário | Uso |
|------------|-----|
| `StudentLoginForm` | RA como username |
| `ProfessorLoginForm` | SIAPE como username |
| `StudentSignupForm` | Cadastro com cursos, máscara de telefone |
| `ProfessorSignupForm` | Cadastro professor |
| `PortalPasswordChangeForm` | Troca de senha |
| `CourseForm` | CRUD curso |
| `MaterialForm` | CRUD material (cursos do professor) |
| `ChatBotForm` | CRUD chatbot (cursos + materiais do professor) |
| `ProfessorConfigForm` | Configuração de API |
| `ChatMessageForm` | Mensagem do chat (validação AJAX) |

Widgets com classes Bootstrap: `form-control`, `form-select`, `form-check-input`.

---

## 10. Testes (`website/tests.py`)

| Classe | Cobertura |
|--------|-----------|
| `ChatFlowTests` | Envio, limites, API, tokens, conversa automática, snippets público/privado |
| `ProfessorMonitoringTests` | Listagem e isolamento de conversas |
| `NavigationTests` | `from`, referer, labels, integração HTTP do voltar |

Executar: `make test`

---

## 11. Dados de exemplo (seed)

```bash
make seed      # ou make reset-db
```

| Perfil | Login | Senha |
|--------|-------|-------|
| Admin | `admin` | `admin123` |
| Professor | SIAPE `2074709` | `prof123` |
| Secretaria | SIAPE `1000001` | `sec123` |
| Aluno | RA `20233012578` | `aluno123` |

**Seed cria:**
- Cursos: Informática, Administração
- Professor: Késsia Marchi
- Aluno: Jair Boeing (matriculado em Informática)
- Material: Calendário Acadêmico 2026
- Chatbot vinculado ao material e curso
- `ProfessorConfig` com API do `.env` (se houver chave) ou vazia

---

## 12. Comandos Make

| Comando | Ação |
|---------|------|
| `make run` | venv + migrate + runserver |
| `make reset-db` | SQLite limpo + migrate + seed |
| `make seed` | Dados de exemplo |
| `make test` | Testes Django |
| `make collectstatic` | Arquivos estáticos |
| `make deploy-gcp` | Script de deploy |

---

## 13. Requisitos PW 2026 (checklist)

### 1º trimestre
- [x] Projeto Django + página Sobre com diagramas
- [x] 8 classes de domínio
- [x] CBVs CRUD completas
- [x] Template `form.html` reutilizado

### 2º trimestre
- [x] Login, logout, alteração de senha
- [x] `LoginRequiredMixin` + `GroupRequiredMixin`
- [x] `form_valid()` / `get_queryset()` por dono
- [x] Menu condicional por autenticação/grupo
- [x] Paginação nas listas
- [x] QuerySets na home
- [x] Debug Toolbar
- [x] `select_related` / `prefetch_related`

### 3º trimestre
- [x] Chat com `Conversation` e `Message` persistidos
- [x] Duas classes por usuário (Material/ChatBot professor; Conversation/Message aluno)
- [x] Filtro `?q=` em materiais
- [x] jQuery Mask + DataTables
- [x] Interface navegável com fluxo coerente

---

## 14. Segurança e limitações conhecidas

- Chave de API do professor armazenada em **texto plano** no banco (protótipo).
- CSRF em todos os POSTs; AJAX do chat envia token.
- URLs de retorno (`from`) validadas como caminhos internos (`navigation.is_safe_return_url`).
- Upload de arquivos sem antivírus (ambiente acadêmico).
- Sem rate limiting global além do limite de tokens por professor.

---

## 15. Estrutura de diretórios

```
pw26/
├── pw26/              # settings, urls raiz, wsgi
├── website/
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── forms.py
│   ├── mixins.py
│   ├── navigation.py
│   ├── chat_service.py
│   ├── usage.py
│   ├── text_extraction.py
│   ├── templatetags/
│   ├── templates/website/
│   ├── migrations/
│   ├── management/commands/seed.py
│   └── tests.py
├── static/            # CSS, imagens, diagramas
├── media/             # uploads locais
├── requirements.txt
├── Makefile
├── Dockerfile
├── SPECS.md           # este documento
├── README.md
└── DEPLOY_GCP.md
```

---

## 16. Referências

- [README.md](README.md) — guia rápido de uso
- [DEPLOY_GCP.md](DEPLOY_GCP.md) — deploy em nuvem
- Diagramas: `static/img/diagrama-casos-uso.svg`, `static/img/diagrama-classes.svg`

---

*Documento gerado para o repositório PW26 — IFPR Campus Paranavaí · 2026*
