"""Dispara 30 alunos ao mesmo tempo contra o chatbot da secretaria.

Cada aluno faz uma pergunta diferente sobre o calendário acadêmico.
O relatório guarda quem perguntou, a resposta e o tempo até ela voltar.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from website.constants import GROUP_ALUNO
from website.models import ChatBot, Conversation, Course, ProfessorConfig, Student

SIAPE_SECRETARIA = "1000001"
CALENDAR_TITLE = "Calendário Acadêmico 2026"
STUDENT_COUNT = 30

QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "Q01",
        "question": "Quando começam as aulas em 2026?",
        "expected_keywords": ["10", "fevereiro"],
    },
    {
        "id": "Q02",
        "question": "Quando encerra o semestre letivo de 2026?",
        "expected_keywords": ["19", "dezembro"],
    },
    {
        "id": "Q03",
        "question": "Qual o período do recesso de julho?",
        "expected_keywords": ["13", "31", "julho"],
    },
    {
        "id": "Q04",
        "question": "Em que dia começa o recesso de julho?",
        "expected_keywords": ["13", "julho"],
    },
    {
        "id": "Q05",
        "question": "Em que dia termina o recesso de julho?",
        "expected_keywords": ["31", "julho"],
    },
    {
        "id": "Q06",
        "question": "Quais dias de fevereiro são ponto facultativo de Carnaval?",
        "expected_keywords": ["16", "17", "fevereiro"],
    },
    {
        "id": "Q07",
        "question": "Quando é a Sexta-feira Santa em 2026?",
        "expected_keywords": ["3", "abril"],
    },
    {
        "id": "Q08",
        "question": "Qual a data de Tiradentes no calendário?",
        "expected_keywords": ["21", "abril"],
    },
    {
        "id": "Q09",
        "question": "Quando é o Dia do Trabalho?",
        "expected_keywords": ["1", "maio"],
    },
    {
        "id": "Q10",
        "question": "Qual a data de Corpus Christi?",
        "expected_keywords": ["4", "junho"],
    },
    {
        "id": "Q11",
        "question": "Quando cai a Independência do Brasil?",
        "expected_keywords": ["7", "setembro"],
    },
    {
        "id": "Q12",
        "question": "Quando é o feriado de Nossa Senhora Aparecida?",
        "expected_keywords": ["12", "outubro"],
    },
    {
        "id": "Q13",
        "question": "Qual a data de Finados?",
        "expected_keywords": ["2", "novembro"],
    },
    {
        "id": "Q14",
        "question": "Quando é a Proclamação da República?",
        "expected_keywords": ["15", "novembro"],
    },
    {
        "id": "Q15",
        "question": "Há aula no dia 16 de fevereiro de 2026?",
        "expected_keywords": ["carnaval", "facultativo"],
    },
    {
        "id": "Q16",
        "question": "Há aula no dia 7 de setembro de 2026?",
        "expected_keywords": ["independência", "setembro"],
    },
    {
        "id": "Q17",
        "question": "Qual o horário da manhã no atendimento da secretaria?",
        "expected_keywords": ["8h", "12h"],
    },
    {
        "id": "Q18",
        "question": "Qual o horário da tarde no atendimento da secretaria?",
        "expected_keywords": ["13h", "17h"],
    },
    {
        "id": "Q19",
        "question": "Em quais dias da semana a secretaria atende?",
        "expected_keywords": ["segunda", "sexta"],
    },
    {
        "id": "Q20",
        "question": "A secretaria atende no sábado?",
        "expected_keywords": ["segunda", "sexta"],
    },
    {
        "id": "Q21",
        "question": "Como o estudante solicita o histórico escolar?",
        "expected_keywords": ["presencialmente", "e-mail"],
    },
    {
        "id": "Q22",
        "question": "Como pedir documentos e declarações?",
        "expected_keywords": ["presencialmente", "e-mail"],
    },
    {
        "id": "Q23",
        "question": "Onde consultar a rematrícula?",
        "expected_keywords": ["edital"],
    },
    {
        "id": "Q24",
        "question": "Onde consultar o trancamento?",
        "expected_keywords": ["edital"],
    },
    {
        "id": "Q25",
        "question": "Quem confirma as datas das provas?",
        "expected_keywords": ["professor"],
    },
    {
        "id": "Q26",
        "question": "As atividades avaliativas seguem qual plano?",
        "expected_keywords": ["plano", "disciplina"],
    },
    {
        "id": "Q27",
        "question": "O que os trabalhos complementares e as recuperações devem respeitar?",
        "expected_keywords": ["prazos", "regulamento"],
    },
    {
        "id": "Q28",
        "question": "O calendário pode ser atualizado? Por quem?",
        "expected_keywords": ["portaria"],
    },
    {
        "id": "Q29",
        "question": "Em caso de divergência, qual documento prevalece?",
        "expected_keywords": ["oficial", "coordenação"],
    },
    {
        "id": "Q30",
        "question": "Este calendário é de qual campus?",
        "expected_keywords": ["paranavaí"],
    },
]


def student_ra(index: int) -> str:
    return f"carga2026{index:03d}"


def student_name(index: int) -> str:
    return f"Aluno Carga {index:02d}"


def keyword_hit(answer: str, keywords: list[str]) -> bool:
    """Confere se a resposta contém cada palavra esperada.

    Números exigem fronteira, para "3" não casar dentro de "13".
    """
    text = (answer or "").casefold()
    for keyword in keywords:
        token = keyword.casefold()
        if token.isdigit():
            if not re.search(rf"(?<!\d){re.escape(token)}(?!\d)", text):
                return False
        elif token not in text:
            return False
    return True


def percentile(sorted_values: list[float], percent: float) -> float:
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (len(sorted_values) - 1) * (percent / 100)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(sorted_values[int(rank)])
    weight = rank - lower
    value = sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight
    return round(value, 1)


def default_clock_ms(_tls: threading.local) -> float:
    return time.monotonic() * 1000


def find_secretaria_chatbot() -> ChatBot | None:
    return (
        ChatBot.objects.select_related("owner")
        .filter(owner__siape=SIAPE_SECRETARIA, materials__title=CALENDAR_TITLE)
        .distinct()
        .first()
    )


def secretaria_api_ready(chatbot: ChatBot) -> tuple[bool, str]:
    try:
        config = chatbot.owner.config
    except ProfessorConfig.DoesNotExist:
        config = None
    if config is None or not config.has_api():
        return (
            False,
            "A secretaria ainda não tem API configurada. "
            "Defina a chave no painel ou no ambiente antes da carga.",
        )
    return True, ""


def ensure_load_students(extra_courses: list[Course] | None = None) -> list[Student]:
    """Garante os 30 alunos de carga, matriculados em Informática e nos cursos do chatbot."""
    informatica, _ = Course.objects.get_or_create(name="Informática")
    courses: list[Course] = [informatica]
    for course in extra_courses or []:
        if course.pk not in {item.pk for item in courses}:
            courses.append(course)

    aluno_group, _ = Group.objects.get_or_create(name=GROUP_ALUNO)
    students: list[Student] = []
    for index in range(1, STUDENT_COUNT + 1):
        ra = student_ra(index)
        name = student_name(index)
        user, created = User.objects.get_or_create(
            username=ra,
            defaults={"email": f"{ra}@ifpr.local"},
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        user.groups.add(aluno_group)
        student, _ = Student.objects.get_or_create(
            user=user,
            defaults={"name": name, "ra": ra},
        )
        if student.name != name or student.ra != ra:
            student.name = name
            student.ra = ra
            student.save(update_fields=["name", "ra"])
        student.courses.add(*courses)
        students.append(student)
    return students


def open_assignments(
    chatbot: ChatBot,
    students: list[Student],
    run_id: str,
) -> list[dict[str, Any]]:
    if len(students) != len(QUESTIONS):
        raise ValueError("Cada aluno de carga precisa de uma pergunta.")
    assignments = []
    for student, question in zip(students, QUESTIONS):
        conversation = Conversation.objects.create(student=student, chatbot=chatbot)
        _ = conversation.student
        assignments.append(
            {
                "student_id": student.pk,
                "ra": student.ra,
                "nome": student.name,
                "pergunta_id": question["id"],
                "pergunta": question["question"],
                "expected_keywords": list(question["expected_keywords"]),
                "conversation": conversation,
                "chatbot": chatbot,
                "request_id": f"loadtest-{run_id}-{student.ra}",
            }
        )
    return assignments


def _empty_row(assignment: dict[str, Any]) -> dict[str, Any]:
    return {
        "ra": assignment["ra"],
        "nome": assignment["nome"],
        "pergunta_id": assignment["pergunta_id"],
        "pergunta": assignment["pergunta"],
        "inicio": None,
        "fim": None,
        "latencia_ms": None,
        "status": "erro",
        "resposta": "",
        "erro": "",
        "tokens": 0,
        "conversa_id": assignment["conversation"].pk,
        "request_id": assignment["request_id"],
        "palavras_encontradas": False,
        "_started_ms": None,
        "_finished_ms": None,
    }


def _apply_outcome(row: dict[str, Any], assignment: dict[str, Any], outcome: dict) -> None:
    assistant = outcome.get("assistant") if outcome.get("ok") else None
    if assistant is not None:
        row["status"] = "sucesso"
        row["resposta"] = assistant.content or ""
        row["tokens"] = assistant.tokens_total or 0
        row["erro"] = ""
        row["palavras_encontradas"] = keyword_hit(
            row["resposta"], assignment["expected_keywords"]
        )
        return
    row["status"] = "erro"
    row["resposta"] = ""
    row["tokens"] = 0
    row["erro"] = outcome.get("error") or "Falha sem mensagem."
    row["palavras_encontradas"] = False


def run_wave(
    assignments: list[dict[str, Any]],
    answer_fn: Callable,
    clock_ms: Callable[[threading.local], float] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Dispara todas as perguntas juntas e devolve as linhas e a duração da leva."""
    clock = clock_ms or default_clock_ms
    barrier = threading.Barrier(len(assignments))
    tls = threading.local()

    def worker(assignment: dict[str, Any]) -> dict[str, Any]:
        close_old_connections()
        row = _empty_row(assignment)
        reached_barrier = False
        try:
            tls.ra = assignment["ra"]
            tls.calls = 0
            reached_barrier = True
            barrier.wait(timeout=120)
            started_ms = clock(tls)
            started_at = datetime.now(timezone.utc)
            try:
                outcome = answer_fn(
                    assignment["chatbot"],
                    assignment["conversation"],
                    assignment["pergunta"],
                    request_id=assignment["request_id"],
                )
            except Exception as exc:
                outcome = {"ok": False, "error": str(exc)}
            finished_ms = clock(tls)
            finished_at = datetime.now(timezone.utc)
            row["_started_ms"] = started_ms
            row["_finished_ms"] = finished_ms
            row["inicio"] = started_at.isoformat()
            row["fim"] = finished_at.isoformat()
            row["latencia_ms"] = int(round(finished_ms - started_ms))
            _apply_outcome(row, assignment, outcome or {})
        except threading.BrokenBarrierError:
            row["erro"] = "A barreira da leva foi interrompida antes do disparo."
        except Exception as exc:
            row["erro"] = str(exc)
            if not reached_barrier:
                barrier.abort()
        finally:
            close_old_connections()
        return row

    with ThreadPoolExecutor(max_workers=len(assignments)) as pool:
        rows = list(pool.map(worker, assignments))

    rows.sort(key=lambda item: item["pergunta_id"])
    started = [row["_started_ms"] for row in rows if row["_started_ms"] is not None]
    finished = [row["_finished_ms"] for row in rows if row["_finished_ms"] is not None]
    if started and finished:
        batch_duration_ms = int(round(max(finished) - min(started)))
    else:
        batch_duration_ms = 0
    return rows, batch_duration_ms


