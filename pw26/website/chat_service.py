"""Recuperação textual simples + resposta usando a API configurada pelo professor."""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Iterable

from django.utils import timezone

from .models import ChatBot, Material, ProfessorConfig


_WEEKDAYS_PT = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
]
_MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _current_date_sentence() -> str:
    now = timezone.localtime()
    weekday = _WEEKDAYS_PT[now.weekday()]
    month = _MONTHS_PT[now.month - 1]
    return (
        f"A data real de hoje é {weekday}, {now.day} de {month} de {now.year} "
        f"(formato ISO {now.date().isoformat()}). Use SEMPRE essa data como referência "
        "para calcular \"hoje\", \"amanhã\", \"próximo feriado\", dias que faltam, etc. "
        "Nunca infira a data a partir do conteúdo dos documentos."
    )


def _normalize_text(text: str) -> str:
    text = text.lower()
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )


def _tokenize(text: str) -> list[str]:
    text = _normalize_text(text)
    return [t for t in re.split(r"[^\w]+", text) if len(t) > 2]


@dataclass
class RetrievedSnippet:
    material_id: int
    title: str
    excerpt: str
    score: int


@dataclass
class AnswerResult:
    """Resultado de uma resposta do assistente, incluindo uso de tokens."""

    text: str
    snippets: list = field(default_factory=list)
    provider: str = ""
    model: str = ""
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_total: int = 0
    tokens_cached: int = 0
    error: str | None = None


_EXCERPT_LEN = 20000


def _make_snippet(m: Material, score: int) -> RetrievedSnippet:
    excerpt_source = (m.text_content or m.title or getattr(m.file, "name", "") or "").strip()
    excerpt = excerpt_source[:_EXCERPT_LEN]
    if len(excerpt_source) > _EXCERPT_LEN:
        excerpt += "…"
    return RetrievedSnippet(
        material_id=m.pk,
        title=m.title or getattr(m.file, "name", "") or f"Material #{m.pk}",
        excerpt=excerpt or "(sem texto indexado — cadastre o campo texto para busca)",
        score=score,
    )


def retrieve_snippets(
    chatbot: ChatBot,
    query: str,
    limit: int = 8,
    *,
    include_private: bool = False,
) -> list[RetrievedSnippet]:
    """Retorna os materiais do chatbot ordenados por relevância à pergunta.

    Inclui materiais vinculados até `limit`, mesmo sem match por palavra-chave,
    para garantir que a IA receba o contexto disponível. Por padrão, considera
    apenas materiais públicos; passe `include_private=True` para incluir também
    materiais privados vinculados ao chatbot.
    """
    terms = set(_tokenize(query))
    if not terms and query.strip():
        terms = {query.lower().strip()}

    qs = chatbot.materials.all().distinct()
    if not include_private:
        qs = qs.filter(public=True)
    materials: Iterable[Material] = qs

    scored: list[tuple[Material, int]] = []
    for m in materials:
        blob = _normalize_text(
            " ".join(
                filter(
                    None,
                    [
                        m.title or "",
                        m.text_content or "",
                        getattr(m.file, "name", "") or "",
                    ],
                )
            )
        )
        score = sum(blob.count(t) for t in terms) if blob else 0
        if score == 0 and blob:
            q = _normalize_text(query.strip())
            if q and q in blob:
                score = 1
        scored.append((m, score))

    scored.sort(key=lambda x: (-x[1], x[0].pk))
    return [_make_snippet(m, sc) for m, sc in scored[:limit]]


def _build_system_prompt(chatbot: ChatBot) -> str:
    system = (
        "Você é um assistente do IFPR Campus Paranavaí. "
        "Responda em português, de forma clara e objetiva, usando apenas as informações do contexto. "
        "Se o contexto não permitir responder, diga que não encontrou nos documentos e sugira a secretaria."
    )
    system = f"{system}\n\n{_current_date_sentence()}"
    extra = (chatbot.prompt or "").strip()
    if extra:
        system = f"{system}\n\nInstruções adicionais do professor:\n{extra}"
    return system


def _gemini_usage(response) -> dict:
    meta = getattr(response, "usage_metadata", None)
    if not meta:
        return {}
    prompt = getattr(meta, "prompt_token_count", 0) or 0
    completion = getattr(meta, "candidates_token_count", 0) or 0
    total = getattr(meta, "total_token_count", 0) or 0
    cached = getattr(meta, "cached_content_token_count", 0) or 0
    if not total:
        total = prompt + completion
    return {"prompt": prompt, "completion": completion, "total": total, "cached": cached}


