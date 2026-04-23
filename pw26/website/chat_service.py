"""Recuperação textual simples + resposta (API generativa opcional)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable

from django.conf import settings

from .models import ChatBot, Material


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    return [t for t in re.split(r"[^\w]+", text) if len(t) > 2]


@dataclass
class RetrievedSnippet:
    material_id: int
    title: str
    excerpt: str
    score: int


_EXCERPT_LEN = 1500


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

    Sempre inclui os materiais vinculados (até `limit`), mesmo sem match por
    palavra-chave, para garantir que a IA sempre receba o contexto disponível.
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
        blob = " ".join(
            filter(
                None,
                [
                    m.title or "",
                    m.text_content or "",
                    getattr(m.file, "name", "") or "",
                ],
            )
        ).lower()
        score = sum(blob.count(t) for t in terms) if blob else 0
        if score == 0 and blob:
            q = query.lower().strip()
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
    extra = (chatbot.prompt or "").strip()
    if extra:
        system = f"{system}\n\nInstruções adicionais do professor:\n{extra}"
    return system


def _gemini_reply(
    user_question: str,
    context_blocks: list[str],
    chatbot: ChatBot,
) -> tuple[str | None, str | None]:
    key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash") or "gemini-2.5-flash"
    if not key:
        return None, "GEMINI_API_KEY não configurada."

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None, "Biblioteca google-genai não instalada (pip install google-genai)."

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
        return None, f"Falha ao chamar Gemini: {err}"

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        feedback = getattr(response, "prompt_feedback", None)
        reason = getattr(feedback, "block_reason", None) if feedback else None
        suffix = f" ({reason})" if reason else ""
        return None, f"Gemini retornou resposta vazia{suffix}."
    return text, None


def _openrouter_reply(
    user_question: str,
    context_blocks: list[str],
    chatbot: ChatBot,
) -> tuple[str | None, str | None]:
    key = getattr(settings, "OPENROUTER_API_KEY", "") or ""
    model = getattr(settings, "OPENROUTER_MODEL", "qwen/qwen3-coder:free") or "qwen/qwen3-coder:free"
    if not key.strip():
        return None, "OPENROUTER_API_KEY não configurada."

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
            "Authorization": f"Bearer {key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "IFPR Chatbot Academico",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip(), None
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="ignore")
        if err.code == 429:
            return None, (
                f"OpenRouter respondeu 429 (limite temporário para o modelo {model}). "
                "Tente novamente em alguns segundos."
            )
        return None, f"OpenRouter HTTP {err.code}: {body[:220]}"
    except urllib.error.URLError as err:
        return None, f"Falha de rede ao chamar OpenRouter: {err.reason}"
    except (KeyError, TimeoutError, json.JSONDecodeError):
        return None, "Resposta inválida da API OpenRouter."


def build_answer(
    chatbot: ChatBot,
    user_question: str,
    *,
    include_private: bool = False,
) -> tuple[str, list[RetrievedSnippet]]:
    """
    Retorna (texto da resposta, trechos usados).
    Prioriza Gemini (GEMINI_API_KEY); se indisponível, tenta OpenRouter;
    sem nenhuma chave, devolve os trechos recuperados localmente.
    """
    snippets = retrieve_snippets(
        chatbot, user_question, include_private=include_private
    )
    blocks = [f"[{s.title}]\n{s.excerpt}" for s in snippets]

    errors: list[str] = []

    if (getattr(settings, "GEMINI_API_KEY", "") or "").strip():
        ai, err = _gemini_reply(user_question, blocks, chatbot)
        if ai:
            return ai, snippets
        if err:
            errors.append(err)

    if (getattr(settings, "OPENROUTER_API_KEY", "") or "").strip():
        ai, err = _openrouter_reply(user_question, blocks, chatbot)
        if ai:
            return ai, snippets
        if err:
            errors.append(err)

    api_error = " | ".join(errors) if errors else None

    if not snippets:
        return (
            "Não há materiais vinculados a este chatbot. "
            "Peça ao professor para cadastrar documentos e preencher o campo de texto para busca.",
            [],
        )

    lines = []
    if api_error:
        lines.append(f"(API indisponível agora: {api_error})")
    lines.append("(Modo sem API de IA — exibindo trechos recuperados por palavras-chave.)")
    lines.append("")
    for s in snippets:
        lines.append(s.title)
        lines.append(s.excerpt)
        lines.append("")
    return "\n".join(lines).strip(), snippets
