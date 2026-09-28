"""Processamento de documentos e particionamento determinístico de trechos (chunking) para o RAG."""

from __future__ import annotations

import hashlib
import re
from typing import List, Tuple

from django.db import transaction

from .models import Material, MaterialChunk
from .text_extraction import ExtractedBlock, extract_document_blocks


def estimate_tokens(text: str) -> int:
    """Estimativa conservadora e calibrada de tokens para texto em português.

    Não assume len(text)/4 nem depende de tiktoken como padrão universal.
    Conta palavras e pontuações, aplicando margem de segurança para sub-palavras.
    """
    if not text:
        return 0
    # Extrai tokens léxicos (palavras e símbolos de pontuação)
    tokens = re.findall(r"\w+|[^\w\s]", text, re.UNICODE)
    # Palavras com mais de 7 caracteres tipicamente se dividem em 2+ subwords
    subword_count = sum(1 + (len(t) // 7) for t in tokens if len(t) > 7)
    regular_count = sum(1 for t in tokens if len(t) <= 7)
    estimated = regular_count + subword_count
    # Aplica margem conservadora de 10%
    return max(1, int(estimated * 1.10))


def source_fingerprint(material: Material) -> str:
    """Hash do texto salvo e dos bytes do arquivo.

    O chunk pode sair do PDF mesmo quando text_content não muda. O fingerprint
    precisa enxergar os dois, senão um arquivo novo fica marcado como já indexado.
    """
    digest = hashlib.sha256()
    digest.update(b"text:")
    digest.update((material.text_content or "").encode("utf-8"))
    file_field = material.file
    if not file_field or not file_field.name:
        return digest.hexdigest()

    digest.update(b"\nfile:")
    digest.update(file_field.name.encode("utf-8"))
    opened = False
    try:
        file_field.open("rb")
        opened = True
        while True:
            blob = file_field.read(1024 * 1024)
            if not blob:
                break
            digest.update(blob)
    except Exception:
        size = 0
        try:
            size = file_field.size or 0
        except Exception:
            size = 0
        digest.update(b"\nsize:")
        digest.update(str(size).encode("utf-8"))
    finally:
        if opened:
            try:
                file_field.close()
            except Exception:
                pass
    return digest.hexdigest()


def chunk_text(
    text: str,
    page_or_section: str = "",
    target_tokens: int = 450,
    overlap_tokens: int = 50,
    start_char_offset: int = 0,
) -> List[dict]:
    """Particiona um texto em trechos determinísticos próximos a `target_tokens` com overlap.

    Preserva parágrafos e frases antes de dividir no nível de palavras.
    """
    if not text or not text.strip():
        return []

    # Divide prioritariamente por parágrafos duplos ou quebras de linha
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    chunks: list[dict] = []
    current_parts: list[str] = []
    current_tokens = 0
    chunk_start_char = start_char_offset

    for para in paragraphs:
        para_tokens = estimate_tokens(para)

        # Se o próprio parágrafo for maior que target_tokens, divide por frases
        if para_tokens > target_tokens:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()]
            for sentence in sentences:
                sent_tokens = estimate_tokens(sentence)
                if current_tokens + sent_tokens > target_tokens and current_parts:
                    content = "\n\n".join(current_parts).strip()
                    c_tokens = estimate_tokens(content)
                    chunks.append(
                        {
                            "content": content,
                            "page_or_section": page_or_section,
                            "token_count": c_tokens,
                            "char_start": chunk_start_char,
                            "char_end": chunk_start_char + len(content),
                        }
                    )
                    # Overlap com última frase
                    current_parts = [sentence]
                    current_tokens = sent_tokens
                    chunk_start_char += len(content)
                else:
                    current_parts.append(sentence)
                    current_tokens += sent_tokens
        elif current_tokens + para_tokens > target_tokens and current_parts:
            content = "\n\n".join(current_parts).strip()
            c_tokens = estimate_tokens(content)
            chunks.append(
                {
                    "content": content,
                    "page_or_section": page_or_section,
                    "token_count": c_tokens,
                    "char_start": chunk_start_char,
                    "char_end": chunk_start_char + len(content),
                }
            )
            # Overlap com último elemento se couber no limite de overlap
            if current_parts and estimate_tokens(current_parts[-1]) <= overlap_tokens:
                current_parts = [current_parts[-1], para]
                current_tokens = estimate_tokens(current_parts[0]) + para_tokens
            else:
                current_parts = [para]
                current_tokens = para_tokens
            chunk_start_char += len(content)
        else:
            current_parts.append(para)
            current_tokens += para_tokens

    if current_parts:
        content = "\n\n".join(current_parts).strip()
        if content:
            chunks.append(
                {
                    "content": content,
                    "page_or_section": page_or_section,
                    "token_count": estimate_tokens(content),
                    "char_start": chunk_start_char,
                    "char_end": chunk_start_char + len(content),
                }
            )

    return chunks


def build_material_chunks(material: Material) -> List[dict]:
    """Gera a lista estruturada de chunks a partir do arquivo ou do text_content do material."""
    blocks: list[ExtractedBlock] = []

    if material.file:
        res = extract_document_blocks(material.file)
        if res.status == "success" and res.blocks:
            blocks = res.blocks

    # Se não há blocos do arquivo, utiliza o text_content cadastrado
    if not blocks:
        text = (material.text_content or "").strip()
        if not text:
            return []
        blocks = [
            ExtractedBlock(
                text=text,
                page_or_section="Documento integral",
                block_type="text",
                char_start=0,
                char_end=len(text),
            )
        ]

    all_chunks: list[dict] = []
    chunk_index = 0

    for block in blocks:
        block_chunks = chunk_text(
            text=block.text,
            page_or_section=block.page_or_section,
            target_tokens=450,
            overlap_tokens=50,
            start_char_offset=block.char_start,
        )
        for c in block_chunks:
            c["chunk_index"] = chunk_index
            c["content_hash"] = hashlib.sha256(c["content"].encode("utf-8")).hexdigest()
            all_chunks.append(c)
            chunk_index += 1

    return all_chunks


def index_material(
    material: Material,
    *,
    force: bool = False,
    generate_embeddings: bool = True,
    config=None,
) -> dict:
    """Indexa de forma idempotente e atômica os chunks de um material.

    Se o conteúdo não mudou e force=False, reaproveita os chunks existentes.
    """
    raw_text = (material.text_content or "").strip()
    if not raw_text and not material.file:
        material.chunks.all().delete()
        return {"updated": False, "chunk_count": 0, "reason": "empty_material"}

    current_hash = source_fingerprint(material)
    if (
        not force
        and material.content_hash == current_hash
        and material.chunks.exists()
    ):
        return {
            "updated": False,
            "chunk_count": material.chunks.count(),
            "reason": "already_indexed",
        }

    raw_chunks = build_material_chunks(material)
    if not raw_chunks:
        material.chunks.all().delete()
        return {"updated": False, "chunk_count": 0, "reason": "no_chunks_generated"}

    # Obter embeddings caso solicitado e configurado
    embeddings_map = {}
    embedding_model_name = ""
    embedding_dim = None

    if generate_embeddings:
        try:
            from .embeddings import generate_batch_embeddings

            texts = [c["content"] for c in raw_chunks]
            embeddings, model_used, dim, _embed_usage = generate_batch_embeddings(
                texts, professor=material.owner, config=config
            )
            if embeddings and len(embeddings) == len(raw_chunks):
                embeddings_map = {idx: emb for idx, emb in enumerate(embeddings)}
                embedding_model_name = model_used
                embedding_dim = dim
        except Exception:
            # Degradação graciosa para modo lexical se embedding falhar
            pass

    chunk_objects = []
    for c in raw_chunks:
        emb = embeddings_map.get(c["chunk_index"])
        chunk_objects.append(
            MaterialChunk(
                material=material,
                chunk_index=c["chunk_index"],
                content=c["content"],
                page_or_section=c["page_or_section"],
                token_count=c["token_count"],
                char_start=c["char_start"],
                char_end=c["char_end"],
                content_hash=c["content_hash"],
                embedding_vector=emb,
                embedding_model=embedding_model_name if emb else "",
                embedding_dimension=embedding_dim if emb else None,
            )
        )

    with transaction.atomic():
        material.chunks.all().delete()
        MaterialChunk.objects.bulk_create(chunk_objects)
        material.content_hash = current_hash
        material.processing_version = (material.processing_version or 1) + 1
        material.save(update_fields=["content_hash", "processing_version", "updated_at"])

    return {
        "updated": True,
        "chunk_count": len(chunk_objects),
        "tokens_total": sum(c.token_count for c in chunk_objects),
        "has_embeddings": bool(embeddings_map),
    }
