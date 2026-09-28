"""Recuperação híbrida persistida (lexical + vetorial) com RRF para o acervo documental institucional."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from django.urls import reverse

from .document_processing import estimate_tokens
from .embeddings import cosine_similarity, generate_single_embedding
from .models import ChatBot, Conversation, MaterialChunk, ProfessorConfig, Student


_STOPWORD_SOURCES = (
    "a", "o", "os", "as", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas",
    "por", "para", "pra", "pro",
    "com", "sem", "sob", "sobre",
    "e", "ou", "mas", "que", "se", "como",
    "ao", "aos",
    "eu", "tu", "ele", "ela", "eles", "elas",
    "me", "te", "lhe", "lhes",
    "meu", "minha", "seu", "sua", "seus", "suas",
    "este", "esta", "esse", "essa", "isso", "isto",
    "aquele", "aquela",
    "nao", "sim", "ja", "tambem", "muito", "mais", "menos",
    "quando", "onde", "qual", "quais", "quem",
    "pelo", "pela", "pelos", "pelas",
    "entre", "ate", "desde", "apos",
    "ser", "sao", "foi", "era", "tem", "ter", "esta", "estao",
    "the", "and", "for", "with",
)


def normalize_term(text: str) -> str:
    """Normaliza texto para busca léxica (minúsculas, sem acentos)."""
    text = text.lower()
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )


_STOPWORDS = {normalize_term(word) for word in _STOPWORD_SOURCES}


def _raw_tokens(text: str) -> List[str]:
    normalized = normalize_term(text)
    return [token for token in re.split(r"[^\w]+", normalized) if token]


def extract_terms(text: str) -> List[str]:
    """Extrai termos de busca: ignora stopwords; exige 3 letras ou um dígito."""
    terms = []
    for token in _raw_tokens(text):
        if token in _STOPWORDS:
            continue
        if any(ch.isdigit() for ch in token) or len(token) >= 3:
            terms.append(token)
    return terms


def _token_counts(text: str) -> Counter:
    return Counter(_raw_tokens(text))


def _term_variants(term: str) -> Set[str]:
    """Singular e plural simples, para pergunta de aluno bater com o documento.

    "feriado" encontra "feriados". Não corta palavra no meio: "arte" não vira "parte".
    """
    variants = {term}
    if len(term) < 4 or any(ch.isdigit() for ch in term):
        return variants
    if term.endswith("s"):
        variants.add(term[:-1])
        if term.endswith("es") and len(term) >= 6:
            variants.add(term[:-2])
    else:
        variants.add(term + "s")
    return variants


def _variant_count(counts: Counter, term: str) -> int:
    return sum(counts.get(variant, 0) for variant in _term_variants(term))


@dataclass
class RetrievedEvidence:
    """Evidência documental recuperada com procedência exata."""

    citation_id: str  # Ex: "[F1]"
    material_id: int
    title: str
    page_or_section: str
    content: str
    score: float
    category: str
    token_count: int
    has_file: bool = False
    download_url: str = ""
    rectification_notice: str = ""


def get_authorized_chunks(chatbot: ChatBot, *, include_private: bool = False) -> List[MaterialChunk]:
    """Retorna os chunks já indexados e autorizados para o chatbot.

    A pergunta do aluno não dispara indexação. O cadastro do professor e o
    comando reextract_materials é que gravam os trechos.
    """
    materials_qs = chatbot.materials.all().distinct()
    if not include_private:
        materials_qs = materials_qs.filter(public=True)

    return list(
        MaterialChunk.objects.filter(material__in=materials_qs)
        .select_related("material", "material__rectified_material")
        .order_by("material_id", "chunk_index")
    )


def lexical_search_chunks(
    chunks: List[MaterialChunk],
    query: str,
    additional_terms: Optional[List[str]] = None,
    preferred_categories: Optional[List[str]] = None,
    limit: int = 20,
) -> List[Tuple[MaterialChunk, float]]:
    """Busca léxica por token inteiro, com bônus de frase e de categoria."""
    terms: Set[str] = set(extract_terms(query))
    if additional_terms:
        for extra in additional_terms:
            terms.update(extract_terms(extra))

    if not terms:
        return []

    pref_cats = set(preferred_categories or [])
    norm_query = normalize_term(query.strip())
    scored: List[Tuple[MaterialChunk, float]] = []

    for chunk in chunks:
        content_counts = _token_counts(chunk.content)
        title_counts = _token_counts(chunk.material.title or "")
        score = 0.0

        if norm_query and norm_query in normalize_term(chunk.content):
            score += 5.0

        for term in terms:
            count = _variant_count(content_counts, term)
            if count > 0:
                score += min(count, 4) * 1.0
            if _variant_count(title_counts, term) > 0:
                score += 2.0

        if score > 0 and chunk.material.category in pref_cats:
            score *= 1.25

        if score > 0:
            scored.append((chunk, score))

    scored.sort(key=lambda item: (-item[1], item[0].material_id, item[0].chunk_index))
    return scored[:limit]


def vector_search_chunks(
    chunks: List[MaterialChunk],
    query: str,
    config: Optional[ProfessorConfig] = None,
    preferred_categories: Optional[List[str]] = None,
    limit: int = 20,
    *,
    student: Optional[Student] = None,
    chatbot: Optional[ChatBot] = None,
    conversation: Optional[Conversation] = None,
) -> Tuple[List[Tuple[MaterialChunk, float]], str, dict]:
    """Busca vetorial real sobre os chunks autorizados usando similaridade de cosseno.

    Retorna (ranking_vetorial, modo_de_recuperacao, uso_de_tokens).
    """
    empty_usage: dict = {}
    pref_cats = set(preferred_categories or [])

    chunks_with_embeddings = [c for c in chunks if c.embedding_vector]
    if not chunks_with_embeddings:
        return [], "lexical_only", empty_usage

    professor = config.professor if config else None
    query_vector, _model_used, _dim, usage = generate_single_embedding(
        query,
        professor=professor,
        config=config,
        student=student,
        chatbot=chatbot,
        conversation=conversation,
    )
    if not query_vector:
        return [], "lexical_only", usage or empty_usage

    scored: List[Tuple[MaterialChunk, float]] = []
    for chunk in chunks_with_embeddings:
        sim = cosine_similarity(query_vector, chunk.embedding_vector)
        if sim > 0:
            if chunk.material.category in pref_cats:
                sim *= 1.15
            scored.append((chunk, sim))

    scored.sort(key=lambda item: (-item[1], item[0].material_id, item[0].chunk_index))
    return scored[:limit], "hybrid", usage or empty_usage


def hybrid_retrieve(
    chatbot: ChatBot,
    query: str,
    *,
    include_private: bool = False,
    config: Optional[ProfessorConfig] = None,
    router_categories: Optional[List[str]] = None,
    router_terms: Optional[List[str]] = None,
    max_candidates: int = 5,
    max_context_tokens: int = 2400,
    student: Optional[Student] = None,
    conversation: Optional[Conversation] = None,
) -> Tuple[List[RetrievedEvidence], str, dict]:
    """Executa a recuperação híbrida com fusão RRF (Reciprocal Rank Fusion).

    Retorna evidências, o modo ('hybrid', 'lexical_only', 'no_materials' ou 'no_match')
    e o uso de tokens do embedding da pergunta.
    """
    chunks = get_authorized_chunks(chatbot, include_private=include_private)
    if not chunks:
        return [], "no_materials", {}

    lexical_ranked = lexical_search_chunks(
        chunks,
        query,
        additional_terms=router_terms,
        preferred_categories=router_categories,
        limit=20,
    )

    vector_ranked, mode, embed_usage = vector_search_chunks(
        chunks,
        query,
        config=config,
        preferred_categories=router_categories,
        limit=20,
        student=student,
        chatbot=chatbot,
        conversation=conversation,
    )

    # RRF(d) = sum( 1 / (60 + rank_i) )
    rrf_scores: Dict[int, float] = {}
    chunk_by_id: Dict[int, MaterialChunk] = {}

    for rank, (chunk, _) in enumerate(lexical_ranked, start=1):
        rrf_scores[chunk.pk] = rrf_scores.get(chunk.pk, 0.0) + (1.0 / (60.0 + rank))
        chunk_by_id[chunk.pk] = chunk

    for rank, (chunk, _) in enumerate(vector_ranked, start=1):
        rrf_scores[chunk.pk] = rrf_scores.get(chunk.pk, 0.0) + (1.0 / (60.0 + rank))
        chunk_by_id[chunk.pk] = chunk

    if not rrf_scores:
        return [], "no_match", embed_usage

    sorted_candidates = sorted(
        rrf_scores.items(), key=lambda item: (-item[1], item[0])
    )

    selected_evidences: List[RetrievedEvidence] = []
    total_tokens = 0
    seen_contents: Set[str] = set()
    citation_counter = 1

    for chunk_id, score in sorted_candidates:
        chunk = chunk_by_id[chunk_id]
        content_stripped = chunk.content.strip()

        if content_stripped in seen_contents:
            continue

        c_tokens = chunk.token_count or estimate_tokens(content_stripped)
        if total_tokens + c_tokens > max_context_tokens and selected_evidences:
            break

        rect_notice = ""
        if chunk.material.rectified_material:
            rect_notice = (
                f"Atenção: este documento retifica o material "
                f"'{chunk.material.rectified_material.title}'."
            )

        has_file = bool(chunk.material.file and chunk.material.file.name)
        download_url = (
            reverse("student_material_download", args=[chunk.material.pk]) if has_file else ""
        )

        evidence = RetrievedEvidence(
            citation_id=f"[F{citation_counter}]",
            material_id=chunk.material.pk,
            title=chunk.material.title or f"Material #{chunk.material.pk}",
            page_or_section=chunk.page_or_section or "Documento",
            content=content_stripped,
            score=round(score, 5),
            category=chunk.material.category,
            token_count=c_tokens,
            has_file=has_file,
            download_url=download_url,
            rectification_notice=rect_notice,
        )

        selected_evidences.append(evidence)
        seen_contents.add(content_stripped)
        total_tokens += c_tokens
        citation_counter += 1

        if len(selected_evidences) >= max_candidates:
            break

    return selected_evidences, mode, embed_usage
