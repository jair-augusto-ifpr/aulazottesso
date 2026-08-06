import json

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group, User
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from .chat_service import build_answer
from .constants import GROUP_ALUNO, GROUP_PROFESSOR
from .forms import (
    ChatBotForm,
    ChatMessageForm,
    CourseForm,
    MaterialForm,
    PortalPasswordChangeForm,
    ProfessorConfigForm,
    ProfessorLoginForm,
    ProfessorSignupForm,
    StudentLoginForm,
    StudentSignupForm,
)
from .mixins import (
    FormTemplateMixin,
    NavBackMixin,
    ProfessorOwnerQuerysetMixin,
    ProfessorRequiredMixin,
    StudentOwnerQuerysetMixin,
    StudentRequiredMixin,
)
from .navigation import get_nav_from_param, resolve_back_navigation
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
from .text_extraction import apply_material_text_extraction
from .usage import can_send, consumed_tokens, usage_summary


def _serialize_snippets(snippets):
    return [{"title": s.title, "excerpt": s.excerpt} for s in snippets]


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


def _answer_and_store(chatbot, conversation, text):
    """Aplica limites, chama a IA e persiste as mensagens. Retorna dict de resultado."""
    professor = chatbot.owner
    config = getattr(professor, "config", None)
    student = conversation.student

    ok, reason = can_send(config, professor, student)
    if not ok:
        return {"ok": False, "status": 403, "error": reason}

    result = build_answer(chatbot, text, include_private=True, config=config)
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


def _student_can_use_chatbot(student: Student, chatbot: ChatBot) -> bool:
    sc = set(student.courses.values_list("pk", flat=True))
    bc = set(chatbot.courses.values_list("pk", flat=True))
    return bool(sc & bc)


# ---------------------------------------------------------------------------
# Páginas públicas
# ---------------------------------------------------------------------------


class IndexView(TemplateView):
    template_name = "website/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["stats"] = {
            "courses": Course.objects.count(),
            "materials": Material.objects.filter(public=True).count(),
            "chatbots": ChatBot.objects.count(),
            "conversations": Conversation.objects.count(),
        }
        ctx["recent_chatbots"] = (
            ChatBot.objects.select_related("owner")
            .prefetch_related("courses")
            .order_by("-created_at")[:5]
        )
        return ctx


class SobreView(TemplateView):
    template_name = "website/sobre.html"


class ContatoView(TemplateView):
    template_name = "website/contato.html"


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------


class StudentLoginView(LoginView):
    template_name = "website/estudante/login.html"
    authentication_form = StudentLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy("student_dashboard")


class ProfessorLoginView(LoginView):
    template_name = "website/professor/login.html"
    authentication_form = ProfessorLoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy("professor_dashboard")


class PortalLogoutView(LogoutView):
    next_page = "home"


class PortalPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    form_class = PortalPasswordChangeForm
    template_name = "website/form.html"
    success_url = reverse_lazy("home")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_title"] = "Alterar senha"
        ctx["submit_label"] = "Atualizar senha"
        ctx["cancel_url"] = reverse("home")
        user = self.request.user
        if user.groups.filter(name=GROUP_PROFESSOR).exists():
            fallback = reverse("professor_dashboard")
            fallback_label = "Painel"
        elif user.groups.filter(name=GROUP_ALUNO).exists():
            fallback = reverse("student_dashboard")
            fallback_label = "Painel"
        else:
            fallback = reverse("home")
            fallback_label = "Início"
        back_url, back_label = resolve_back_navigation(
            self.request,
            fallback_url=fallback,
            fallback_label=fallback_label,
        )
        ctx["back_url"] = back_url
        ctx["back_label"] = back_label
        ctx["nav_from"] = get_nav_from_param(self.request, back_url)
        return ctx

    def form_valid(self, form):
        messages.success(self.request, "Senha alterada com sucesso.")
        return super().form_valid(form)


