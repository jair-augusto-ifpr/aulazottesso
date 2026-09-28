import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0003_rag_chunks_and_logs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="llmcalllog",
            name="chatbot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="llm_calls",
                to="website.chatbot",
                verbose_name="chatbot",
            ),
        ),
        migrations.AlterField(
            model_name="llmcalllog",
            name="student",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="llm_calls",
                to="website.student",
                verbose_name="aluno",
            ),
        ),
        migrations.AlterField(
            model_name="professorconfig",
            name="router_model",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Opcional. Se vazio e o modelo principal for caro, usa um modelo barato. "
                    "Se o principal já for Flash ou gratuito, reutiliza o principal."
                ),
                max_length=120,
                verbose_name="modelo roteador",
            ),
        ),
    ]
