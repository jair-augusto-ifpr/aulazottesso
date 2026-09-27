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

    RAG_MODE_TWO_STAGE = "two_stage"
    RAG_MODE_DIRECT = "direct"
    RAG_MODE_BASELINE = "baseline"
    RAG_MODE_CHOICES = [
        (RAG_MODE_TWO_STAGE, "Duas etapas (Roteador + Gerador)"),
        (RAG_MODE_DIRECT, "RAG Direto (Apenas Gerador)"),
        (RAG_MODE_BASELINE, "Baseline (Prefixos longos)"),
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
    router_model = models.CharField(
        "modelo roteador",
        max_length=120,
        blank=True,
        help_text="Opcional. Se vazio, reutiliza o modelo principal.",
    )
    embedding_model = models.CharField(
        "modelo de embedding",
        max_length=120,
        blank=True,
        help_text="Opcional. Ex.: text-embedding-004.",
    )
    rag_mode = models.CharField(
        "modo RAG",
        max_length=20,
        choices=RAG_MODE_CHOICES,
        default=RAG_MODE_TWO_STAGE,
        help_text="Estratégia de recuperação e geração.",
    )
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

    CATEGORY_GERAL = "geral"
    CATEGORY_CALENDARIO = "calendario"
    CATEGORY_ATIVIDADES = "atividades_complementares"
    CATEGORY_EDITAL = "edital"
    CATEGORY_REGULAMENTO = "regulamento"
    CATEGORY_MANUAL = "manual"
    CATEGORY_OUTRO = "outro"
    CATEGORY_CHOICES = [
        (CATEGORY_GERAL, "Geral"),
        (CATEGORY_CALENDARIO, "Calendário Acadêmico"),
        (CATEGORY_ATIVIDADES, "Atividades Complementares"),
        (CATEGORY_EDITAL, "Edital"),
        (CATEGORY_REGULAMENTO, "Regulamento"),
        (CATEGORY_MANUAL, "Manual / Guia"),
        (CATEGORY_OUTRO, "Outro"),
    ]

    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_EMPTY = "empty"
    STATUS_UNSUPPORTED = "unsupported"
    STATUS_SCANNED = "scanned"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendente"),
        (STATUS_SUCCESS, "Sucesso"),
        (STATUS_EMPTY, "Texto vazio"),
        (STATUS_UNSUPPORTED, "Não suportado"),
        (STATUS_SCANNED, "Possível documento escaneado"),
        (STATUS_ERROR, "Erro de extração"),
    ]

    owner = models.ForeignKey(
        Professor,
        on_delete=models.CASCADE,
        related_name="materials",
        verbose_name="professor",
    )
    title = models.CharField("título", max_length=200, blank=True)
    category = models.CharField(
        "categoria",
        max_length=50,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_GERAL,
        db_index=True,
    )
    document_year = models.PositiveIntegerField(
        "ano do documento", null=True, blank=True
    )
    document_number = models.CharField(
        "número / edital", max_length=100, blank=True
    )
    effective_start = models.DateField(
        "início da vigência", null=True, blank=True
    )
    effective_end = models.DateField(
        "fim da vigência", null=True, blank=True
    )
    rectified_material = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rectifications",
        verbose_name="material retificado",
    )
    text_content = models.TextField("texto para busca", blank=True)
    file = models.FileField("arquivo", upload_to="materiais/%Y/%m/", blank=True)
    extraction_status = models.CharField(
        "status da extração",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    extraction_error = models.TextField("erro de extração", blank=True)
    content_hash = models.CharField(
        "hash do conteúdo", max_length=64, blank=True
    )
    processing_version = models.PositiveIntegerField(
        "versão de processamento", default=1
    )
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


class MaterialChunk(models.Model):
    """Trecho documental persistido para recuperação híbrida (lexical + vetorial)."""

    material = models.ForeignKey(
        Material,
        on_delete=models.CASCADE,
        related_name="chunks",
        verbose_name="material",
    )
    chunk_index = models.PositiveIntegerField("índice do chunk")
    content = models.TextField("conteúdo do chunk")
    page_or_section = models.CharField(
        "página ou seção", max_length=100, blank=True
    )
    token_count = models.PositiveIntegerField("contagem de tokens", default=0)
    char_start = models.PositiveIntegerField("caractere inicial", default=0)
    char_end = models.PositiveIntegerField("caractere final", default=0)
    content_hash = models.CharField("hash do chunk", max_length=64, blank=True)
    embedding_vector = models.JSONField(
        "vetor de embedding", null=True, blank=True
    )
    embedding_model = models.CharField(
        "modelo de embedding", max_length=120, blank=True
    )
    embedding_dimension = models.PositiveIntegerField(
        "dimensão do embedding", null=True, blank=True
    )
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "trecho de material"
        verbose_name_plural = "trechos de materiais"
        ordering = ["chunk_index"]
        unique_together = [("material", "chunk_index")]

    def __str__(self) -> str:
        loc = f" ({self.page_or_section})" if self.page_or_section else ""
        return f"Chunk #{self.chunk_index} de {self.material.title or self.material.pk}{loc}"


class LLMCallLog(models.Model):
    """Registro auditável por chamada/etapa aos modelos de linguagem."""

    STAGE_ROUTER = "router"
    STAGE_GENERATOR = "generator"
    STAGE_EMBEDDING = "embedding"
    STAGE_CHOICES = [
        (STAGE_ROUTER, "Roteador / Classificador"),
        (STAGE_GENERATOR, "Gerador de Resposta"),
        (STAGE_EMBEDDING, "Embedding Vetorial"),
    ]

    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_FALLBACK = "fallback"
    STATUS_CHOICES = [
        (STATUS_SUCCESS, "Sucesso"),
        (STATUS_FAILED, "Falha"),
        (STATUS_FALLBACK, "Fallback"),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="call_logs",
        verbose_name="conversa",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="llm_calls",
        verbose_name="aluno",
    )
    professor = models.ForeignKey(
        Professor,
        on_delete=models.CASCADE,
        related_name="llm_calls",
        verbose_name="professor",
    )
    chatbot = models.ForeignKey(
        ChatBot,
        on_delete=models.CASCADE,
        related_name="llm_calls",
        verbose_name="chatbot",
    )
    stage = models.CharField("etapa", max_length=20, choices=STAGE_CHOICES)
    provider = models.CharField("provedor", max_length=20, blank=True)
    model_name = models.CharField("modelo", max_length=120, blank=True)
    status = models.CharField(
        "status", max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCESS
    )
    duration_ms = models.PositiveIntegerField("duração (ms)", default=0)
    tokens_prompt = models.PositiveIntegerField("tokens de entrada", default=0)
    tokens_completion = models.PositiveIntegerField("tokens de saída", default=0)
    tokens_total = models.PositiveIntegerField("tokens totais", default=0)
    tokens_cached = models.PositiveIntegerField("tokens em cache", default=0)
    cost = models.DecimalField(
        "custo", max_digits=10, decimal_places=6, null=True, blank=True
    )
    currency = models.CharField("moeda", max_length=10, default="USD")
    error_message = models.TextField("mensagem de erro", blank=True)
    request_id = models.CharField(
        "id da requisição", max_length=64, blank=True, db_index=True
    )
    created_at = models.DateTimeField(
        "criado em", auto_now_add=True, db_index=True
    )

    class Meta:
        verbose_name = "registro de chamada LLM"
        verbose_name_plural = "registros de chamadas LLM"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.stage}] {self.model_name} — {self.tokens_total} tokens ({self.status})"