class StudentSignupView(CreateView):
    model = Student
    template_name = "website/estudante/signup.html"
    form_class = StudentSignupForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("student_dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        ra = form.cleaned_data["ra"]

        user = User.objects.create_user(
            username=ra,
            email=email,
            password=password,
        )
        group, _ = Group.objects.get_or_create(name=GROUP_ALUNO)
        user.groups.add(group)

        student = form.save(commit=False)
        student.user = user
        student.save()
        form.save_m2m()

        login(self.request, user)
        messages.success(self.request, "Cadastro concluído. Bem-vindo(a).")
        return redirect("student_dashboard")


class ProfessorSignupView(CreateView):
    model = Professor
    template_name = "website/professor/signup.html"
    form_class = ProfessorSignupForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("professor_dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        siape = form.cleaned_data["siape"]

        user = User.objects.create_user(
            username=siape,
            email=email,
            password=password,
        )
        group, _ = Group.objects.get_or_create(name=GROUP_PROFESSOR)
        user.groups.add(group)

        professor = form.save(commit=False)
        professor.user = user
        professor.save()
        form.save_m2m()

        login(self.request, user)
        messages.success(self.request, "Cadastro concluído. Bem-vindo(a).")
        return redirect("professor_dashboard")


# ---------------------------------------------------------------------------
# Estudante
# ---------------------------------------------------------------------------


class StudentDashboardView(StudentRequiredMixin, TemplateView):
    template_name = "website/estudante/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        student = self.get_student()
        rows = []
        for course in student.courses.prefetch_related("chatbots").all():
            rows.append(
                {
                    "course": course,
                    "chatbots": course.chatbots.select_related("owner").all(),
                }
            )
        ctx["student"] = student
        ctx["rows"] = rows
        return ctx


class StudentConversationListView(
    NavBackMixin, StudentOwnerQuerysetMixin, StudentRequiredMixin, ListView
):
    model = Conversation
    template_name = "website/estudante/conversation_list.html"
    context_object_name = "conversations"
    paginate_by = 10
    nav_back_url_name = "student_dashboard"
    nav_back_label = "Painel"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("chatbot", "chatbot__owner")
            .annotate(message_count=Count("messages"))
            .order_by("-updated_at")
        )


class StudentConversationDeleteView(
    NavBackMixin,
    StudentOwnerQuerysetMixin,
    StudentRequiredMixin,
    DeleteView,
):
    model = Conversation
    template_name = "website/confirm_delete.html"
    context_object_name = "object"
    success_url = reverse_lazy("student_conversation_list")
    nav_back_url_name = "student_conversation_list"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["delete_title"] = "Excluir conversa"
        ctx["delete_message"] = (
            "Tem certeza que deseja excluir esta conversa e todas as mensagens?"
        )
        ctx["cancel_url"] = reverse("student_conversation_list")
        return ctx


def _get_student_chatbot_or_none(request, student, chatbot_id):
    chatbot = get_object_or_404(
        ChatBot.objects.select_related("owner").prefetch_related("courses"),
        pk=chatbot_id,
    )
    if not _student_can_use_chatbot(student, chatbot):
        return None
    return chatbot


class StudentChatView(StudentRequiredMixin, View):
    template_name = "website/estudante/chat.html"

    def _history_from_conversation(self, conversation):
        if not conversation:
            return []
        history = []
        for msg in conversation.messages.all():
            history.append(_serialize_message(msg))
        return history

    def get(self, request, chatbot_id):
        student = self.get_student()
        chatbot = _get_student_chatbot_or_none(request, student, chatbot_id)
        if not chatbot:
            messages.error(request, "Você não tem acesso a este chatbot.")
            return redirect("student_dashboard")

        conversations = Conversation.objects.filter(
            student=student, chatbot=chatbot
        ).annotate(message_count=Count("messages")).order_by("-updated_at")

        conv_id = request.GET.get("conversa")
        conversation = None
        if conv_id and conv_id.isdigit():
            conversation = conversations.filter(pk=int(conv_id)).first()

        professor = chatbot.owner
        config = getattr(professor, "config", None)
        can_chat, block_reason = can_send(config, professor, student)
        summary = usage_summary(config, professor, student)
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
        chatbot = _get_student_chatbot_or_none(request, student, chatbot_id)
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
    """Retorna as mensagens de uma conversa do aluno (AJAX) para trocar sem recarregar."""

    def get(self, request, chatbot_id, conversation_id):
        student = self.get_student()
        chatbot = _get_student_chatbot_or_none(request, student, chatbot_id)
        if not chatbot:
            return JsonResponse(
                {"error": "Sem permissão para acessar este chatbot."}, status=403
            )
        conversation = get_object_or_404(
            Conversation, pk=conversation_id, student=student, chatbot=chatbot
        )
        messages_data = [
            _serialize_message(m) for m in conversation.messages.all()
        ]
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
        chatbot = _get_student_chatbot_or_none(request, student, chatbot_id)
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
        conversation = None
        if conversation_id and str(conversation_id).isdigit():
            conversation = Conversation.objects.filter(
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

        outcome = _answer_and_store(chatbot, conversation, text)
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


# ---------------------------------------------------------------------------
# Professor — Cursos
# ---------------------------------------------------------------------------


class CourseListView(NavBackMixin, ProfessorRequiredMixin, ListView):
    model = Course
    template_name = "website/professor/course_list.html"
    context_object_name = "courses"
    paginate_by = 10
    nav_back_url_name = "professor_dashboard"
    nav_back_label = "Painel"

    def get_queryset(self):
        return Course.objects.annotate(
            material_count=Count("materials", distinct=True),
            chatbot_count=Count("chatbots", distinct=True),
        )


class CourseCreateView(FormTemplateMixin, ProfessorRequiredMixin, CreateView):
    model = Course
    form_class = CourseForm
    form_title = "Novo curso"
    submit_label = "Cadastrar curso"
    cancel_url_name = "professor_course_list"
    success_url = reverse_lazy("professor_course_list")


class CourseUpdateView(FormTemplateMixin, ProfessorRequiredMixin, UpdateView):
    model = Course
    form_class = CourseForm
    form_title = "Editar curso"
    submit_label = "Salvar curso"
    cancel_url_name = "professor_course_list"
    success_url = reverse_lazy("professor_course_list")


class CourseDeleteView(NavBackMixin, ProfessorRequiredMixin, DeleteView):
    model = Course
    template_name = "website/confirm_delete.html"
    success_url = reverse_lazy("professor_course_list")
    nav_back_url_name = "professor_course_list"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["delete_title"] = "Excluir curso"
        ctx["delete_message"] = (
            f"Tem certeza que deseja excluir o curso «{self.object.name}»?"
        )
        ctx["cancel_url"] = reverse("professor_course_list")
        return ctx


class CourseDetailView(NavBackMixin, ProfessorRequiredMixin, DetailView):
    model = Course
    template_name = "website/professor/course_detail.html"
    context_object_name = "course"
    nav_back_url_name = "professor_course_list"
    nav_back_label = "Cursos"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        course = self.object
        ctx["materials"] = course.materials.select_related("owner")[:10]
        ctx["chatbots"] = course.chatbots.select_related("owner")[:10]
        return ctx


# ---------------------------------------------------------------------------
# Professor — Materiais
# ---------------------------------------------------------------------------


class MaterialListView(
    NavBackMixin, ProfessorOwnerQuerysetMixin, ProfessorRequiredMixin, ListView
):
    model = Material
    template_name = "website/professor/material_list.html"
    context_object_name = "materials"
    paginate_by = 10
    nav_back_url_name = "professor_dashboard"
    nav_back_label = "Painel"

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("owner")
            .prefetch_related("courses")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(text_content__icontains=q)
                | Q(courses__name__icontains=q)
            ).distinct()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "").strip()
        return ctx