def summarize(rows: list[dict[str, Any]], batch_duration_ms: int) -> dict[str, Any]:
    success = sum(1 for row in rows if row["status"] == "sucesso")
    failed = len(rows) - success
    measured = [row for row in rows if row["latencia_ms"] is not None]
    ordered = sorted(row["latencia_ms"] for row in measured)
    if ordered:
        latency = {
            "minimo": ordered[0],
            "media": round(sum(ordered) / len(ordered), 1),
            "mediana": percentile(ordered, 50),
            "p95": percentile(ordered, 95),
            "maximo": ordered[-1],
        }
        ranked = sorted(measured, key=lambda row: (row["latencia_ms"], row["pergunta_id"]))
        fastest = _identity(ranked[0])
        slowest = _identity(ranked[-1])
    else:
        latency = {
            "minimo": None,
            "media": None,
            "mediana": None,
            "p95": None,
            "maximo": None,
        }
        fastest = None
        slowest = None
    return {
        "total": len(rows),
        "sucesso": success,
        "falha": failed,
        "latencia_ms": latency,
        "mais_rapido": fastest,
        "mais_lento": slowest,
        "duracao_leva_ms": batch_duration_ms,
    }


def _identity(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ra": row["ra"],
        "nome": row["nome"],
        "pergunta_id": row["pergunta_id"],
        "latencia_ms": row["latencia_ms"],
    }


