import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import TemplateView

from .chat_service import build_answer
from .forms import (
    ChatBotForm,
    ChatMessageForm,
    MaterialForm,
    ProfessorLoginForm,
    ProfessorSignupForm,
    StudentLoginForm,
    StudentSignupForm,
)
from .models import ChatBot, Professor, Student
from .passwords import check_password_for, set_password
from .text_extraction import extract_text_from_upload


class Index(TemplateView):
    template_name = "website/index.html"


class Sobre(TemplateView):
    template_name = "website/sobre.html"


class Contato(TemplateView):
    template_name = "website/contato.html"


def _serialize_snippets(snippets):
    return [{"title": s.title, "excerpt": s.excerpt} for s in snippets]


def _append_chat_history(history, question: str, answer: str, snippets):
    return history + [
        {"role": "user", "content": question},
        {
            "role": "assistant",
            "content": answer,
            "sources": _serialize_snippets(snippets),
        },
    ]


def _get_chat_context_or_redirect(request, chatbot_id: int):
    sid = request.session.get("student_id")
    if not sid:
        return None, None, None, redirect("student_login")

    student = get_object_or_404(Student, pk=sid)
    chatbot = get_object_or_404(ChatBot, pk=chatbot_id)
    if not _student_can_use_chatbot(student, chatbot):
        messages.error(request, "Você não tem acesso a este chatbot.")
        return None, None, None, redirect("student_dashboard")

    session_key = f"chat_history_{chatbot_id}"
    history = request.session.get(session_key, [])
    return student, chatbot, history, None


def student_login_view(request):
    if request.session.get("student_id"):
        return redirect("student_dashboard")
    form = StudentLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        s = Student.objects.filter(ra=form.cleaned_data["ra"]).first()
        if s and check_password_for(s, form.cleaned_data["password"]):
            request.session["student_id"] = s.pk
            messages.success(request, "Bem-vindo(a).")
            return redirect("student_dashboard")
        messages.error(request, "RA ou senha incorretos.")
    return render(request, "website/estudante/login.html", {"form": form})


def student_signup_view(request):
    if request.session.get("student_id"):
        return redirect("student_dashboard")
    form = StudentSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        student = form.save(commit=False)
        set_password(student, form.cleaned_data["password"])
        student.save()
        form.save_m2m()
        request.session["student_id"] = student.pk
        messages.success(request, "Cadastro concluído. Bem-vindo(a).")
        return redirect("student_dashboard")
    return render(request, "website/estudante/signup.html", {"form": form})


def student_logout_view(request):
    request.session.pop("student_id", None)
    messages.info(request, "Sessão encerrada.")
    return redirect("home")


def student_dashboard_view(request):
    sid = request.session.get("student_id")
    if not sid:
        return redirect("student_login")
    student = get_object_or_404(Student, pk=sid)
    rows = []
    for course in student.courses.all():
        rows.append({"course": course, "chatbots": course.chatbots.all()})
    return render(
        request,
        "website/estudante/dashboard.html",
        {"student": student, "rows": rows},
    )


def _student_can_use_chatbot(student: Student, chatbot: ChatBot) -> bool:
    sc = set(student.courses.values_list("pk", flat=True))
    bc = set(chatbot.courses.values_list("pk", flat=True))
    return bool(sc & bc)


def student_chat_view(request, chatbot_id: int):
    student, chatbot, history, redirect_response = _get_chat_context_or_redirect(
        request, chatbot_id
    )
    if redirect_response:
        return redirect_response

    session_key = f"chat_history_{chatbot_id}"

    if request.method == "POST":
        form = ChatMessageForm(request.POST)
        if form.is_valid():
            text = form.cleaned_data["message"].strip()
            if text:
                answer, snippets = build_answer(
                    chatbot, text, include_private=True
                )
                history = _append_chat_history(history, text, answer, snippets)
                request.session[session_key] = history[-40:]
                request.session.modified = True
            return redirect("student_chat", chatbot_id=chatbot_id)
    else:
        form = ChatMessageForm()

    return render(
        request,
        "website/estudante/chat.html",
        {
            "student": student,
            "chatbot": chatbot,
            "form": form,
            "history": history,
        },
    )


def student_chat_send_view(request, chatbot_id: int):
    if request.method != "POST":
        return JsonResponse({"error": "Método não permitido."}, status=405)

    student, chatbot, history, redirect_response = _get_chat_context_or_redirect(
        request, chatbot_id
    )
    if redirect_response:
        return JsonResponse({"error": "Sem permissão para acessar este chatbot."}, status=403)

    payload = request.POST.dict()
    if not payload and request.body:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
    form = ChatMessageForm(payload or None)
    if not form.is_valid():
        return JsonResponse({"error": "Mensagem inválida."}, status=400)

    text = form.cleaned_data["message"].strip()
    if not text:
        return JsonResponse({"error": "Mensagem vazia."}, status=400)

    answer, snippets = build_answer(chatbot, text, include_private=True)
    history = _append_chat_history(history, text, answer, snippets)
    session_key = f"chat_history_{chatbot_id}"
    request.session[session_key] = history[-40:]
    request.session.modified = True
    return JsonResponse(
        {
            "reply": answer,
            "sources": _serialize_snippets(snippets),
            "history_length": len(request.session[session_key]),
        }
    )


