# Tarefas de revisão executadas

## 1. Erro de digitação/cópia

**Executado:** o texto alternativo da marca na página inicial foi corrigido de `Instituto Federal Paraná` para `Instituto Federal do Paraná`.

## 2. Bug no fallback do chat

**Executado:** o envio assíncrono agora recoloca a mensagem no `textarea` antes de acionar o fallback com `form.submit()`, evitando que a submissão tradicional envie uma mensagem vazia após falha de rede/HTTP.

## 3. Comentário/documentação discrepante

**Executado:** a docstring de `retrieve_snippets` agora descreve que materiais privados só são incluídos quando `include_private=True`.

## 4. Melhoria de testes

**Executado:** `website/tests.py` agora cobre o fluxo crítico de envio do chat e a regra de privacidade de `retrieve_snippets`.
