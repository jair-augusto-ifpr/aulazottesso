import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from .chat_service import RetrievedSnippet, retrieve_snippets
from .models import ChatBot, Course, Material, Professor, Student


class ChatFlowTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(name="Informática")
        self.student = Student.objects.create(
            name="Ana Estudante",
            ra="2026001",
            email="ana@example.com",
            password="hash",
        )
        self.student.courses.add(self.course)
        self.professor = Professor.objects.create(
            name="Prof. Bruno",
            siape="12345",
            email="bruno@example.com",
            password="hash",
        )
        self.professor.courses.add(self.course)
        self.material = Material.objects.create(
            title="Calendário acadêmico",
            text_content="As férias começam em julho.",
            file="materiais/calendario.pdf",
            public=False,
        )
        self.material.courses.add(self.course)
        self.chatbot = ChatBot.objects.create(
            professor=self.professor,
            prompt="Responda de forma breve.",
        )
        self.chatbot.courses.add(self.course)
        self.chatbot.materials.add(self.material)
        self.send_url = reverse("student_chat_send", args=[self.chatbot.pk])

    def _login_student(self, student=None):
        session = self.client.session
        session["student_id"] = (student or self.student).pk
        session.save()

    def test_chat_send_requires_student_course_access(self):
        other_student = Student.objects.create(
            name="Carlos",
            ra="2026002",
            email="carlos@example.com",
            password="hash",
        )
        self._login_student(other_student)

        response = self.client.post(
            self.send_url,
            data=json.dumps({"message": "Quando começam as férias?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {"error": "Sem permissão para acessar este chatbot."},
        )

    def test_chat_send_rejects_invalid_message(self):
        self._login_student()

        response = self.client.post(
            self.send_url,
            data=json.dumps({"message": ""}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Mensagem inválida."})

    @patch("website.views.build_answer")
    def test_chat_send_returns_answer_and_updates_session(self, build_answer_mock):
        snippet = RetrievedSnippet(
            material_id=self.material.pk,
            title=self.material.title,
            excerpt="As férias começam em julho.",
            score=2,
        )
        build_answer_mock.return_value = ("As férias começam em julho.", [snippet])
        self._login_student()

        response = self.client.post(
            self.send_url,
            data=json.dumps({"message": "Quando começam as férias?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "reply": "As férias começam em julho.",
                "sources": [
                    {
                        "title": "Calendário acadêmico",
                        "excerpt": "As férias começam em julho.",
                    }
                ],
                "history_length": 2,
            },
        )
        build_answer_mock.assert_called_once_with(
            self.chatbot,
            "Quando começam as férias?",
            include_private=True,
        )
        self.assertEqual(
            self.client.session[f"chat_history_{self.chatbot.pk}"],
            [
                {"role": "user", "content": "Quando começam as férias?"},
                {
                    "role": "assistant",
                    "content": "As férias começam em julho.",
                    "sources": [
                        {
                            "title": "Calendário acadêmico",
                            "excerpt": "As férias começam em julho.",
                        }
                    ],
                },
            ],
        )

    def test_retrieve_snippets_respects_private_material_flag(self):
        public_material = Material.objects.create(
            title="Manual público",
            text_content="Secretaria atende pela manhã.",
            file="materiais/manual.pdf",
            public=True,
        )
        self.chatbot.materials.add(public_material)

        public_only_titles = [
            snippet.title
            for snippet in retrieve_snippets(
                self.chatbot,
                "férias secretaria",
                include_private=False,
            )
        ]
        all_titles = [
            snippet.title
            for snippet in retrieve_snippets(
                self.chatbot,
                "férias secretaria",
                include_private=True,
            )
        ]

        self.assertEqual(public_only_titles, ["Manual público"])
        self.assertEqual(
            all_titles,
            ["Calendário acadêmico", "Manual público"],
        )
