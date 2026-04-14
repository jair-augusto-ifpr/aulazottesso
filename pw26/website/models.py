from django.db import models


class Course(models.Model):
    """Curso: eixo central dos relacionamentos N:N do diagrama."""

    name = models.CharField("nome", max_length=50)

    class Meta:
        verbose_name = "curso"
        verbose_name_plural = "cursos"

    def __str__(self) -> str:
        return self.name


class Professor(models.Model):
    name = models.CharField("nome", max_length=50)
    siape = models.CharField("SIAPE", max_length=50)
    email = models.CharField("e-mail", max_length=50)
    password = models.CharField("senha", max_length=50)
    courses = models.ManyToManyField(
        Course,
        related_name="professors",
        verbose_name="cursos",
        blank=True,
    )

    class Meta:
        verbose_name = "professor"
        verbose_name_plural = "professores"

    def __str__(self) -> str:
        return self.name


class Student(models.Model):
    name = models.CharField("nome", max_length=50)
    ra = models.CharField("RA", max_length=50)
    email = models.CharField("e-mail", max_length=50)
    password = models.CharField("senha", max_length=50)
    courses = models.ManyToManyField(
        Course,
        related_name="students",
        verbose_name="cursos",
        blank=True,
    )

    class Meta:
        verbose_name = "aluno"
        verbose_name_plural = "alunos"

    def __str__(self) -> str:
        return self.name


class Material(models.Model):
    """Documento institucional; text_content alimenta a busca por palavras-chave do protótipo."""

    title = models.CharField("título", max_length=200, blank=True)
    text_content = models.TextField("texto para busca", blank=True)
    file = models.FileField("arquivo", upload_to="materiais/%Y/%m/")
    public = models.BooleanField("público", default=False)
    courses = models.ManyToManyField(
        Course,
        related_name="materials",
        verbose_name="cursos",
        blank=True,
    )

    class Meta:
        verbose_name = "material"
        verbose_name_plural = "materiais"

    def __str__(self) -> str:
        if self.title:
            return self.title
        return self.file.name or f"Material #{self.pk}"


class ChatBot(models.Model):
    professor = models.ForeignKey(
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

    class Meta:
        verbose_name = "chatbot"
        verbose_name_plural = "chatbots"

    def __str__(self) -> str:
        return f"ChatBot de {self.professor.name}"
