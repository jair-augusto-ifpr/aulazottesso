# RAG

Use esta rotina ao alterar indexação ou recuperação.

## Arquivos

- `ia/text_extraction.py` — PDF, DOCX e texto do upload.
- `ia/document_processing.py` — particiona o material em `MaterialChunk` e estima tokens.
- `ia/embeddings.py` — vetor real via Gemini. Sem chave, não inventa vetor.
- `ia/rag_retrieval.py` — busca lexical e vetorial combinadas por RRF.

## Comandos

```bash
python manage.py reextract_materials
python manage.py evaluate_rag
```

A indexação roda no `form_valid` de criar e editar material, em `website/views.py`, chamando `ia.document_processing.index_material`.

## O que não quebrar

- Sem trecho correspondente, o gerador não recebe documento.
- Retificação aponta para outro material pelo campo `rectified_material`.
- Embedding só é gerado quando a configuração do professor tem API e o chamador pede `generate_embeddings=True`.
