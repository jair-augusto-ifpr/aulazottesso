from django.contrib import admin

from .models import ChatBot, Course, Material, Professor, Student
from .passwords import looks_hashed, set_password


class _HashPasswordOnSaveMixin:
    """Se o campo `password` foi preenchido com texto puro, hashea antes de salvar."""

    def save_model(self, request, obj, form, change):
        raw = getattr(obj, "password", "") or ""
        if raw and not looks_hashed(raw):
            set_password(obj, raw)
        super().save_model(request, obj, form, change)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Professor)
class ProfessorAdmin(_HashPasswordOnSaveMixin, admin.ModelAdmin):
    list_display = ("name", "siape", "email")
    search_fields = ("name", "siape", "email")
    filter_horizontal = ("courses",)


@admin.register(Student)
class StudentAdmin(_HashPasswordOnSaveMixin, admin.ModelAdmin):
    list_display = ("name", "ra", "email")
    search_fields = ("name", "ra", "email")
    filter_horizontal = ("courses",)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "public", "file")
    list_filter = ("public",)
    search_fields = ("title", "text_content")
    filter_horizontal = ("courses",)


@admin.register(ChatBot)
class ChatBotAdmin(admin.ModelAdmin):
    list_display = ("id", "professor", "prompt")
    list_filter = ("professor",)
    search_fields = ("prompt",)
    filter_horizontal = ("materials", "courses")
