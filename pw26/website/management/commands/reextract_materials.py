from django.core.management.base import BaseCommand

from website.models import Material
from website.text_extraction import apply_material_text_extraction


class Command(BaseCommand):
    help = "Reextrai texto dos arquivos anexados aos materiais (útil após correções de indexação)."

    def handle(self, *args, **options):
        updated = 0
        for material in Material.objects.exclude(file="").iterator():
            chars = apply_material_text_extraction(material, prefer_file=True)
            if chars:
                updated += 1
                self.stdout.write(f"  {material.pk}: {material.title} — {chars} caracteres")
        self.stdout.write(self.style.SUCCESS(f"Concluído. {updated} material(is) atualizado(s)."))
