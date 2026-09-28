"""Cria superusuário Django a partir de variáveis de ambiente (deploy Cloud Run)."""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Cria ou atualiza superusuário usando DJANGO_SUPERUSER_* no ambiente."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not password:
            self.stderr.write("Defina DJANGO_SUPERUSER_PASSWORD.")
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        verb = "Criado" if created else "Atualizado"
        self.stdout.write(self.style.SUCCESS(f"{verb} superusuário: {username}"))
