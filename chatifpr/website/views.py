from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group, User
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.db.models import Count, Prefetch, Sum
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from ia.document_processing import index_material
from ia.text_extraction import apply_material_text_extraction

from .constants import GROUP_ALUNO, GROUP_PROFESSOR
from .filters import ConversationFilter, MaterialFilter
from .forms import (
    ChatBotForm,
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
from .navigation import get_nav_from_param
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

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and not hasattr(user, "student_profile"):
            self.redirect_authenticated_user = False
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy("student_dashboard")


class ProfessorLoginView(LoginView):
    template_name = "website/professor/login.html"
    authentication_form = ProfessorLoginForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if user.is_authenticated and not hasattr(user, "professor_profile"):
            self.redirect_authenticated_user = False
        return super().dispatch(request, *args, **kwargs)

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
        if request.user.is_authenticated and hasattr(request.user, "student_profile"):
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
        if request.user.is_authenticated and hasattr(request.user, "professor_profile"):
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
        courses = student.courses.prefetch_related(
            Prefetch(
                "chatbots",
                queryset=ChatBot.objects.filter(is_global=False).select_related(
                    "owner"
                ),
            )
        )
        ctx["student"] = student
        ctx["global_chatbots"] = ChatBot.objects.filter(is_global=True).select_related(
            "owner"
        )
        ctx["rows"] = [
            {"course": course, "chatbots": course.chatbots.all()}
            for course in courses
        ]
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
            .select_related("student", "chatbot", "chatbot__owner")
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
        ctx["chatbots"] = course.chatbots.filter(is_global=False).select_related(
            "owner"
        )[:10]
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
        self.filterset = MaterialFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter"] = getattr(self, "filterset", None)
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

    def get_queryset(self):
        return super().get_queryset().with_related()


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
        index_res = index_material(material, force=True)
        if index_res.get("chunk_count"):
            messages.info(
                self.request,
                f"Indexação documental concluída: {index_res['chunk_count']} trecho(s) particionado(s).",
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

    def get_queryset(self):
        return super().get_queryset().prefetch_related("courses")

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
        index_res = index_material(material, force=file_changed)
        if index_res.get("chunk_count") and index_res.get("updated"):
            messages.info(
                self.request,
                f"Índice documental atualizado: {index_res['chunk_count']} trecho(s).",
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
            .prefetch_related("courses")
            .annotate(material_count=Count("materials", distinct=True))
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
            .prefetch_related("courses")
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
        return (
            super()
            .get_queryset()
            .with_list_related()
        )


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

    def get_queryset(self):
        return super().get_queryset().with_related()

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
        self.filterset = ConversationFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        professor = self.get_professor()
        ctx["filter"] = getattr(self, "filterset", None)
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
        return (
            Conversation.objects.filter(chatbot__owner=professor)
            .with_related()
            .prefetch_related("messages")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        conversation = self.object
        professor = self.get_professor()
        messages_list = list(conversation.messages.all())
        ctx["messages_list"] = messages_list
        ctx["tokens_total"] = sum(m.tokens_total for m in messages_list)
        ctx["sidebar_conversations"] = (
            Conversation.objects.filter(chatbot__owner=professor)
            .select_related("student")
            .annotate(message_count=Count("messages"))
            .order_by("-updated_at")[:80]
        )
        return ctx
