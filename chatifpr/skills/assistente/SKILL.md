# Assistente

Use esta rotina ao alterar o chat do estudante.

## Arquivos

- `ia/views.py` — tela, envio AJAX, histórico e download citado.
- `ia/urls.py` — rotas `student_chat`, `student_chat_send`, conversa nova, mensagens e download.
- `ia/chat_service.py` — roteador, gerador e persistência da chamada.
- `ia/usage.py` — limite de tokens.
- `ia/templates/chat.html` — interface. O `template_name` da view é `chat.html`.
- `ia/templatetags/chat_tags.py` — negrito e chips de citação.

## O que não quebrar

- Recusar chatbot fora do curso do aluno, exceto quando `is_global` é verdadeiro.
- Gravar a mensagem do usuário e a do assistente na mesma conversa, com as fontes serializadas.
- Devolver 403 quando o limite de tokens estoura e 502 quando o provedor falha.
- Manter o nome das URLs. O painel e a lista de conversas apontam para `student_chat`.
