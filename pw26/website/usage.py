"""Cálculo de consumo e limite de tokens por aluno em cada professor."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from .models import Message, Professor, ProfessorConfig, Student


def get_config(professor: Professor) -> ProfessorConfig | None:
    return getattr(professor, "config", None)


def consumed_tokens(
    professor: Professor,
    student: Student,
    *,
    period_days: int | None = None,
) -> int:
    """Soma os tokens das respostas do assistente para o aluno nos chatbots do professor."""
    qs = Message.objects.filter(
        role=Message.ROLE_ASSISTANT,
        conversation__student=student,
        conversation__chatbot__owner=professor,
    )
    if period_days:
        since = timezone.now() - timedelta(days=period_days)
        qs = qs.filter(created_at__gte=since)
    return qs.aggregate(total=Sum("tokens_total"))["total"] or 0


def remaining_tokens(
    config: ProfessorConfig | None,
    professor: Professor,
    student: Student,
) -> int | None:
    """Tokens restantes para o aluno, ou None quando o limite é ilimitado."""
    if not config or not config.token_limit_per_student:
        return None
    used = consumed_tokens(
        professor, student, period_days=config.limit_period_days or None
    )
    return max(config.token_limit_per_student - used, 0)


def usage_summary(
    config: ProfessorConfig | None,
    professor: Professor,
    student: Student,
) -> dict:
    """Resumo de uso para exibir na tela do aluno e no monitoramento do professor."""
    period = (config.limit_period_days or None) if config else None
    used = consumed_tokens(professor, student, period_days=period)
    limit = config.token_limit_per_student if config else 0
    remaining = max(limit - used, 0) if limit else None
    return {
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "period_days": config.limit_period_days if config else 0,
        "unlimited": not bool(limit),
    }


def can_send(
    config: ProfessorConfig | None,
    professor: Professor,
    student: Student,
) -> tuple[bool, str]:
    """Verifica API configurada e limite de tokens. Retorna (ok, motivo)."""
    if config is None or not config.has_api():
        return False, "O professor ainda não configurou uma API para este assistente."
    remaining = remaining_tokens(config, professor, student)
    if remaining is not None and remaining <= 0:
        return False, "Você atingiu o limite de tokens definido pelo professor."
    return True, ""
