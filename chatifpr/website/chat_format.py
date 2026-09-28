"""Apresentação segura das respostas do assistente.

O texto salvo permanece em Markdown cru. Esta camada só escapa HTML e
aplica negrito (`**trecho**`) e chips de citação (`[F1]`, `[M12]`).
"""

from __future__ import annotations

import html
import re
from typing import Any

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_CITE_RE = re.compile(r"\[([A-Za-z])(\d+)\]")
_CITE_ID_RE = re.compile(r"^\[([A-Za-z])(\d+)\]$")


def parse_citation_id(citation_id: str | None) -> tuple[str, str] | None:
    """Retorna (chave sem colchetes, número) para um id como ``[F1]``."""
    match = _CITE_ID_RE.match((citation_id or "").strip())
    if not match:
        return None
    return f"{match.group(1)}{match.group(2)}", match.group(2)


def citation_label(citation_id: str | None) -> str:
    """``[F1]`` vira ``Fonte 1``. Ids fora do padrão voltam como texto."""
    parsed = parse_citation_id(citation_id)
    if not parsed:
        return citation_id or ""
    return f"Fonte {parsed[1]}"


def _source_field(source: Any, name: str) -> str:
    if isinstance(source, dict):
        value = source.get(name, "")
    else:
        value = getattr(source, name, "")
    if value is None:
        return ""
    return str(value)


def _source_index(sources: Any) -> dict[str, Any]:
    index: dict[str, Any] = {}
    for source in sources or []:
        citation_id = _source_field(source, "citation_id").strip()
        if citation_id and citation_id not in index:
            index[citation_id] = source
    return index


def _plain_title(source: Any) -> str:
    title = " ".join(_source_field(source, "title").split())
    return title or "Fonte"


def format_assistant_html(text: str | None, sources: Any = None) -> str:
    """Escapa o texto e devolve HTML de negrito, quebras de linha e citações."""
    escaped = html.escape(text or "", quote=True)
    escaped = _BOLD_RE.sub(lambda match: f"<strong>{match.group(1)}</strong>", escaped)
    index = _source_index(sources)

    def replace_citation(match: re.Match[str]) -> str:
        citation_id = match.group(0)
        source = index.get(citation_id)
        if source is None:
            return citation_id
        key = f"{match.group(1)}{match.group(2)}"
        number = match.group(2)
        label = html.escape(f"Fonte {number}: {_plain_title(source)}", quote=True)
        return (
            f'<button type="button" class="cite-chip" data-cite="{html.escape(key, quote=True)}" '
            f'title="{label}" aria-label="{label}">{html.escape(number, quote=True)}</button>'
        )

    escaped = _CITE_RE.sub(replace_citation, escaped)
    return escaped.replace("\n", "<br>")
