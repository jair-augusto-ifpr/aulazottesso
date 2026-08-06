import os

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from website.constants import GROUP_ALUNO, GROUP_PROFESSOR
from website.models import (
    ChatBot,
    Course,
    Material,
    Professor,
    ProfessorConfig,
    Student,
)

CALENDARIO_ACADEMICO_TEXT = """
CALENDÁRIO ACADÊMICO 2026 — IFPR CAMPUS PARANAVAÍ

1. PERÍODO LETIVO
- Início das aulas: 10 de fevereiro de 2026
- Encerramento do semestre: 19 de dezembro de 2026

2. RECESSO E FERIADOS
- Recesso de julho: 13 a 31 de julho de 2026
- Carnaval (ponto facultativo): 16 e 17 de fevereiro de 2026
- Sexta-feira Santa: 3 de abril de 2026
- Tiradentes: 21 de abril de 2026
- Dia do Trabalho: 1º de maio de 2026
- Corpus Christi: 4 de junho de 2026
- Independência do Brasil: 7 de setembro de 2026
- Nossa Senhora Aparecida: 12 de outubro de 2026
- Finados: 2 de novembro de 2026
- Proclamação da República: 15 de novembro de 2026

3. AVALIAÇÕES E ENTREGAS
- Atividades avaliativas seguem o plano de cada disciplina publicado pelos professores.
- Trabalhos complementares e recuperações devem respeitar os prazos do regulamento do curso.
- Dúvidas sobre datas de provas devem ser confirmadas com o professor da disciplina.

4. MATRÍCULA E SECRETARIA
- Horário de atendimento da secretaria: segunda a sexta, das 8h às 12h e das 13h às 17h.
- Documentos, declarações e histórico escolar: solicitar presencialmente ou pelo e-mail institucional.
- Rematrícula e trancamento: consultar edital publicado no início de cada semestre.

5. OBSERVAÇÕES
- Este calendário pode ser atualizado por portaria do campus.
- Em caso de divergência, prevalece o documento oficial publicado pela coordenação.
""".strip()


