import json
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from website.forms import ChatMessageForm
from website.mixins import StudentRequiredMixin
from website.models import ChatBot, Conversation, Course, Material, Message
from website.navigation import resolve_back_navigation

from .chat_service import build_answer
from .usage import can_send, can_send_from_summary, usage_summary


def _serialize_snippets(snippets):
    serialized = []
    for snippet in snippets:
        serialized.append(
            {
                "title": getattr(snippet, "title", ""),
                "excerpt": getattr(snippet, "excerpt", ""),
                "citation_id": getattr(snippet, "citation_id", ""),
                "page_or_section": getattr(snippet, "page_or_section", ""),
                "download_url": getattr(snippet, "download_url", ""),
                "material_id": getattr(snippet, "material_id", None),
                "category": getattr(snippet, "category", ""),
            }
        )
    return serialized


def _serialize_message(msg):
    return {
        "role": msg.role,
        "content": msg.content,
        "sources": msg.sources or [],
        "provider": msg.provider,
        "model": msg.model_name,
        "tokens_prompt": msg.tokens_prompt,
        "tokens_completion": msg.tokens_completion,
        "tokens_total": msg.tokens_total,
        "tokens_cached": msg.tokens_cached,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def _answer_and_store(chatbot, conversation, text, request_id=""):
    """Aplica limites, chama a IA e persiste as mensagens."""
    professor = chatbot.owner
    config = getattr(professor, "config", None)
    student = conversation.student

    ok, reason = can_send(config, professor, student)
    if not ok:
        return {"ok": False, "status": 403, "error": reason}

    result = build_answer(
        chatbot,
        text,
        include_private=True,
        config=config,
        conversation=conversation,
        request_id=request_id,
    )
    if result.error:
        return {"ok": False, "status": 502, "error": result.error}

    Message.objects.create(
        conversation=conversation,
        role=Message.ROLE_USER,
        content=text,
    )
    assistant_msg = Message.objects.create(
        conversation=conversation,
        role=Message.ROLE_ASSISTANT,
        content=result.text,
        sources=_serialize_snippets(result.snippets),
        provider=result.provider,
        model_name=result.model,
        tokens_prompt=result.tokens_prompt,
        tokens_completion=result.tokens_completion,
        tokens_total=result.tokens_total,
        tokens_cached=result.tokens_cached,
    )

    update_fields = ["updated_at"]
    if not conversation.title:
        conversation.title = text[:120]
        update_fields = ["title", "updated_at"]
    conversation.save(update_fields=update_fields)

    return {"ok": True, "status": 200, "assistant": assistant_msg}


def _student_can_use_chatbot(student, chatbot: ChatBot) -> bool:
    if chatbot.is_global:
        return True
    student_courses = {course.pk for course in student.courses.all()}
    chatbot_courses = {course.pk for course in chatbot.courses.all()}
    return bool(student_courses & chatbot_courses)


def _get_student_chatbot_or_none(student, chatbot_id):
    chatbot = get_object_or_404(
        ChatBot.objects.select_related("owner", "owner__config").prefetch_related(
            "courses"
        ),
        pk=chatbot_id,
    )
    if not _student_can_use_chatbot(student, chatbot):
        return None
    return chatbot


class StudentChatView(StudentRequiredMixin, View):
    template_name = "chat.html"

    def _history_from_conversation(self, conversation):
        if not conversation:
            return []
        return [_serialize_message(msg) for msg in conversation.messages.all()]

    def get(self, request, chatbot_id):
        student = self.get_student()
        chatbot = _get_student_chatbot_or_none(student, chatbot_id)
        if not chatbot:
            messages.error(request, "Você não tem acesso a este chatbot.")
            return redirect("student_dashboard")

        conversations = list(
            Conversation.objects.filter(student=student, chatbot=chatbot)
            .annotate(message_count=Count("messages"))
            .prefetch_related("messages")
            .order_by("-updated_at")
        )

        conv_id = request.GET.get("conversa")
        conversation = None
        if conv_id and conv_id.isdigit():
            pk = int(conv_id)
            conversation = next((item for item in conversations if item.pk == pk), None)

        professor = chatbot.owner
        config = getattr(professor, "config", None)
        summary = usage_summary(config, professor, student)
        can_chat, block_reason = can_send_from_summary(config, summary)
        back_url, back_label = resolve_back_navigation(
            request,
            fallback_url=reverse("student_dashboard"),
            fallback_label="Painel",
        )

        return render(
            request,
            self.template_name,
            {
                "student": student,
                "chatbot": chatbot,
                "professor": professor,
                "conversations": conversations,
                "conversation": conversation,
                "history": self._history_from_conversation(conversation),
                "form": ChatMessageForm(),
                "can_chat": can_chat,
                "block_reason": block_reason,
                "usage": summary,
                "back_url": back_url,
                "back_label": back_label,
            },
        )


class StudentConversationCreateView(StudentRequiredMixin, View):
    """Cria uma conversa vazia (AJAX) antes do aluno enviar a primeira mensagem."""

    def post(self, request, chatbot_id):
        student = self.get_student()
        chatbot = _get_student_chatbot_or_none(student, chatbot_id)
        if not chatbot:
            return JsonResponse(
                {"error": "Sem permissão para acessar este chatbot."}, status=403
            )
        conversation = Conversation.objects.create(student=student, chatbot=chatbot)
        return JsonResponse(
            {
                "conversation_id": conversation.pk,
                "title": conversation.title or "Nova conversa",
            }
        )


class StudentConversationMessagesView(StudentRequiredMixin, View):
    """Retorna as mensagens de uma conversa do aluno (AJAX)."""

    def get(self, request, chatbot_id, conversation_id):
        student = self.get_student()
        chatbot = _get_student_chatbot_or_none(student, chatbot_id)
        if not chatbot:
            return JsonResponse(
                {"error": "Sem permissão para acessar este chatbot."}, status=403
            )
        conversation = get_object_or_404(
            Conversation, pk=conversation_id, student=student, chatbot=chatbot
        )
        messages_data = [_serialize_message(msg) for msg in conversation.messages.all()]
        return JsonResponse(
            {
                "conversation_id": conversation.pk,
                "title": conversation.title or "Conversa",
                "messages": messages_data,
            }
        )


class StudentChatSendView(StudentRequiredMixin, View):
    def post(self, request, chatbot_id):
        student = self.get_student()
        chatbot = _get_student_chatbot_or_none(student, chatbot_id)
        if not chatbot:
            return JsonResponse(
                {"error": "Sem permissão para acessar este chatbot."}, status=403
            )

        payload = request.POST.dict()
        if not payload and request.body:
            try:
                payload = json.loads(request.body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = {}

        conversation_id = payload.get("conversa")
        if conversation_id and str(conversation_id).isdigit():
            conversation = Conversation.objects.select_related("student").filter(
                pk=int(conversation_id), student=student, chatbot=chatbot
            ).first()
            if not conversation:
                return JsonResponse({"error": "Conversa não encontrada."}, status=404)
        else:
            conversation = Conversation.objects.create(student=student, chatbot=chatbot)

        form = ChatMessageForm(payload or None)
        if not form.is_valid():
            return JsonResponse({"error": "Mensagem inválida."}, status=400)

        text = form.cleaned_data["message"].strip()
        if not text:
            return JsonResponse({"error": "Mensagem vazia."}, status=400)

        request_id = (
            request.headers.get("X-Request-ID") or payload.get("request_id") or ""
        )
        outcome = _answer_and_store(
            chatbot, conversation, text, request_id=request_id
        )
        if not outcome["ok"]:
            return JsonResponse({"error": outcome["error"]}, status=outcome["status"])

        assistant = outcome["assistant"]
        professor = chatbot.owner
        config = getattr(professor, "config", None)
        summary = usage_summary(config, professor, student)
        data = _serialize_message(assistant)
        data.update(
            {
                "reply": assistant.content,
                "conversation_id": conversation.pk,
                "conversation_title": conversation.title,
                "usage": summary,
            }
        )
        return JsonResponse(data)


class StudentMaterialDownloadView(StudentRequiredMixin, View):
    """Download de documentos citados no chat, só com vínculo ao curso ou chatbot."""

    def get(self, request, material_id):
        student = self.get_student()
        material = get_object_or_404(Material, pk=material_id)

        student_courses = set(student.courses.values_list("pk", flat=True))
        material_courses = set(material.courses.values_list("pk", flat=True))
        chatbot_courses = set(
            Course.objects.filter(
                chatbots__materials=material,
                chatbots__is_global=False,
            ).values_list("pk", flat=True)
        )
        used_by_global_chatbot = ChatBot.objects.filter(
            is_global=True,
            materials=material,
        ).exists()

        has_access = used_by_global_chatbot or bool(
            student_courses & (material_courses | chatbot_courses)
        )
        if not has_access:
            raise PermissionDenied("Você não tem permissão para acessar este material.")

        if not material.file:
            raise Http404("Este material não possui arquivo para download.")

        filename = Path(material.file.name).name
        try:
            return FileResponse(
                material.file.open("rb"),
                as_attachment=True,
                filename=filename,
            )
        except Exception:
            raise Http404("Arquivo não encontrado no armazenamento.")
