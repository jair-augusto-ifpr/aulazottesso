"""Integração com embeddings reais e funções de similaridade vetorial (compatível com SQLite e PostgreSQL)."""

from __future__ import annotations

import math
import time
from typing import List, Optional, Tuple

from .models import LLMCallLog, Professor, ProfessorConfig


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calcula a similaridade de cosseno exata entre dois vetores numéricos."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def get_embedding_config(
    professor: Optional[Professor] = None,
    config: Optional[ProfessorConfig] = None,
) -> Tuple[str, str, str]:
    """Retorna (provider, api_key, model) configurados para embedding.

    Se embedding_model não estiver especificado, usa text-embedding-004 no Gemini.
    """
    conf = config or (getattr(professor, "config", None) if professor else None)
    if not conf or not conf.has_api():
        return "", "", ""

    provider = conf.provider
    api_key = conf.api_key.strip()
    model = (conf.embedding_model or "").strip()

    if not model and provider == ProfessorConfig.PROVIDER_GEMINI:
        model = "text-embedding-004"

    return provider, api_key, model


def generate_single_embedding(
    text: str,
    *,
    professor: Optional[Professor] = None,
    config: Optional[ProfessorConfig] = None,
) -> Tuple[Optional[List[float]], str, Optional[int]]:
    """Gera embedding para um único texto (ex.: consulta de busca).

    Retorna (vetor, modelo_usado, dimensao). Se indisponível, retorna (None, "", None).
    """
    embeddings, model, dim = generate_batch_embeddings(
        [text], professor=professor, config=config
    )
    if embeddings and len(embeddings) > 0:
        return embeddings[0], model, dim
    return None, "", None


def generate_batch_embeddings(
    texts: List[str],
    *,
    professor: Optional[Professor] = None,
    config: Optional[ProfessorConfig] = None,
) -> Tuple[List[List[float]], str, Optional[int]]:
    """Gera embeddings para uma lista de textos via SDK real (Gemini).

    Se não configurado ou houver erro, retorna lista vazia e modo degradado explícito.
    Nunca gera vetores randômicos ou hashes como embeddings semânticos.
    """
    if not texts:
        return [], "", None

    provider, api_key, model = get_embedding_config(professor, config)
    if not api_key or not model:
        return [], "", None

    start_time = time.monotonic()

    if provider == ProfessorConfig.PROVIDER_GEMINI:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            # Batch de até 100 textos por chamada
            all_vectors: list[list[float]] = []
            batch_size = 50

            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                response = client.models.embed_content(
                    model=model,
                    contents=batch,
                )
                raw_embeddings = getattr(response, "embeddings", None) or []
                for emb in raw_embeddings:
                    values = getattr(emb, "values", None) or []
                    all_vectors.append(list(values))

            duration_ms = int((time.monotonic() - start_time) * 1000)
            dimension = len(all_vectors[0]) if all_vectors else None

            # Registro de auditoria caso professor esteja disponível
            if professor:
                try:
                    conf = config or getattr(professor, "config", None)
                    LLMCallLog.objects.create(
                        professor=professor,
                        student=getattr(professor, "student_profile", None)
                        or professor.user.student_profile
                        if hasattr(professor.user, "student_profile")
                        else None,  # será preenchido se houver student
                        chatbot=None,
                        stage=LLMCallLog.STAGE_EMBEDDING,
                        provider=provider,
                        model_name=model,
                        status=LLMCallLog.STATUS_SUCCESS,
                        duration_ms=duration_ms,
                        tokens_total=len(texts) * 10,  # aproximação de embeddings
                    )
                except Exception:
                    pass

            return all_vectors, model, dimension
        except Exception as exc:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return [], "", None

    # Caso outros provedores não suportem embedding nativo
    return [], "", None