class Command(BaseCommand):
    help = "Cria grupos, superusuário e dados de exemplo para desenvolvimento."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Remove dados de exemplo antes de recriar.",
        )

    def _apply_api_config(self, config: ProfessorConfig) -> None:
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if gemini_key:
            config.provider = ProfessorConfig.PROVIDER_GEMINI
            config.api_key = gemini_key
            config.model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        elif openrouter_key:
            config.provider = ProfessorConfig.PROVIDER_OPENROUTER
            config.api_key = openrouter_key
            config.model = os.environ.get("OPENROUTER_MODEL", "qwen/qwen3-coder:free")
        config.token_limit_per_student = 50000
        config.limit_period_days = 30
        config.save()

    def _ensure_professor(
        self,
        *,
        username: str,
        password: str,
        email: str,
        name: str,
        siape: str,
        courses: list[Course],
        prof_group: Group,
    ) -> Professor:
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email},
        )
        if created:
            user.set_password(password)
            user.save()
        user.groups.add(prof_group)

        professor, _ = Professor.objects.get_or_create(
            user=user,
            defaults={"name": name, "siape": siape},
        )
        professor.name = name
        professor.siape = siape
        professor.save(update_fields=["name", "siape"])
        professor.courses.set(courses)

        config, _ = ProfessorConfig.objects.get_or_create(professor=professor)
        self._apply_api_config(config)
        return professor

    def handle(self, *args, **options):
        if options["reset"]:
            ChatBot.objects.all().delete()
            Material.objects.all().delete()
            ProfessorConfig.objects.all().delete()
            Student.objects.all().delete()
            Professor.objects.all().delete()
            Course.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write("Dados de exemplo removidos.")

        prof_group, _ = Group.objects.get_or_create(name=GROUP_PROFESSOR)
        aluno_group, _ = Group.objects.get_or_create(name=GROUP_ALUNO)

        admin_user, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@ifpr.edu.br",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            admin_user.set_password("admin123")
            admin_user.save()
            self.stdout.write(self.style.SUCCESS("Superusuário admin / admin123 criado."))

        informatica, _ = Course.objects.get_or_create(name="Informática")
        administracao, _ = Course.objects.get_or_create(name="Administração")
        all_courses = [informatica, administracao]

        professor = self._ensure_professor(
            username="2074709",
            password="prof123",
            email="professor@ifpr.edu.br",
            name="Késsia Marchi",
            siape="2074709",
            courses=all_courses,
            prof_group=prof_group,
        )

        secretaria = self._ensure_professor(
            username="1000001",
            password="sec123",
            email="secretaria@ifpr.edu.br",
            name="Secretaria",
            siape="1000001",
            courses=all_courses,
            prof_group=prof_group,
        )

        aluno_user, created = User.objects.get_or_create(
            username="20233012578",
            defaults={"email": "aluno@ifpr.edu.br"},
        )
        if created:
            aluno_user.set_password("aluno123")
            aluno_user.save()
        aluno_user.groups.add(aluno_group)

        student, _ = Student.objects.get_or_create(
            user=aluno_user,
            defaults={
                "name": "Jair Boeing",
                "ra": "20233012578",
                "phone": "(44) 99999-0000",
            },
        )
        student.courses.set(all_courses)

        calendario, _ = Material.objects.update_or_create(
            owner=secretaria,
            title="Calendário Acadêmico 2026",
            defaults={
                "text_content": CALENDARIO_ACADEMICO_TEXT,
                "public": True,
            },
        )
        calendario.courses.set(all_courses)

        material_prof, _ = Material.objects.get_or_create(
            owner=professor,
            title="Regulamento de Estágio — Informática",
            defaults={
                "text_content": (
                    "O estágio supervisionado é obrigatório no curso de Informática. "
                    "A carga horária mínima é de 240 horas. O aluno deve apresentar "
                    "plano de atividades assinado pela empresa e pelo orientador do IFPR."
                ),
                "public": True,
            },
        )
        material_prof.courses.set([informatica])

        chatbot_secretaria, created = ChatBot.objects.get_or_create(
            owner=secretaria,
            defaults={
                "prompt": (
                    "Você é o assistente institucional da Secretaria do IFPR Campus Paranavaí. "
                    "Responda com base no calendário acadêmico e em normas administrativas. "
                    "Seja objetivo e cite datas quando disponíveis no documento. "
                    "Se a informação não estiver no material, oriente o estudante a procurar "
                    "a secretaria presencialmente ou por e-mail institucional."
                ),
            },
        )
        if created or not chatbot_secretaria.courses.exists():
            chatbot_secretaria.courses.set(all_courses)
        chatbot_secretaria.materials.set([calendario])

        chatbot_prof, created = ChatBot.objects.get_or_create(
            owner=professor,
            defaults={
                "prompt": (
                    "Responda com base nos documentos do curso de Informática. "
                    "Se não souber, oriente o estudante a falar com o professor ou a secretaria."
                ),
            },
        )
        if created or not chatbot_prof.courses.exists():
            chatbot_prof.courses.set([informatica])
        chatbot_prof.materials.set([material_prof])

        config = ProfessorConfig.objects.get(professor=professor)

        self.stdout.write(self.style.SUCCESS("Seed concluído."))
        self.stdout.write("Professor: SIAPE 2074709 / senha prof123")
        self.stdout.write("Secretaria: SIAPE 1000001 / senha sec123")
        self.stdout.write("Aluno: RA 20233012578 / senha aluno123")
        self.stdout.write("Admin: admin / admin123")
        if config.has_api():
            self.stdout.write(
                f"Config de API (professores): {config.get_provider_display()} / "
                f"modelo {config.model}"
            )
        else:
            self.stdout.write(
                "Config de API vazia (defina GEMINI_API_KEY ou OPENROUTER_API_KEY "
                "no ambiente ou pelo painel do professor para liberar o chat)."
            )
