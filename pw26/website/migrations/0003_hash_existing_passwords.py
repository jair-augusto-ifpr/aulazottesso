from django.contrib.auth.hashers import make_password
from django.db import migrations, models

HASH_PREFIXES = (
    "pbkdf2_",
    "argon2",
    "bcrypt",
    "scrypt",
    "unsalted_",
    "sha1$",
    "md5$",
    "crypt$",
)


def _needs_hash(value: str) -> bool:
    return bool(value) and not value.startswith(HASH_PREFIXES)


def hash_plaintext_passwords(apps, schema_editor):
    for model_name in ("Professor", "Student"):
        Model = apps.get_model("website", model_name)
        for obj in Model.objects.all():
            if _needs_hash(obj.password or ""):
                obj.password = make_password(obj.password)
                obj.save(update_fields=["password"])


def noop_reverse(apps, schema_editor):
    # Não há como recuperar a senha original a partir do hash.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0002_material_title_text_content"),
    ]

    operations = [
        migrations.AlterField(
            model_name="professor",
            name="password",
            field=models.CharField(max_length=128, verbose_name="senha"),
        ),
        migrations.AlterField(
            model_name="student",
            name="password",
            field=models.CharField(max_length=128, verbose_name="senha"),
        ),
        migrations.RunPython(hash_plaintext_passwords, noop_reverse),
    ]
