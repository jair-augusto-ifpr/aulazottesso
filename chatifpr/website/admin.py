from django.contrib import admin

from .models import (
    ChatBot,
    Conversation,
    Course,
    Material,
    Message,
    Professor,
    ProfessorConfig,
    Student,
)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Professor)
class ProfessorAdmin(admin.ModelAdmin):
    list_display = ("name", "siape", "user")
    list_select_related = ("user",)
    search_fields = ("name", "siape", "user__username", "user__email")
    filter_horizontal = ("courses",)
    raw_id_fields = ("user",)


@admin.register(ProfessorConfig)
class ProfessorConfigAdmin(admin.ModelAdmin):
    list_display = (
        "professor",
        "provider",
        "model",
        "token_limit_per_student",
        "limit_period_days",
    )
    list_select_related = ("professor",)
    list_filter = ("provider",)
    search_fields = ("professor__name",)
    raw_id_fields = ("professor",)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "ra", "phone", "user")
    list_select_related = ("user",)
    search_fields = ("name", "ra", "user__username", "user__email")
    filter_horizontal = ("courses",)
    raw_id_fields = ("user",)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "owner", "public", "created_at")
    list_select_related = ("owner",)
    list_filter = ("public", "owner")
    search_fields = ("title", "text_content")
    filter_horizontal = ("courses",)
    raw_id_fields = ("owner",)


@admin.register(ChatBot)
class ChatBotAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "created_at")
    list_select_related = ("owner",)
    list_filter = ("owner",)
    search_fields = ("prompt", "owner__name")
    filter_horizontal = ("materials", "courses")
    raw_id_fields = ("owner",)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "chatbot", "title", "updated_at")
    list_select_related = ("student", "chatbot", "chatbot__owner")
    list_filter = ("chatbot",)
    search_fields = ("title", "student__name")
    raw_id_fields = ("student", "chatbot")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conversation",
        "role",
        "model_name",
        "tokens_total",
        "created_at",
    )
    list_select_related = ("conversation",)
    list_filter = ("role", "provider")
    search_fields = ("content", "model_name")
    raw_id_fields = ("conversation",)