class MaterialDetailView(
    NavBackMixin, ProfessorOwnerQuerysetMixin, ProfessorRequiredMixin, DetailView
):
    model = Material
    template_name = "website/professor/material_detail.html"
    context_object_name = "material"
    nav_back_url_name = "professor_material_list"
    nav_back_label = "Materiais"


class MaterialCreateView(FormTemplateMixin, ProfessorRequiredMixin, CreateView):
    model = Material
    form_class = MaterialForm
    form_title = "Novo material"
    submit_label = "Cadastrar material"
    cancel_url_name = "professor_material_list"
    success_url = reverse_lazy("professor_material_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["professor"] = self.get_professor()
        return kwargs

    def form_valid(self, form):
        form.instance.owner = self.get_professor()
        response = super().form_valid(form)
        material = self.object
        chars = apply_material_text_extraction(material, prefer_file=bool(material.file))
        if chars:
            messages.info(
                self.request,
                f"Texto extraído automaticamente do arquivo: {chars} caracteres.",
            )
        elif material.file and not (material.text_content or "").strip():
            messages.warning(
                self.request,
                "Arquivo anexado, mas não foi possível extrair texto. "
                "Use PDF com texto selecionável ou preencha o campo de texto manualmente.",
            )
        messages.success(self.request, "Material cadastrado.")
        return response


class MaterialUpdateView(
    ProfessorOwnerQuerysetMixin, FormTemplateMixin, ProfessorRequiredMixin, UpdateView
):
    model = Material
    form_class = MaterialForm
    form_title = "Editar material"
    submit_label = "Salvar material"
    cancel_url_name = "professor_material_list"
    success_url = reverse_lazy("professor_material_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["professor"] = self.get_professor()
        return kwargs

    def form_valid(self, form):
        material = form.save(commit=False)
        previous_file = ""
        if material.pk:
            previous_file = (
                Material.objects.filter(pk=material.pk)
                .values_list("file", flat=True)
                .first()
                or ""
            )
        material.save()
        form.save_m2m()
        file_changed = (material.file.name or "") != previous_file
        chars = apply_material_text_extraction(
            material, prefer_file=file_changed or bool(material.file)
        )
        if chars:
            messages.info(
                self.request,
                f"Texto extraído automaticamente do arquivo: {chars} caracteres.",
            )
        elif material.file and file_changed and not (material.text_content or "").strip():
            messages.warning(
                self.request,
                "Arquivo anexado, mas não foi possível extrair texto. "
                "Use PDF com texto selecionável ou preencha o campo de texto manualmente.",
            )
        messages.success(self.request, "Material atualizado.")
        return redirect(self.get_success_url())


class MaterialDeleteView(
    NavBackMixin, ProfessorOwnerQuerysetMixin, ProfessorRequiredMixin, DeleteView
):
    model = Material
    template_name = "website/confirm_delete.html"
    success_url = reverse_lazy("professor_material_list")
    nav_back_url_name = "professor_material_list"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["delete_title"] = "Excluir material"
        ctx["delete_message"] = (
            f"Tem certeza que deseja excluir «{self.object}»?"
        )
        ctx["cancel_url"] = reverse("professor_material_list")
        return ctx


# ---------------------------------------------------------------------------
# Professor — Chatbots
# ---------------------------------------------------------------------------


class ProfessorDashboardView(ProfessorRequiredMixin, TemplateView):
    template_name = "website/professor/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        professor = self.get_professor()
        ctx["professor"] = professor
        ctx["chatbots"] = (
            professor.chatbots.select_related("owner")
            .prefetch_related("materials", "courses")
            .all()
        )
        ctx["material_count"] = professor.materials.count()
        config = getattr(professor, "config", None)
        ctx["config"] = config
        ctx["has_api"] = bool(config and config.has_api())
        ctx["conversation_count"] = Conversation.objects.filter(
            chatbot__owner=professor
        ).count()
        return ctx


class ChatBotListView(
    NavBackMixin, ProfessorOwnerQuerysetMixin, ProfessorRequiredMixin, ListView
):
    model = ChatBot
    template_name = "website/professor/chatbot_list.html"
    context_object_name = "chatbots"
    paginate_by = 10
    nav_back_url_name = "professor_dashboard"
    nav_back_label = "Painel"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("owner")
            .prefetch_related("courses", "materials")
            .annotate(material_count=Count("materials", distinct=True))
        )


class ChatBotDetailView(
    NavBackMixin, ProfessorOwnerQuerysetMixin, ProfessorRequiredMixin, DetailView
):
    model = ChatBot
    template_name = "website/professor/chatbot_detail.html"
    context_object_name = "chatbot"
    nav_back_url_name = "professor_chatbot_list"
    nav_back_label = "Chatbots"

    def get_queryset(self):
        return super().get_queryset().prefetch_related("materials", "courses")


class ChatBotCreateView(FormTemplateMixin, ProfessorRequiredMixin, CreateView):
    model = ChatBot
    form_class = ChatBotForm
    form_title = "Novo chatbot"
    submit_label = "Criar chatbot"
    cancel_url_name = "professor_chatbot_list"
    success_url = reverse_lazy("professor_chatbot_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["professor"] = self.get_professor()
        return kwargs

    def form_valid(self, form):
        form.instance.owner = self.get_professor()
        messages.success(self.request, "Chatbot criado.")
        return super().form_valid(form)


class ChatBotUpdateView(
    ProfessorOwnerQuerysetMixin, FormTemplateMixin, ProfessorRequiredMixin, UpdateView
):
    model = ChatBot
    form_class = ChatBotForm
    form_title = "Editar chatbot"
    submit_label = "Salvar chatbot"
    cancel_url_name = "professor_chatbot_list"
    success_url = reverse_lazy("professor_chatbot_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["professor"] = self.get_professor()
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Chatbot atualizado.")
        return super().form_valid(form)


class ChatBotDeleteView(
    NavBackMixin, ProfessorOwnerQuerysetMixin, ProfessorRequiredMixin, DeleteView
):
    model = ChatBot
    template_name = "website/confirm_delete.html"
    success_url = reverse_lazy("professor_chatbot_list")
    nav_back_url_name = "professor_chatbot_list"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["delete_title"] = "Excluir chatbot"
        ctx["delete_message"] = "Tem certeza que deseja excluir este chatbot?"
        ctx["cancel_url"] = reverse("professor_chatbot_list")
        return ctx


# ---------------------------------------------------------------------------
# Professor — Configuração de API
# ---------------------------------------------------------------------------


class ProfessorConfigUpdateView(FormTemplateMixin, ProfessorRequiredMixin, UpdateView):
    model = ProfessorConfig
    form_class = ProfessorConfigForm
    form_title = "Configuração de API"
    submit_label = "Salvar configuração"
    cancel_url_name = "professor_dashboard"
    success_url = reverse_lazy("professor_dashboard")

    def get_object(self, queryset=None):
        professor = self.get_professor()
        config, _ = ProfessorConfig.objects.get_or_create(professor=professor)
        return config

    def form_valid(self, form):
        messages.success(self.request, "Configuração salva.")
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Professor — Monitoramento de conversas (somente leitura)
# ---------------------------------------------------------------------------


class ProfessorConversationListView(NavBackMixin, ProfessorRequiredMixin, ListView):
    model = Conversation
    template_name = "website/professor/conversation_list.html"
    context_object_name = "conversations"
    paginate_by = 10
    nav_back_url_name = "professor_dashboard"
    nav_back_label = "Painel"

    def get_queryset(self):
        professor = self.get_professor()
        qs = (
            Conversation.objects.filter(chatbot__owner=professor)
            .select_related("student", "chatbot", "chatbot__owner")
            .annotate(
                message_count=Count("messages"),
                tokens=Sum("messages__tokens_total"),
            )
            .order_by("-updated_at")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(student__name__icontains=q)
                | Q(student__ra__icontains=q)
                | Q(title__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        professor = self.get_professor()
        ctx["search_query"] = self.request.GET.get("q", "").strip()
        ctx["config"] = getattr(professor, "config", None)
        ctx["student_usage"] = (
            Message.objects.filter(
                role=Message.ROLE_ASSISTANT,
                conversation__chatbot__owner=professor,
            )
            .values(
                "conversation__student__id",
                "conversation__student__name",
                "conversation__student__ra",
            )
            .annotate(tokens=Sum("tokens_total"), replies=Count("id"))
            .order_by("-tokens")
        )
        return ctx


class ProfessorConversationDetailView(ProfessorRequiredMixin, DetailView):
    model = Conversation
    template_name = "website/professor/conversation_detail.html"
    context_object_name = "conversation"

    def get_queryset(self):
        professor = self.get_professor()
        return Conversation.objects.filter(
            chatbot__owner=professor
        ).select_related("student", "chatbot")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        conversation = self.object
        professor = self.get_professor()
        ctx["messages_list"] = conversation.messages.all()
        ctx["tokens_total"] = (
            conversation.messages.aggregate(t=Sum("tokens_total"))["t"] or 0
        )
        ctx["sidebar_conversations"] = (
            Conversation.objects.filter(chatbot__owner=professor)
            .select_related("student", "chatbot")
            .annotate(message_count=Count("messages"))
            .order_by("-updated_at")[:80]
        )
        return ctx