def professor_login_view(request):
    if request.session.get("professor_id"):
        return redirect("professor_dashboard")
    form = ProfessorLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        p = Professor.objects.filter(siape=form.cleaned_data["siape"]).first()
        if p and check_password_for(p, form.cleaned_data["password"]):
            request.session["professor_id"] = p.pk
            messages.success(request, "Bem-vindo(a).")
            return redirect("professor_dashboard")
        messages.error(request, "SIAPE ou senha incorretos.")
    return render(request, "website/professor/login.html", {"form": form})


def professor_signup_view(request):
    if request.session.get("professor_id"):
        return redirect("professor_dashboard")
    form = ProfessorSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        professor = form.save(commit=False)
        set_password(professor, form.cleaned_data["password"])
        professor.save()
        form.save_m2m()
        request.session["professor_id"] = professor.pk
        messages.success(request, "Cadastro concluído. Bem-vindo(a).")
        return redirect("professor_dashboard")
    return render(request, "website/professor/signup.html", {"form": form})


def professor_logout_view(request):
    request.session.pop("professor_id", None)
    messages.info(request, "Sessão encerrada.")
    return redirect("home")


def professor_dashboard_view(request):
    pid = request.session.get("professor_id")
    if not pid:
        return redirect("professor_login")
    professor = get_object_or_404(Professor, pk=pid)
    return render(
        request,
        "website/professor/dashboard.html",
        {
            "professor": professor,
            "chatbots": professor.chatbots.all(),
        },
    )


def professor_material_create_view(request):
    pid = request.session.get("professor_id")
    if not pid:
        return redirect("professor_login")
    professor = get_object_or_404(Professor, pk=pid)
    form = MaterialForm(
        request.POST or None,
        request.FILES or None,
        professor=professor,
    )
    if request.method == "POST" and form.is_valid():
        material = form.save(commit=False)
        if not (material.text_content or "").strip() and material.file:
            extracted = extract_text_from_upload(material.file)
            if extracted.strip():
                material.text_content = extracted
                messages.info(request, f"Texto extraído automaticamente: {len(extracted)} caracteres.")
        material.save()
        form.save_m2m()
        for bot in form.cleaned_data.get("chatbots", []):
            bot.materials.add(material)
        messages.success(request, "Material cadastrado.")
        return redirect("professor_dashboard")
    return render(
        request,
        "website/professor/material_form.html",
        {"form": form, "professor": professor},
    )


def professor_chatbot_create_view(request):
    pid = request.session.get("professor_id")
    if not pid:
        return redirect("professor_login")
    professor = get_object_or_404(Professor, pk=pid)
    form = ChatBotForm(request.POST or None, professor=professor)
    if request.method == "POST" and form.is_valid():
        chatbot = form.save(commit=False)
        chatbot.professor = professor
        chatbot.save()
        form.save_m2m()
        messages.success(request, "Chatbot criado.")
        return redirect("professor_dashboard")
    return render(
        request,
        "website/professor/chatbot_form.html",
        {"form": form, "professor": professor, "is_edit": False},
    )


def professor_chatbot_edit_view(request, chatbot_id: int):
    pid = request.session.get("professor_id")
    if not pid:
        return redirect("professor_login")
    professor = get_object_or_404(Professor, pk=pid)
    chatbot = get_object_or_404(ChatBot, pk=chatbot_id)
    if chatbot.professor_id != professor.pk:
        messages.error(request, "Você não pode editar este chatbot.")
        return redirect("professor_dashboard")

    form = ChatBotForm(request.POST or None, instance=chatbot, professor=professor)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Chatbot atualizado.")
        return redirect("professor_dashboard")
    return render(
        request,
        "website/professor/chatbot_form.html",
        {"form": form, "professor": professor, "chatbot": chatbot, "is_edit": True},
    )


def professor_chatbot_delete_view(request, chatbot_id: int):
    pid = request.session.get("professor_id")
    if not pid:
        return redirect("professor_login")
    professor = get_object_or_404(Professor, pk=pid)
    chatbot = get_object_or_404(ChatBot, pk=chatbot_id)
    if chatbot.professor_id != professor.pk:
        messages.error(request, "Você não pode excluir este chatbot.")
        return redirect("professor_dashboard")

    if request.method == "POST":
        chatbot.delete()
        messages.success(request, "Chatbot excluído.")
        return redirect("professor_dashboard")
    return render(
        request,
        "website/professor/chatbot_confirm_delete.html",
        {"professor": professor, "chatbot": chatbot},
    )
