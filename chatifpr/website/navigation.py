"""Utilitários para o botão Voltar seguir a tela anterior."""

from __future__ import annotations

from urllib.parse import quote, unquote, urlparse

from django.urls import Resolver404, resolve

BACK_LABELS: dict[str, str] = {
    "home": "Início",
    "professor_dashboard": "Painel",
    "student_dashboard": "Painel",
    "professor_course_list": "Cursos",
    "professor_material_list": "Materiais",
    "professor_chatbot_list": "Chatbots",
    "professor_conversation_list": "Conversas",
    "student_conversation_list": "Conversas",
    "student_chat": "Chat",
    "professor_config": "Configuração de API",
    "password_change": "Alterar senha",
}

BLOCKED_PATH_PREFIXES = (
    "/sair/",
    "/professor/entrar/",
    "/estudante/entrar/",
    "/professor/cadastrar/",
    "/estudante/cadastrar/",
)


def _path_from_url(url: str) -> str:
    if url.startswith("/"):
        return url.split("?")[0]
    return urlparse(url).path


def normalize_return_path(url: str, request) -> str:
    """Converte URL absoluta interna em caminho relativo com query string."""
    if not url:
        return ""
    if url.startswith("/"):
        return url
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc != request.get_host():
        return ""
    if parsed.query:
        return f"{parsed.path}?{parsed.query}"
    return parsed.path


def is_safe_return_url(url: str, request) -> bool:
    if not url:
        return False

    path = _path_from_url(url)
    if not path.startswith("/"):
        return False

    current = request.path
    if path == current:
        return False

    for blocked in BLOCKED_PATH_PREFIXES:
        if path == blocked.rstrip("/") or path.startswith(blocked):
            return False

    if url.startswith("/"):
        return True

    parsed = urlparse(url)
    return parsed.netloc == request.get_host()


def get_return_url(request, fallback: str | None = None) -> str | None:
    """Prioridade: parâmetro from, Referer seguro, fallback."""
    for key in ("from",):
        raw = request.GET.get(key) or request.POST.get(key)
        if not raw:
            continue
        candidate = unquote(raw)
        if not candidate.startswith("/"):
            candidate = normalize_return_path(candidate, request)
        if candidate and is_safe_return_url(candidate, request):
            return candidate

    referer = request.META.get("HTTP_REFERER")
    if referer:
        candidate = normalize_return_path(referer, request)
        if candidate and is_safe_return_url(candidate, request):
            return candidate

    return fallback


def label_for_return_url(url: str, fallback_label: str = "Voltar") -> str:
    path = _path_from_url(url)
    try:
        match = resolve(path)
        return BACK_LABELS.get(match.url_name, "Voltar")
    except Resolver404:
        if path.rstrip("/") in ("/professor", "/estudante"):
            return "Painel"
        return fallback_label


def resolve_back_navigation(
    request,
    *,
    fallback_url: str | None = None,
    fallback_label: str = "Voltar",
) -> tuple[str | None, str]:
    back_url = get_return_url(request, fallback_url)
    if not back_url:
        return fallback_url, fallback_label
    if fallback_url and back_url == fallback_url:
        return back_url, fallback_label
    return back_url, label_for_return_url(back_url, fallback_label=fallback_label)


def get_nav_from_param(request, back_url: str | None) -> str:
    """Valor para campo oculto que preserva o destino de voltar em POST."""
    explicit = request.GET.get("from") or request.POST.get("from")
    if explicit:
        return explicit
    if request.method == "GET" and back_url:
        if back_url.startswith("http"):
            return normalize_return_path(back_url, request)
        return back_url
    return ""


def append_from_param(url: str, request) -> str:
    """Anexa ?from= ou &from= com a URL atual."""
    current = request.get_full_path()
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}from={quote(current, safe='')}"