def public_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hidden = {"_started_ms", "_finished_ms", "expected_keywords"}
    return [{key: value for key, value in row.items() if key not in hidden} for row in rows]


def build_report(
    *,
    run_id: str,
    chatbot_id: int,
    started_at: datetime,
    finished_at: datetime,
    rows: list[dict[str, Any]],
    batch_duration_ms: int,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "chatbot_id": chatbot_id,
        "inicio": started_at.isoformat(),
        "fim": finished_at.isoformat(),
        "resumo": summarize(rows, batch_duration_ms),
        "resultados": public_rows(rows),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["resumo"]
    latency = summary["latencia_ms"]
    lines = [
        f"# Carga do calendário acadêmico — {report['run_id']}",
        "",
        f"- Chatbot: {report['chatbot_id']}",
        f"- Início: {report['inicio']}",
        f"- Fim: {report['fim']}",
        f"- Duração da leva: {summary['duracao_leva_ms']} ms",
        f"- Sucesso: {summary['sucesso']} de {summary['total']}",
        f"- Falha: {summary['falha']}",
        (
            "- Latência (ms): "
            f"mínimo {latency['minimo']}, média {latency['media']}, "
            f"mediana {latency['mediana']}, p95 {latency['p95']}, "
            f"máximo {latency['maximo']}"
        ),
    ]
    if summary["mais_rapido"]:
        fast = summary["mais_rapido"]
        slow = summary["mais_lento"]
        lines.append(
            f"- Mais rápido: {fast['nome']} ({fast['ra']}) "
            f"{fast['pergunta_id']} em {fast['latencia_ms']} ms"
        )
        lines.append(
            f"- Mais lento: {slow['nome']} ({slow['ra']}) "
            f"{slow['pergunta_id']} em {slow['latencia_ms']} ms"
        )
    lines.extend(["", "## Alunos", ""])
    lines.append("| RA | Aluno | Pergunta | Latência (ms) | Status | Palavras |")
    lines.append("| --- | --- | --- | ---: | --- | --- |")
    for row in report["resultados"]:
        palavras = "sim" if row["palavras_encontradas"] else "não"
        lines.append(
            f"| {row['ra']} | {row['nome']} | {row['pergunta_id']} | "
            f"{row['latencia_ms']} | {row['status']} | {palavras} |"
        )
    lines.extend(["", "## Respostas", ""])
    for row in report["resultados"]:
        lines.append(f"### {row['pergunta_id']} — {row['nome']} ({row['ra']})")
        lines.append("")
        lines.append(f"- Pedido: `{row['request_id']}`")
        lines.append(f"- Conversa: {row['conversa_id']}")
        lines.append(f"- Início: {row['inicio']}")
        lines.append(f"- Fim: {row['fim']}")
        lines.append(f"- Latência: {row['latencia_ms']} ms")
        lines.append(f"- Status: {row['status']}")
        lines.append(f"- Tokens: {row['tokens']}")
        if row["erro"]:
            lines.append(f"- Erro: {row['erro']}")
        lines.append("")
        lines.append(f"**Pergunta:** {row['pergunta']}")
        lines.append("")
        lines.append("**Resposta:**")
        lines.append("")
        lines.append(row["resposta"] or "_(sem resposta)_")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_reports(report: dict[str, Any], output_dir: Path | None = None) -> tuple[Path, Path]:
    directory = output_dir or (Path(settings.BASE_DIR) / "reports")
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"loadtest-calendario-{report['run_id']}"
    json_path = directory / f"{stem}.json"
    md_path = directory / f"{stem}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


class Command(BaseCommand):
    help = (
        "Simula 30 alunos perguntando ao mesmo tempo sobre o calendário acadêmico "
        "no chatbot da secretaria e grava a auditoria de tempo e resposta."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default="",
            help="Pasta dos relatórios. Padrão: reports/ na raiz do projeto.",
        )

    def handle(self, *args, **options):
        if len(QUESTIONS) != STUDENT_COUNT:
            raise CommandError("O conjunto de perguntas precisa ter 30 itens.")

        chatbot = find_secretaria_chatbot()
        if chatbot is None:
            raise CommandError(
                "Chatbot da secretaria com o material "
                f"'{CALENDAR_TITLE}' não encontrado (SIAPE {SIAPE_SECRETARIA})."
            )
        ready, reason = secretaria_api_ready(chatbot)
        if not ready:
            raise CommandError(reason)

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        students = ensure_load_students(extra_courses=list(chatbot.courses.all()))
        assignments = open_assignments(chatbot, students, run_id)
        _ = chatbot.owner

        from website.views import _answer_and_store

        self.stdout.write(
            f"Disparando {STUDENT_COUNT} perguntas ao mesmo tempo "
            f"(run {run_id}, chatbot {chatbot.pk})."
        )
        started_at = datetime.now(timezone.utc)
        rows, batch_duration_ms = run_wave(assignments, _answer_and_store)
        finished_at = datetime.now(timezone.utc)
        report = build_report(
            run_id=run_id,
            chatbot_id=chatbot.pk,
            started_at=started_at,
            finished_at=finished_at,
            rows=rows,
            batch_duration_ms=batch_duration_ms,
        )
        output_dir = Path(options["output_dir"]) if options["output_dir"] else None
        json_path, md_path = write_reports(report, output_dir)
        summary = report["resumo"]
        self.stdout.write(
            self.style.SUCCESS(
                f"Sucesso {summary['sucesso']}/{summary['total']}, "
                f"falha {summary['falha']}, "
                f"p95 {summary['latencia_ms']['p95']} ms, "
                f"leva {summary['duracao_leva_ms']} ms."
            )
        )
        self.stdout.write(f"JSON: {json_path}")
        self.stdout.write(f"Markdown: {md_path}")