def _gemini_reply(
    user_question: str,
    context_blocks: list[str],
    chatbot: ChatBot,
    api_key: str,
    model: str,
) -> tuple[str | None, dict | None, str | None]:
    key = (api_key or "").strip()
    model = (model or "").strip() or "gemini-2.5-flash"
    if not key:
        return None, None, "Chave Gemini não configurada."

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None, None, "Biblioteca google-genai não instalada (pip install google-genai)."

    context = "\n\n---\n\n".join(context_blocks) if context_blocks else "(nenhum trecho recuperado)"
    system = _build_system_prompt(chatbot)
    user_text = (
        f"Contexto dos documentos:\n{context}\n\n"
        f"Pergunta do estudante: {user_question}"
    )

    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=model,
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.3,
            ),
        )
    except Exception as err:  # SDK lança várias classes de erro (APIError, etc.)
        return None, None, f"Falha ao chamar Gemini: {err}"

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        feedback = getattr(response, "prompt_feedback", None)
        reason = getattr(feedback, "block_reason", None) if feedback else None
        suffix = f" ({reason})" if reason else ""
        return None, None, f"Gemini retornou resposta vazia{suffix}."
    return text, _gemini_usage(response), None


def _openrouter_usage(data: dict) -> dict:
    usage = data.get("usage") or {}
    prompt = usage.get("prompt_tokens", 0) or 0
    completion = usage.get("completion_tokens", 0) or 0
    total = usage.get("total_tokens", 0) or 0
    cached = 0
    details = usage.get("prompt_tokens_details") or {}
    if isinstance(details, dict):
        cached = details.get("cached_tokens", 0) or 0
    if not total:
        total = prompt + completion
    return {"prompt": prompt, "completion": completion, "total": total, "cached": cached}


def _openrouter_reply(
    user_question: str,
    context_blocks: list[str],
    chatbot: ChatBot,
    api_key: str,
    model: str,
) -> tuple[str | None, dict | None, str | None]:
    key = (api_key or "").strip()
    model = (model or "").strip() or "qwen/qwen3-coder:free"
    if not key:
        return None, None, "Chave OpenRouter não configurada."

    context = "\n\n---\n\n".join(context_blocks) if context_blocks else "(nenhum trecho recuperado)"
    system = _build_system_prompt(chatbot)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"Contexto dos documentos:\n{context}\n\nPergunta do estudante: {user_question}",
            },
        ],
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "IFPR Chatbot Academico",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"].strip()
        return text, _openrouter_usage(data), None
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="ignore")
        if err.code == 429:
            return None, None, (
                f"OpenRouter respondeu 429 (limite temporário para o modelo {model}). "
                "Tente novamente em alguns segundos."
            )
        return None, None, f"OpenRouter HTTP {err.code}: {body[:220]}"
    except urllib.error.URLError as err:
        return None, None, f"Falha de rede ao chamar OpenRouter: {err.reason}"
    except (KeyError, TimeoutError, json.JSONDecodeError):
        return None, None, "Resposta inválida da API OpenRouter."


def build_answer(
    chatbot: ChatBot,
    user_question: str,
    *,
    include_private: bool = False,
    config: ProfessorConfig | None = None,
) -> AnswerResult:
    """Gera a resposta usando exclusivamente a API configurada pelo professor.

    Sem `config` válida (`config.has_api()`), retorna um `AnswerResult` com `error`
    e sem consumo de tokens — o envio deve ser bloqueado pela view.
    """
    snippets = retrieve_snippets(
        chatbot, user_question, include_private=include_private
    )
    blocks = [f"[{s.title}]\n{s.excerpt}" for s in snippets]

    if config is None or not config.has_api():
        return AnswerResult(
            text="",
            snippets=snippets,
            error="O professor ainda não configurou uma API para este assistente.",
        )

    if config.provider == ProfessorConfig.PROVIDER_GEMINI:
        text, usage, err = _gemini_reply(
            user_question, blocks, chatbot, config.api_key, config.model
        )
    elif config.provider == ProfessorConfig.PROVIDER_OPENROUTER:
        text, usage, err = _openrouter_reply(
            user_question, blocks, chatbot, config.api_key, config.model
        )
    else:
        return AnswerResult(
            text="",
            snippets=snippets,
            error="Provedor de API inválido na configuração do professor.",
        )

    if err:
        return AnswerResult(
            text="",
            snippets=snippets,
            provider=config.provider,
            model=config.model,
            error=err,
        )

    usage = usage or {}
    return AnswerResult(
        text=text or "",
        snippets=snippets,
        provider=config.provider,
        model=config.model,
        tokens_prompt=usage.get("prompt", 0),
        tokens_completion=usage.get("completion", 0),
        tokens_total=usage.get("total", 0),
        tokens_cached=usage.get("cached", 0),
    )
