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


def retrieve_snippets(
    chatbot: ChatBot,
    query: str,
    limit: int = 5,
    *,
    include_private: bool = False,
) -> list[RetrievedSnippet]:
    """Pontua materiais ligados ao chatbot por ocorrência de termos da pergunta."""
    terms = set(_tokenize(query))
    if not terms:
        terms = {query.lower().strip()} if query.strip() else set()

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
        score = sum(blob.count(t) for t in terms)
        if score == 0 and blob:
            # fallback fraco: qualquer substring da pergunta inteira
            q = query.lower().strip()
            if q and q in blob:
                score = 1
        if score > 0:
            scored.append((m, score))

    scored.sort(key=lambda x: -x[1])
    out: list[RetrievedSnippet] = []
    for m, sc in scored[:limit]:
        excerpt_source = (m.text_content or m.title or m.file.name or "").strip()
        excerpt = excerpt_source[:800]
        if len(excerpt_source) > 800:
            excerpt += "…"
        out.append(
            RetrievedSnippet(
                material_id=m.pk,
                title=m.title or m.file.name or f"Material #{m.pk}",
                excerpt=excerpt or "(sem texto indexado — cadastre o campo texto para busca)",
                score=sc,
            )
        )
    return out


def _openai_reply(
    user_question: str,
    context_blocks: list[str],
    chatbot: ChatBot,
) -> str | None:
    key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not key.strip():
        return None

    context = "\n\n---\n\n".join(context_blocks) if context_blocks else "(nenhum trecho recuperado)"
    extra = (chatbot.prompt or "").strip()
    system = (
        "Você é um assistente do IFPR Campus Paranavaí. "
        "Responda em português, de forma clara e objetiva, usando apenas as informações do contexto. "
        "Se o contexto não permitir responder, diga que não encontrou nos documentos e sugira a secretaria."
    )
    if extra:
        system = f"{system}\n\nInstruções adicionais do professor:\n{extra}"
    payload = {
        "model": "gpt-4o-mini",
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
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key.strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, TimeoutError, json.JSONDecodeError):
        return None


def build_answer(
    chatbot: ChatBot,
    user_question: str,
    *,
    include_private: bool = False,
) -> tuple[str, list[RetrievedSnippet]]:
    """
    Retorna (texto da resposta, trechos usados).
    Com OPENAI_API_KEY, tenta gerar linguagem natural; senão, devolve trechos brutos.
    """
    snippets = retrieve_snippets(
        chatbot, user_question, include_private=include_private
    )
    blocks = [f"[{s.title}]\n{s.excerpt}" for s in snippets]

    ai = _openai_reply(user_question, blocks, chatbot)
    if ai:
        return ai, snippets

    if not snippets:
        return (
            "Não encontrei trechos nos documentos públicos ligados a este chatbot para essa pergunta. "
            "Peça ao professor para cadastrar materiais com o campo “texto para busca” ou reformule com outras palavras-chave.",
            [],
        )

    lines = [
        "(Modo sem API de IA — exibindo trechos recuperados por palavras-chave.)",
        "",
    ]
    for s in snippets:
        lines.append(s.title)
        lines.append(s.excerpt)
        lines.append("")
    return "\n".join(lines).strip(), snippets
