from django import template
from django.urls import reverse

from website.navigation import append_from_param

register = template.Library()


@register.simple_tag(takes_context=True)
def append_nav_from(context, url: str) -> str:
    """Anexa o parâmetro from com a página atual ao link informado."""
    return append_from_param(url, context["request"])


@register.simple_tag(takes_context=True)
def nav_from_suffix(context) -> str:
    """Retorna ?from=... com a URL atual (navegação interna)."""
    request = context["request"]
    from urllib.parse import quote

    return f"?from={quote(request.get_full_path(), safe='')}"


@register.simple_tag
def nav_from_panel(panel_url_name: str) -> str:
    """Retorna ?from=... apontando para o painel (links do menu do usuário)."""
    from urllib.parse import quote

    return f"?from={quote(reverse(panel_url_name), safe='')}"


@register.simple_tag(takes_context=True)
def student_chat_open_url(context, chatbot_id, conversation_id) -> str:
    """URL do chat com conversa e rastreio da página atual para o botão voltar."""
    url = f"{reverse('student_chat', args=[chatbot_id])}?conversa={conversation_id}"
    return append_from_param(url, context["request"])
