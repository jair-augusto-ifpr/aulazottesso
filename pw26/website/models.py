from django.conf import settings
from django.db import models


class Course(models.Model):
    """Curso: eixo central dos relacionamentos N:N do diagrama."""

    name = models.CharField("nome", max_length=50)

    class Meta:
        verbose_name = "curso"
        verbose_name_plural = "cursos"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Professor(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="professor_profile",
        verbose_name="usuário",
    )
    name = models.CharField("nome", max_length=50)
    siape = models.CharField("SIAPE", max_length=50, unique=True)
    courses = models.ManyToManyField(
        Course,
        related_name="professors",
        verbose_name="cursos",
        blank=True,
    )

    class Meta:
        verbose_name = "professor"
        verbose_name_plural = "professores"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ProfessorConfig(models.Model):
    """Configuração de API própria do professor e limites de uso por aluno."""

    PROVIDER_GEMINI = "gemini"
    PROVIDER_OPENROUTER = "openrouter"
    PROVIDER_CHOICES = [
        (PROVIDER_GEMINI, "Google Gemini"),
        (PROVIDER_OPENROUTER, "OpenRouter"),
    ]

    professor = models.OneToOneField(
        Professor,
        on_delete=models.CASCADE,
        related_name="config",
        verbose_name="professor",
    )
    provider = models.CharField(
        "provedor",
        max_length=20,
        choices=PROVIDER_CHOICES,
        blank=True,
    )
    api_key = models.CharField("chave da API", max_length=255, blank=True)
    model = models.CharField("modelo", max_length=120, blank=True)
    token_limit_per_student = models.PositiveIntegerField(
        "limite de tokens por aluno",
        default=0,
        help_text="0 = ilimitado.",
    )
    limit_period_days = models.PositiveIntegerField(
        "período do limite (dias)",
        default=0,
        help_text="0 = acumulado total (sem reinício).",
    )
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "configuração do professor"
        verbose_name_plural = "configurações dos professores"

    def __str__(self) -> str:
        return f"Config de {self.professor.name}"

    def has_api(self) -> bool:
        return bool(self.provider and self.api_key.strip() and self.model.strip())


class Student(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
        verbose_name="usuário",
    )
    name = models.CharField("nome", max_length=50)
    ra = models.CharField("RA", max_length=50, unique=True)
    phone = models.CharField("telefone", max_length=20, blank=True)
    courses = models.ManyToManyField(
        Course,
        related_name="students",
        verbose_name="cursos",
        blank=True,
    )

    class Meta:
        verbose_name = "aluno"
        verbose_name_plural = "alunos"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Material(models.Model):
    """Documento institucional indexado para recuperação textual."""

    owner = models.ForeignKey(
        Professor,
        on_delete=models.CASCADE,
        related_name="materials",
        verbose_name="professor",
    )
    title = models.CharField("título", max_length=200, blank=True)
    text_content = models.TextField("texto para busca", blank=True)
    file = models.FileField("arquivo", upload_to="materiais/%Y/%m/", blank=True)
    public = models.BooleanField("tornar público", default=True)
    courses = models.ManyToManyField(
        Course,
        related_name="materials",
        verbose_name="cursos",
        blank=True,
    )
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "material"
        verbose_name_plural = "materiais"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        if self.title:
            return self.title
        return self.file.name or f"Material #{self.pk}"


class ChatBot(models.Model):
    owner = models.ForeignKey(
        Professor,
        on_delete=models.CASCADE,
        related_name="chatbots",
        verbose_name="professor",
    )
    prompt = models.CharField("prompt", max_length=2000)
    materials = models.ManyToManyField(
        Material,
        related_name="chatbots",
        verbose_name="materiais",
        blank=True,
    )
    courses = models.ManyToManyField(
        Course,
        related_name="chatbots",
        verbose_name="cursos",
        blank=True,
    )
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "chatbot"
        verbose_name_plural = "chatbots"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"ChatBot de {self.owner.name}"

    @property
    def professor(self):
        """Compatibilidade com chat_service e templates legados."""
        return self.owner

    @property
    def assistant_title(self) -> str:
        name = self.owner.name.strip()
        if name.lower() == "secretaria":
            return "Assistente da Secretaria"
        return f"Assistente de {name}"


class Conversation(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="conversations",
        verbose_name="aluno",
    )
    chatbot = models.ForeignKey(
        ChatBot,
        on_delete=models.CASCADE,
        related_name="conversations",
        verbose_name="chatbot",
    )
    title = models.CharField("título", max_length=200, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "conversa"
        verbose_name_plural = "conversas"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title or f"Conversa #{self.pk}"


class Message(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [
        (ROLE_USER, "Usuário"),
        (ROLE_ASSISTANT, "Assistente"),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="conversa",
    )
    role = models.CharField("papel", max_length=20, choices=ROLE_CHOICES)
    content = models.TextField("conteúdo")
    sources = models.JSONField("fontes", default=list, blank=True)
    provider = models.CharField("provedor", max_length=20, blank=True)
    model_name = models.CharField("modelo", max_length=120, blank=True)
    tokens_prompt = models.PositiveIntegerField("tokens de entrada", default=0)
    tokens_completion = models.PositiveIntegerField("tokens de saída", default=0)
    tokens_total = models.PositiveIntegerField("tokens totais", default=0)
    tokens_cached = models.PositiveIntegerField("tokens em cache", default=0)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "mensagem"
        verbose_name_plural = "mensagens"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.get_role_display()} — {self.content[:40]}"
