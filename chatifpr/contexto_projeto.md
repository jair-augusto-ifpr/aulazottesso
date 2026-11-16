# Contexto do projeto — ChatIFPR

Protótipo de Programação Web 2026, IFPR Campus Paranavaí. O estudante tira dúvida com base nos documentos do curso. A resposta vem de recuperação híbrida (palavras-chave + vetor) e, quando o professor configurou a API, de um modelo Gemini ou OpenRouter.

## Perfis

| Perfil | Entra com | Pode |
|---|---|---|
| Estudante | RA e senha, grupo `Aluno` | Conversar com assistentes dos cursos matriculados e com chatbots globais; ver e apagar as próprias conversas |
| Professor | SIAPE e senha, grupo `Professor` | CRUD de cursos, materiais e chatbots; definir provedor, modelo, modo RAG e limite de tokens; ler conversas dos próprios chatbots |
| Administrador | Django Admin | Gestão em `/admin/` |
| Visitante | — | Início, sobre, contato, cadastro e login |

## Regras que o código aplica

- Material, chatbot e configuração de API pertencem a um professor. A lista e a edição filtram pelo dono.
- Curso é catálogo compartilhado: não tem dono.
- Chatbot global fica disponível para qualquer estudante. Os demais exigem interseção entre os cursos do aluno e os cursos do chatbot.
- Download de material citado só ocorre se o aluno estiver num curso do material, num curso de um chatbot que usa o material, ou se um chatbot global usar esse material.
- Limite de tokens é por aluno, dentro do professor, com período em dias. Zero significa sem limite ou sem reinício, conforme o campo.
- Sem chave de API configurada, o envio do chat não chama o provedor.
- A primeira mensagem da conversa vira o título, cortada em 120 caracteres.

## Assistente

O fluxo padrão (`two_stage`) classifica a pergunta, busca trechos em `MaterialChunk` e gera a resposta citando `[F1]`, `[F2]`. Os outros modos são `direct` e `baseline`, escolhidos em `/professor/configuracao/`.

Cada chamada fica em `LLMCallLog`. A mensagem do assistente guarda conteúdo, provedor, modelo, tokens e as fontes usadas no chat.
