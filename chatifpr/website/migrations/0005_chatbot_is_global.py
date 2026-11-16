from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0004_embedding_audit_nullable_fks"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatbot",
            name="is_global",
            field=models.BooleanField(
                default=False,
                help_text="Disponível para todos os estudantes, independente do curso.",
                verbose_name="global",
            ),
        ),
    ]
