"""Helpers para hash/verificação de senhas dos modelos Professor/Student.

Os modelos guardam a senha numa `CharField` simples (sem usar
`django.contrib.auth.User`). Para evitar armazenamento em texto puro, usamos
os hashers padrão do Django (`make_password` / `check_password`).
"""

from __future__ import annotations

from django.contrib.auth.hashers import check_password, make_password

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


def looks_hashed(value: str | None) -> bool:
    """Heurística: a senha parece ter sido hasheada pelo Django?"""
    if not value:
        return False
    return value.startswith(HASH_PREFIXES)


def set_password(instance, raw: str) -> None:
    """Atribui ao atributo `password` do instance a versão hasheada de `raw`."""
    instance.password = make_password(raw)


def check_password_for(instance, raw: str) -> bool:
    """Compara `raw` com a senha guardada no instance.

    Se o valor armazenado não parece hash (banco antigo), faz comparação
    direta como fallback — mas isso só deve ocorrer antes da data migration.
    """
    stored = getattr(instance, "password", "") or ""
    if looks_hashed(stored):
        return check_password(raw, stored)
    return raw == stored
