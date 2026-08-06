from braces.views import GroupRequiredMixin
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404

from .constants import GROUP_ALUNO, GROUP_PROFESSOR
from .models import Professor, Student
from .navigation import get_nav_from_param, resolve_back_navigation


class ProfessorRequiredMixin(LoginRequiredMixin, GroupRequiredMixin):
    group_required = GROUP_PROFESSOR
    login_url = "professor_login"

    def get_professor(self) -> Professor:
        return get_object_or_404(Professor, user=self.request.user)


class StudentRequiredMixin(LoginRequiredMixin, GroupRequiredMixin):
    group_required = GROUP_ALUNO
    login_url = "student_login"

    def get_student(self) -> Student:
        return get_object_or_404(Student, user=self.request.user)


class ProfessorOwnerQuerysetMixin:
    """Restringe queryset aos registros do professor autenticado."""

    owner_field = "owner"

    def get_queryset(self):
        qs = super().get_queryset()
        professor = self.get_professor()
        return qs.filter(**{self.owner_field: professor})


class StudentOwnerQuerysetMixin:
    """Restringe queryset aos registros do aluno autenticado."""

    student_field = "student"

    def get_queryset(self):
        qs = super().get_queryset()
        student = self.get_student()
        return qs.filter(**{self.student_field: student})


class NavBackMixin:
    """Injeta back_url/back_label com base na tela anterior (from ou Referer)."""

    nav_back_url_name = None
    nav_back_label = "Voltar"
    nav_back_fixed = False

    def get_nav_back_fallback_url(self):
        from django.urls import reverse

        cancel_name = getattr(self, "cancel_url_name", None)
        if cancel_name:
            return reverse(cancel_name)

        name = getattr(self, "nav_back_url_name", None) or getattr(
            self, "back_url_name", None
        )
        if name:
            return reverse(name)
        return None

    def get_nav_back_label(self) -> str:
        return getattr(self, "nav_back_label", None) or getattr(
            self, "back_label", "Voltar"
        )

    def apply_nav_back_context(self, ctx):
        fallback = self.get_nav_back_fallback_url()
        fallback_label = self.get_nav_back_label()
        if getattr(self, "nav_back_fixed", False) and fallback:
            back_url, back_label = fallback, fallback_label
        else:
            back_url, back_label = resolve_back_navigation(
                self.request,
                fallback_url=fallback,
                fallback_label=fallback_label,
            )
        ctx["back_url"] = back_url
        ctx["back_label"] = back_label
        ctx["nav_from"] = get_nav_from_param(self.request, back_url)
        return ctx

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        return self.apply_nav_back_context(ctx)


class FormTemplateMixin(NavBackMixin):
    """Reutiliza o template genérico de formulário com título dinâmico."""

    template_name = "website/form.html"
    cancel_url_name = None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = self.get_form_title()
        ctx["submit_label"] = self.get_submit_label()
        from django.urls import reverse

        if self.cancel_url_name:
            ctx["cancel_url"] = reverse(self.cancel_url_name)
        return ctx

    def get_form_title(self) -> str:
        return getattr(self, "form_title", "Formulário")

    def get_submit_label(self) -> str:
        return getattr(self, "submit_label", "Salvar")
