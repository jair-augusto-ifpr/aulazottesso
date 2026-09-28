from django import template
from django.utils.safestring import mark_safe

from website.chat_format import citation_label, format_assistant_html, parse_citation_id

register = template.Library()


@register.filter(name="format_assistant")
def format_assistant_filter(text, sources):
    """Renderiza negrito e chips de citação de uma resposta do assistente."""
    return mark_safe(format_assistant_html(text or "", sources))


@register.filter(name="citation_label")
def citation_label_filter(citation_id):
    return citation_label(citation_id)


@register.filter(name="citation_key")
def citation_key_filter(citation_id):
    parsed = parse_citation_id(citation_id)
    if not parsed:
        return ""
    return parsed[0]
