"""Integração com embeddings reais e funções de similaridade vetorial (compatível com SQLite e PostgreSQL)."""

from __future__ import annotations

import math
import time
from typing import List, Optional, Tuple

from .document_processing import estimate_tokens
from .models import ChatBot, Conversation, LLMCallLog, Professor, ProfessorConfig, Student


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


def embedding_token_usage(response, texts: List[str]) -> dict:
    """Conta tokens do embedding pela API ou, na falta disso, pela estimativa local."""
    meta = getattr(response, "usage_metadata", None)
    prompt = int(getattr(meta, "prompt_token_count", 0) or 0) if meta is not None else 0
    total = int(getattr(meta, "total_token_count", 0) or 0) if meta is not None else 0
    cached = int(getattr(meta, "cached_content_token_count", 0) or 0) if meta is not None else 0
    if total <= 0 and prompt > 0:
        total = prompt
    if total <= 0:
        total = sum(estimate_tokens(text) for text in texts)
        prompt = total
    return {
        "prompt": prompt,
        "completion": 0,
        "total": total,
        "cached": cached,
    }


def _empty_usage() -> dict:
    return {"prompt": 0, "completion": 0, "total": 0, "cached": 0}


def _add_usage(total: dict, extra: dict) -> None:
    for key in ("prompt", "completion", "total", "cached"):
        total[key] = (total.get(key) or 0) + (extra.get(key) or 0)


def _log_embedding_call(
    *,
    professor: Optional[Professor],
    student: Optional[Student],
    chatbot: Optional[ChatBot],
    conversation: Optional[Conversation],
    provider: str,
    model_name: str,
    status: str,
    duration_ms: int,
    usage: dict,
    error_message: str = "",
) -> None:
    """Grava a chamada. Sem aluno, o log não entra na cota do estudante."""
    if professor is None:
        return
    LLMCallLog.objects.create(
        professor=professor,
        student=student,
        chatbot=chatbot,
        conversation=conversation,
        stage=LLMCallLog.STAGE_EMBEDDING,
        provider=provider or "",
        model_name=model_name or "",
        status=status,
        duration_ms=duration_ms,
        tokens_prompt=usage.get("prompt", 0) or 0,
        tokens_completion=usage.get("completion", 0) or 0,
        tokens_total=usage.get("total", 0) or 0,
        tokens_cached=usage.get("cached", 0) or 0,
        error_message=(error_message or "")[:500],
    )


def generate_single_embedding(
    text: str,
    *,
    professor: Optional[Professor] = None,
    config: Optional[ProfessorConfig] = None,
    student: Optional[Student] = None,
    chatbot: Optional[ChatBot] = None,
    conversation: Optional[Conversation] = None,
) -> Tuple[Optional[List[float]], str, Optional[int], dict]:
    """Gera embedding para um único texto (ex.: consulta de busca).

    Retorna (vetor, modelo_usado, dimensao, uso). Se indisponível, o vetor é None.
    """
    embeddings, model, dim, usage = generate_batch_embeddings(
        [text],
        professor=professor,
        config=config,
        student=student,
        chatbot=chatbot,
        conversation=conversation,
    )
    if embeddings:
        return embeddings[0], model, dim, usage
    return None, "", None, usage


def generate_batch_embeddings(
    texts: List[str],
    *,
    professor: Optional[Professor] = None,
    config: Optional[ProfessorConfig] = None,
    student: Optional[Student] = None,
    chatbot: Optional[ChatBot] = None,
    conversation: Optional[Conversation] = None,
) -> Tuple[List[List[float]], str, Optional[int], dict]:
    """Gera embeddings para uma lista de textos via SDK real (Gemini).

    Se não configurado ou houver erro, retorna lista vazia e modo degradado explícito.
    Nunca gera vetores randômicos ou hashes como embeddings semânticos.
    """
    if not texts:
        return [], "", None, _empty_usage()

    provider, api_key, model = get_embedding_config(professor, config)
    if not api_key or not model:
        return [], "", None, _empty_usage()

    if provider != ProfessorConfig.PROVIDER_GEMINI:
        return [], "", None, _empty_usage()

    start_time = time.monotonic()
    usage = _empty_usage()
    all_vectors: list[list[float]] = []

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
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
            _add_usage(usage, embedding_token_usage(response, batch))

        duration_ms = int((time.monotonic() - start_time) * 1000)
        dimension = len(all_vectors[0]) if all_vectors else None
        if len(all_vectors) != len(texts):
            raise RuntimeError("A API de embedding devolveu quantidade diferente de vetores.")

        _log_embedding_call(
            professor=professor,
            student=student,
            chatbot=chatbot,
            conversation=conversation,
            provider=provider,
            model_name=model,
            status=LLMCallLog.STATUS_SUCCESS,
            duration_ms=duration_ms,
            usage=usage,
        )
        return all_vectors, model, dimension, usage
    except Exception as exc:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        _log_embedding_call(
            professor=professor,
            student=student,
            chatbot=chatbot,
            conversation=conversation,
            provider=provider,
            model_name=model,
            status=LLMCallLog.STATUS_FAILED,
            duration_ms=duration_ms,
            usage=usage,
            error_message=str(exc),
        )
        return [], "", None, usage
