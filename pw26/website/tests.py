import json
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .chat_service import AnswerResult, RetrievedSnippet, retrieve_snippets
from .constants import GROUP_ALUNO, GROUP_PROFESSOR
from .models import (
    ChatBot,
    Conversation,
    Course,
    Material,
    Message,
    Professor,
    ProfessorConfig,
    Student,
)


class ChatFlowTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(name="Informática")
        aluno_group, _ = Group.objects.get_or_create(name=GROUP_ALUNO)
        prof_group, _ = Group.objects.get_or_create(name=GROUP_PROFESSOR)

        student_user = User.objects.create_user(
            username="2026001",
            email="ana@example.com",
            password="testpass123",
        )
        student_user.groups.add(aluno_group)
        self.student = Student.objects.create(
            user=student_user,
            name="Ana Estudante",
            ra="2026001",
        )
        self.student.courses.add(self.course)

        professor_user = User.objects.create_user(
            username="12345",
            email="bruno@example.com",
            password="testpass123",
        )
        professor_user.groups.add(prof_group)
        self.professor = Professor.objects.create(
            user=professor_user,
            name="Prof. Bruno",
            siape="12345",
        )
        self.professor.courses.add(self.course)
        self.config = ProfessorConfig.objects.create(
            professor=self.professor,
            provider=ProfessorConfig.PROVIDER_GEMINI,
            api_key="chave-de-teste",
            model="gemini-2.5-flash",
            token_limit_per_student=0,
            limit_period_days=0,
        )

        self.material = Material.objects.create(
            owner=self.professor,
            title="Calendário acadêmico",
            text_content="As férias começam em julho.",
            public=False,
        )
        self.material.courses.add(self.course)
        self.chatbot = ChatBot.objects.create(
            owner=self.professor,
            prompt="Responda de forma breve.",
        )
        self.chatbot.courses.add(self.course)
        self.chatbot.materials.add(self.material)
        self.send_url = reverse("student_chat_send", args=[self.chatbot.pk])

    def _login_student(self, student=None):
        user = (student or self.student).user
        self.client.force_login(user)

    def _new_conversation(self, student=None):
        return Conversation.objects.create(
            student=student or self.student, chatbot=self.chatbot
        )

    def _post(self, payload):
        return self.client.post(
            self.send_url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _answer_result(self):
        snippet = RetrievedSnippet(
            material_id=self.material.pk,
            title=self.material.title,
            excerpt="As férias começam em julho.",
            score=2,
        )
        return AnswerResult(
            text="As férias começam em julho.",
            snippets=[snippet],
            provider="gemini",
            model="gemini-2.5-flash",
            tokens_prompt=10,
            tokens_completion=20,
            tokens_total=30,
        )

    def test_chat_send_requires_student_course_access(self):
        other_user = User.objects.create_user(
            username="2026002",
            email="carlos@example.com",
            password="testpass123",
        )
        other_user.groups.add(Group.objects.get(name=GROUP_ALUNO))
        other_student = Student.objects.create(
            user=other_user, name="Carlos", ra="2026002"
        )
        self._login_student(other_student)

        response = self._post({"message": "Olá?", "conversa": 1})
        self.assertEqual(response.status_code, 403)

    def test_chat_send_requires_started_conversation(self):
        self._login_student()
        response = self._post({"message": "Quando começam as férias?"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Inicie uma conversa", response.json()["error"])

    def test_chat_send_rejects_invalid_message(self):
        self._login_student()
        conversation = self._new_conversation()
        response = self._post({"message": "", "conversa": conversation.pk})
        self.assertEqual(response.status_code, 400)

    def test_chat_send_blocked_without_professor_api(self):
        self.config.api_key = ""
        self.config.save()
        self._login_student()
        conversation = self._new_conversation()
        response = self._post(
            {"message": "Quando começam as férias?", "conversa": conversation.pk}
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("API", response.json()["error"])

    def test_chat_send_blocked_when_token_limit_reached(self):
        self.config.token_limit_per_student = 20
        self.config.save()
        conversation = self._new_conversation()
        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_ASSISTANT,
            content="resposta anterior",
            tokens_total=25,
        )
        self._login_student()
        response = self._post(
            {"message": "Mais uma pergunta?", "conversa": conversation.pk}
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("limite", response.json()["error"].lower())

    @patch("website.views.build_answer")
    def test_chat_send_returns_answer_and_persists_tokens(self, build_answer_mock):
        build_answer_mock.return_value = self._answer_result()
        self._login_student()
        conversation = self._new_conversation()

        response = self._post(
            {"message": "Quando começam as férias?", "conversa": conversation.pk}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["reply"], "As férias começam em julho.")
        self.assertEqual(data["model"], "gemini-2.5-flash")
        self.assertEqual(data["tokens_total"], 30)
        self.assertEqual(data["usage"]["used"], 30)

        conversation.refresh_from_db()
        self.assertEqual(conversation.messages.count(), 2)
        assistant = conversation.messages.get(role=Message.ROLE_ASSISTANT)
        self.assertEqual(assistant.tokens_total, 30)
        self.assertEqual(assistant.model_name, "gemini-2.5-flash")

        build_answer_mock.assert_called_once()
        args, kwargs = build_answer_mock.call_args
        self.assertEqual(args[0], self.chatbot)
        self.assertEqual(args[1], "Quando começam as férias?")
        self.assertTrue(kwargs["include_private"])
        self.assertEqual(kwargs["config"], self.config)

    def test_conversation_create_endpoint(self):
        self._login_student()
        url = reverse("student_conversation_create", args=[self.chatbot.pk])
        response = self.client.post(url, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("conversation_id", response.json())
        self.assertTrue(
            Conversation.objects.filter(
                pk=response.json()["conversation_id"], student=self.student
            ).exists()
        )

    @patch("website.views.build_answer")
    def test_chat_send_creates_conversation_when_missing(self, build_answer_mock):
        build_answer_mock.return_value = self._answer_result()
        self._login_student()
        response = self._post({"message": "Quando começam as férias?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("conversation_id", data)
        self.assertTrue(
            Conversation.objects.filter(
                pk=data["conversation_id"], student=self.student, chatbot=self.chatbot
            ).exists()
        )

    def test_retrieve_snippets_respects_private_material_flag(self):
        public_material = Material.objects.create(
            owner=self.professor,
            title="Manual público",
            text_content="Secretaria atende pela manhã.",
            public=True,
        )
        self.chatbot.materials.add(public_material)

        public_only_titles = [
            snippet.title
            for snippet in retrieve_snippets(
                self.chatbot, "férias secretaria", include_private=False
            )
        ]
        all_titles = [
            snippet.title
            for snippet in retrieve_snippets(
                self.chatbot, "férias secretaria", include_private=True
            )
        ]

        self.assertEqual(public_only_titles, ["Manual público"])
        self.assertEqual(all_titles, ["Calendário acadêmico", "Manual público"])


class MaterialExtractionTests(TestCase):
    def test_apply_extraction_replaces_short_manual_text(self):
        from unittest.mock import patch

        from website.text_extraction import apply_material_text_extraction

        prof_group, _ = Group.objects.get_or_create(name=GROUP_PROFESSOR)
        user = User.objects.create_user(username="ext01", password="testpass123")
        user.groups.add(prof_group)
        professor = Professor.objects.create(user=user, name="Prof", siape="ext01")

        material = Material.objects.create(
            owner=professor,
            title="Calendário",
            text_content="CALENDÁRIO ACADÊMICO 2026",
            public=True,
        )
        material.file.name = "calendario.pdf"

        long_text = "Férias de julho de 13 a 31 de julho de 2026. " * 50
        with patch(
            "website.text_extraction.extract_text_from_upload",
            return_value=long_text,
        ):
            chars = apply_material_text_extraction(material, prefer_file=True)

        material.refresh_from_db()
        self.assertGreater(chars, len("CALENDÁRIO ACADÊMICO 2026"))
        self.assertIn("julho", material.text_content.lower())
        self.assertEqual(material.text_content, long_text.strip())


class ProfessorMonitoringTests(TestCase):
    def setUp(self):
        prof_group, _ = Group.objects.get_or_create(name=GROUP_PROFESSOR)
        self.course = Course.objects.create(name="Informática")

        professor_user = User.objects.create_user(
            username="99999", password="testpass123"
        )
        professor_user.groups.add(prof_group)
        self.professor = Professor.objects.create(
            user=professor_user, name="Prof. Ana", siape="99999"
        )
        self.professor.courses.add(self.course)

        aluno_group, _ = Group.objects.get_or_create(name=GROUP_ALUNO)
        student_user = User.objects.create_user(
            username="30001", password="testpass123"
        )
        student_user.groups.add(aluno_group)
        self.student = Student.objects.create(
            user=student_user, name="Aluno X", ra="30001"
        )
        self.student.courses.add(self.course)

        self.chatbot = ChatBot.objects.create(owner=self.professor, prompt="p")
        self.chatbot.courses.add(self.course)
        self.conversation = Conversation.objects.create(
            student=self.student, chatbot=self.chatbot, title="Dúvida"
        )
        Message.objects.create(
            conversation=self.conversation,
            role=Message.ROLE_ASSISTANT,
            content="resposta",
            tokens_total=42,
        )

    def test_professor_sees_own_conversations(self):
        self.client.force_login(self.professor.user)
        response = self.client.get(reverse("professor_conversation_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dúvida")

    def test_professor_cannot_open_foreign_conversation(self):
        other_user = User.objects.create_user(
            username="88888", password="testpass123"
        )
        other_user.groups.add(Group.objects.get(name=GROUP_PROFESSOR))
        Professor.objects.create(user=other_user, name="Outro", siape="88888")
        self.client.force_login(other_user)

        response = self.client.get(
            reverse("professor_conversation_detail", args=[self.conversation.pk])
        )
        self.assertEqual(response.status_code, 404)


class NavigationTests(TestCase):
    def setUp(self):
        from django.test import RequestFactory

        self.factory = RequestFactory()

    def _request(self, path, *, referer=None, from_param=None, method="GET", post_from=None):
        if method == "POST":
            request = self.factory.post(path, data={"from": post_from} if post_from else {})
        else:
            data = {"from": from_param} if from_param else {}
            request = self.factory.get(path, data=data)
        request.META["HTTP_HOST"] = "testserver"
        if referer:
            request.META["HTTP_REFERER"] = referer
        return request

    def test_from_param_takes_priority_over_referer(self):
        from website.navigation import get_return_url

        request = self._request(
            "/professor/cursos/novo/",
            from_param="/professor/cursos/",
            referer="http://testserver/professor/",
        )
        self.assertEqual(get_return_url(request), "/professor/cursos/")

    def test_referer_used_when_no_from_param(self):
        from website.navigation import get_return_url

        request = self._request(
            "/professor/cursos/novo/",
            referer="http://testserver/professor/cursos/",
        )
        self.assertEqual(get_return_url(request), "/professor/cursos/")

    def test_unsafe_referer_falls_back(self):
        from website.navigation import get_return_url

        request = self._request(
            "/professor/cursos/novo/",
            referer="http://evil.example/phish",
        )
        self.assertEqual(
            get_return_url(request, fallback="/professor/"),
            "/professor/",
        )

    def test_label_for_course_list(self):
        from website.navigation import resolve_back_navigation

        request = self._request(
            "/professor/cursos/novo/",
            from_param="/professor/cursos/",
        )
        back_url, back_label = resolve_back_navigation(
            request,
            fallback_url="/professor/",
            fallback_label="Painel",
        )
        self.assertEqual(back_url, "/professor/cursos/")
        self.assertEqual(back_label, "Cursos")

    def test_course_create_back_from_list(self):
        prof_group, _ = Group.objects.get_or_create(name=GROUP_PROFESSOR)
        user = User.objects.create_user(username="11111", password="testpass123")
        user.groups.add(prof_group)
        Professor.objects.create(user=user, name="Prof", siape="11111")

        self.client.force_login(user)
        course_list = reverse("professor_course_list")
        create_url = reverse("professor_course_new")
        response = self.client.get(f"{create_url}?from={course_list}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{course_list}"')
        self.assertContains(response, "Cursos")

    def test_student_conversation_list_back_via_navbar(self):
        aluno_group, _ = Group.objects.get_or_create(name=GROUP_ALUNO)
        user = User.objects.create_user(username="2023999", password="testpass123")
        user.groups.add(aluno_group)
        Student.objects.create(user=user, name="Aluno Teste", ra="2023999")

        self.client.force_login(user)
        panel = reverse("student_dashboard")
        response = self.client.get(
            f"{reverse('student_conversation_list')}?from={panel}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{panel}"')
        self.assertContains(response, "Painel")

    def test_student_conversation_list_back_via_internal_chat(self):
        aluno_group, _ = Group.objects.get_or_create(name=GROUP_ALUNO)
        prof_group, _ = Group.objects.get_or_create(name=GROUP_PROFESSOR)
        course = Course.objects.create(name="Informática")
        professor_user = User.objects.create_user(username="99999", password="testpass123")
        professor_user.groups.add(prof_group)
        professor = Professor.objects.create(
            user=professor_user, name="Prof. Teste", siape="99999"
        )
        professor.courses.add(course)
        chatbot = ChatBot.objects.create(owner=professor, prompt="Teste.")
        chatbot.courses.add(course)

        user = User.objects.create_user(username="2023888", password="testpass123")
        user.groups.add(aluno_group)
        student = Student.objects.create(user=user, name="Aluno Chat", ra="2023888")
        student.courses.add(course)

        self.client.force_login(user)
        chat_url = reverse("student_chat", args=[chatbot.pk])
        conv_list = reverse("student_conversation_list")
        response = self.client.get(f"{conv_list}?from={chat_url}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{chat_url}"')
        self.assertContains(response, "Chat")
