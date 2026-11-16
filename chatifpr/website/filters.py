import django_filters
from django.db.models import Q

from .models import Conversation, Material


class MaterialFilter(django_filters.FilterSet):
    """Busca de materiais do professor por título, texto ou curso."""

    q = django_filters.CharFilter(method="filter_q", label="Busca")

    class Meta:
        model = Material
        fields = []

    def filter_q(self, queryset, name, value):
        term = (value or "").strip()
        if not term:
            return queryset
        return queryset.filter(
            Q(title__icontains=term)
            | Q(text_content__icontains=term)
            | Q(courses__name__icontains=term)
        ).distinct()


class ConversationFilter(django_filters.FilterSet):
    """Busca de conversas monitoradas pelo professor."""

    q = django_filters.CharFilter(method="filter_q", label="Busca")

    class Meta:
        model = Conversation
        fields = []

    def filter_q(self, queryset, name, value):
        term = (value or "").strip()
        if not term:
            return queryset
        return queryset.filter(
            Q(student__name__icontains=term)
            | Q(student__ra__icontains=term)
            | Q(title__icontains=term)
        )
