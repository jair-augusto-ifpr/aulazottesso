import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Course",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=50, verbose_name="nome")),
            ],
            options={
                "verbose_name": "curso",
                "verbose_name_plural": "cursos",
            },
        ),
        migrations.CreateModel(
            name="Material",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "file",
                    models.FileField(
                        upload_to="materiais/%Y/%m/", verbose_name="arquivo"
                    ),
                ),
                ("public", models.BooleanField(default=False, verbose_name="público")),
            ],
            options={
                "verbose_name": "material",
                "verbose_name_plural": "materiais",
            },
        ),
        migrations.CreateModel(
            name="Professor",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=50, verbose_name="nome")),
                ("siape", models.CharField(max_length=50, verbose_name="SIAPE")),
                ("email", models.CharField(max_length=50, verbose_name="e-mail")),
                ("password", models.CharField(max_length=50, verbose_name="senha")),
            ],
            options={
                "verbose_name": "professor",
                "verbose_name_plural": "professores",
            },
        ),
        migrations.CreateModel(
            name="Student",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=50, verbose_name="nome")),
                ("ra", models.CharField(max_length=50, verbose_name="RA")),
                ("email", models.CharField(max_length=50, verbose_name="e-mail")),
                ("password", models.CharField(max_length=50, verbose_name="senha")),
            ],
            options={
                "verbose_name": "aluno",
                "verbose_name_plural": "alunos",
            },
        ),
        migrations.AddField(
            model_name="professor",
            name="courses",
            field=models.ManyToManyField(
                blank=True,
                related_name="professors",
                to="website.course",
                verbose_name="cursos",
            ),
        ),
        migrations.AddField(
            model_name="student",
            name="courses",
            field=models.ManyToManyField(
                blank=True,
                related_name="students",
                to="website.course",
                verbose_name="cursos",
            ),
        ),
        migrations.AddField(
            model_name="material",
            name="courses",
            field=models.ManyToManyField(
                blank=True,
                related_name="materials",
                to="website.course",
                verbose_name="cursos",
            ),
        ),
        migrations.CreateModel(
            name="ChatBot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("prompt", models.CharField(max_length=2000, verbose_name="prompt")),
                (
                    "professor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chatbots",
                        to="website.professor",
                        verbose_name="professor",
                    ),
                ),
            ],
            options={
                "verbose_name": "chatbot",
                "verbose_name_plural": "chatbots",
            },
        ),
        migrations.AddField(
            model_name="chatbot",
            name="courses",
            field=models.ManyToManyField(
                blank=True,
                related_name="chatbots",
                to="website.course",
                verbose_name="cursos",
            ),
        ),
        migrations.AddField(
            model_name="chatbot",
            name="materials",
            field=models.ManyToManyField(
                blank=True,
                related_name="chatbots",
                to="website.material",
                verbose_name="materiais",
            ),
        ),
    ]
