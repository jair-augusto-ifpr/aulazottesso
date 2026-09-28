"""Comando para reextração de texto e reindexação de chunks para RAG econômico."""

from django.core.management.base import BaseCommand

from website.document_processing import index_material
from website.models import Material, Professor
from website.text_extraction import apply_material_text_extraction


class Command(BaseCommand):
    help = (
        "Reextrai texto e reindexa trechos (chunks) dos materiais para RAG. "
        "Suporta seleção por material, professor, modo de inspeção (--dry-run) e força (--force)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--material-id",
            type=int,
            default=None,
            help="Processa apenas o material com o ID especificado.",
        )
        parser.add_argument(
            "--professor-id",
            type=int,
            default=None,
            help="Processa apenas materiais do professor com o ID especificado.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Modo de inspeção: apenas analisa e exibe o que seria processado sem persistir.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Força reprocessamento mesmo que o hash de conteúdo não tenha mudado.",
        )
        parser.add_argument(
            "--with-embeddings",
            action="store_true",
            help="Gera embeddings reais caso o professor tenha API configurada.",
        )

    def handle(self, *args, **options):
        material_id = options.get("material_id")
        professor_id = options.get("professor_id")
        dry_run = options.get("dry_run", False)
        force = options.get("force", False)
        with_embeddings = options.get("with_embeddings", False)

        qs = Material.objects.all().select_related("owner")
        if material_id:
            qs = qs.filter(pk=material_id)
        if professor_id:
            qs = qs.filter(owner_id=professor_id)

        total = qs.count()
        if dry_run:
            self.stdout.write(self.style.WARNING(f"[MODO DE INSPEÇÃO] {total} material(is) selecionado(s):"))
            for m in qs:
                has_file = bool(m.file and m.file.name)
                chars = len(m.text_content or "")
                chunks_count = m.chunks.count()
                self.stdout.write(
                    f"  Material #{m.pk}: «{m.title}» | Professor: {m.owner.name} | "
                    f"Arquivo: {'Sim' if has_file else 'Não'} | Chars: {chars} | Chunks atuais: {chunks_count} | Status: {m.extraction_status}"
                )
            return

        self.stdout.write(f"Iniciando reextração e reindexação de {total} material(is)...")
        updated_extracted = 0
        indexed_chunks_total = 0

        for m in qs.iterator():
            chars = 0
            if m.file:
                chars = apply_material_text_extraction(m, prefer_file=force)
                if chars:
                    updated_extracted += 1

            idx_res = index_material(
                m,
                force=force,
                generate_embeddings=with_embeddings,
            )
            chunks_count = idx_res.get("chunk_count", 0)
            if idx_res.get("updated"):
                indexed_chunks_total += chunks_count
                self.stdout.write(
                    f"  Material #{m.pk}: «{m.title}» — {chars} chars extraídos, {chunks_count} chunk(s) indexado(s)."
                )
            else:
                self.stdout.write(
                    f"  Material #{m.pk}: «{m.title}» — índice inalterado ({chunks_count} chunks existentes)."
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Concluído com sucesso. {updated_extracted} material(is) com texto extraído; "
                f"{indexed_chunks_total} chunk(s) atualizados."
            )
        )
