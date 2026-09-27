"""Recuperação híbrida persistida (lexical + vetorial) com RRF para o acervo documental institucional."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from django.db.models import Q

from .document_processing import estimate_tokens, index_material
from .embeddings import cosine_similarity, generate_single_embedding
from .models import ChatBot, Material, MaterialChunk, ProfessorConfig


def normalize_term(text: str) -> str:
    """Normaliza texto para busca léxica (minúsculas, sem acentos)."""
    text = text.lower()
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )


def extract_terms(text: str) -> List[str]:
    """Extrai termos significativos de busca (comprimento >= 2)."""
    normalized = normalize_term(text)
    return [t for t in re.split(r"[^\w]+", normalized) if len(t) >= 2]


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
    """Retorna o conjunto de chunks estritamente elegíveis e autorizados para o chatbot."""
    materials_qs = chatbot.materials.all().distinct()
    if not include_private:
        materials_qs = materials_qs.filter(public=True)

    materials = list(materials_qs)
    # Garante que materiais vinculados tenham chunks indexados (backfill transparente para legados)
    for mat in materials:
        if not mat.chunks.exists() and ((mat.text_content or "").strip() or mat.file):
            index_material(mat, force=False, generate_embeddings=False)

    return list(
        MaterialChunk.objects.filter(material__in=materials)
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
    """Busca léxica com ponderação de termos, correspondência de frases e categoria."""
    terms = set(extract_terms(query))
    if additional_terms:
        for t in additional_terms:
            terms.update(extract_terms(t))

    if not terms and query.strip():
        terms = {normalize_term(query.strip())}

    pref_cats = set(preferred_categories or [])
    norm_query = normalize_term(query.strip())

    scored: List[Tuple[MaterialChunk, float]] = []

    for chunk in chunks:
        norm_content = normalize_term(chunk.content)
        norm_title = normalize_term(chunk.material.title or "")
        score = 0.0

        # Correspondência exata da frase de consulta
        if norm_query and norm_query in norm_content:
            score += 5.0

        # Termos no conteúdo do chunk
        for term in terms:
            count = norm_content.count(term)
            if count > 0:
                score += min(count, 4) * 1.0

        # Termos no título do material
        for term in terms:
            if term in norm_title:
                score += 2.0

        # Priorização moderada por categoria identificada
        if chunk.material.category in pref_cats:
            score *= 1.25

        if score > 0:
            scored.append((chunk, score))

    scored.sort(key=lambda x: (-x[1], x[0].material_id, x[0].chunk_index))
    return scored[:limit]


def vector_search_chunks(
    chunks: List[MaterialChunk],
    query: str,
    config: Optional[ProfessorConfig] = None,
    preferred_categories: Optional[List[str]] = None,
    limit: int = 20,
) -> Tuple[List[Tuple[MaterialChunk, float]], str]:
    """Busca vetorial real sobre os chunks autorizados usando similaridade de cosseno.

    Retorna (ranking_vetorial, modo_de_recuperacao).
    """
    pref_cats = set(preferred_categories or [])

    # Verifica se algum chunk possui embedding
    chunks_with_embeddings = [c for c in chunks if c.embedding_vector]
    if not chunks_with_embeddings:
        return [], "lexical_only"

    professor = config.professor if config else None
    query_vector, model_used, dim = generate_single_embedding(
        query, professor=professor, config=config
    )
    if not query_vector:
        return [], "lexical_only"

    scored: List[Tuple[MaterialChunk, float]] = []
    for chunk in chunks_with_embeddings:
        sim = cosine_similarity(query_vector, chunk.embedding_vector)
        if sim > 0:
            # Ponderação por categoria identificada pelo roteador
            if chunk.material.category in pref_cats:
                sim *= 1.15
            scored.append((chunk, sim))

    scored.sort(key=lambda x: (-x[1], x[0].material_id, x[0].chunk_index))
    return scored[:limit], "hybrid"


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
) -> Tuple[List[RetrievedEvidence], str]:
    """Executa a recuperação híbrida com fusão RRF (Reciprocal Rank Fusion).

    Retorna a lista de evidências selecionadas e a etiqueta do modo utilizado ('hybrid' ou 'lexical_only').
    """
    chunks = get_authorized_chunks(chatbot, include_private=include_private)
    if not chunks:
        return [], "no_materials"

    # 1. Ranking Léxico
    lexical_ranked = lexical_search_chunks(
        chunks,
        query,
        additional_terms=router_terms,
        preferred_categories=router_categories,
        limit=20,
    )

    # 2. Ranking Vetorial
    vector_ranked, mode = vector_search_chunks(
        chunks,
        query,
        config=config,
        preferred_categories=router_categories,
        limit=20,
    )

    # 3. Reciprocal Rank Fusion (RRF)
    # RRF(d) = sum( 1 / (60 + rank_i) )
    rrf_scores: Dict[int, float] = {}
    chunk_by_id: Dict[int, MaterialChunk] = {}

    for rank, (chunk, _) in enumerate(lexical_ranked, start=1):
        rrf_scores[chunk.pk] = rrf_scores.get(chunk.pk, 0.0) + (1.0 / (60.0 + rank))
        chunk_by_id[chunk.pk] = chunk

    for rank, (chunk, _) in enumerate(vector_ranked, start=1):
        rrf_scores[chunk.pk] = rrf_scores.get(chunk.pk, 0.0) + (1.0 / (60.0 + rank))
        chunk_by_id[chunk.pk] = chunk

    # Se a busca léxica e vetorial não retornaram nada (ex: termos sem match),
    # inclui como fallback até 3 chunks dos materiais vinculados com maior prioridade
    if not rrf_scores:
        for idx, chunk in enumerate(chunks[:3], start=1):
            rrf_scores[chunk.pk] = 1.0 / (60.0 + idx)
            chunk_by_id[chunk.pk] = chunk

    sorted_candidates = sorted(
        rrf_scores.items(), key=lambda item: (-item[1], item[0])
    )

    # 4. Seleção e controle de orçamento (Budgeting)
    selected_evidences: List[RetrievedEvidence] = []
    total_tokens = 0
    seen_contents: Set[str] = set()
    citation_counter = 1

    for chunk_id, score in sorted_candidates:
        chunk = chunk_by_id[chunk_id]
        content_stripped = chunk.content.strip()

        # Evita duplicação exata de conteúdo
        if content_stripped in seen_contents:
            continue

        c_tokens = chunk.token_count or estimate_tokens(content_stripped)
        if total_tokens + c_tokens > max_context_tokens and selected_evidences:
            # Já temos evidências suficientes e este chunk excederia o orçamento
            break

        rect_notice = ""
        if chunk.material.rectified_material:
            rect_notice = f"Atenção: este documento retifica o material '{chunk.material.rectified_material.title}'."

        has_file = bool(chunk.material.file and chunk.material.file.name)
        download_url = f"/estudante/materiais/{chunk.material.pk}/download/" if has_file else ""

        citation_id = f"[F{citation_counter}]"
        evidence = RetrievedEvidence(
            citation_id=citation_id,
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

    return selected_evidences, mode
