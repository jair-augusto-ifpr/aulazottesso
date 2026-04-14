from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import TemplateView

from .chat_service import build_answer
from .forms import ChatMessageForm, MaterialForm, ProfessorLoginForm, StudentLoginForm
from .models import ChatBot, Professor, Student


class Index(TemplateView):
    template_name = "website/index.html"


class Sobre(TemplateView):
    template_name = "website/sobre.html"


class Contato(TemplateView):
    template_name = "website/contato.html"


def student_login_view(request):
    if request.session.get("student_id"):
        return redirect("student_dashboard")
    form = StudentLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        s = Student.objects.filter(ra=form.cleaned_data["ra"]).first()
        if s and s.password == form.cleaned_data["password"]:
            request.session["student_id"] = s.pk
            messages.success(request, "Bem-vindo(a).")
            return redirect("student_dashboard")
        messages.error(request, "RA ou senha incorretos.")
    return render(request, "website/estudante/login.html", {"form": form})


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
    sid = request.session.get("student_id")
    if not sid:
        return redirect("student_login")
    student = get_object_or_404(Student, pk=sid)
    chatbot = get_object_or_404(ChatBot, pk=chatbot_id)
    if not _student_can_use_chatbot(student, chatbot):
        messages.error(request, "Você não tem acesso a este chatbot.")
        return redirect("student_dashboard")

    session_key = f"chat_history_{chatbot_id}"
    history: list = request.session.get(session_key, [])

    if request.method == "POST":
        form = ChatMessageForm(request.POST)
        if form.is_valid():
            text = form.cleaned_data["message"].strip()
            if text:
                answer, _snippets = build_answer(
                    chatbot, text, include_private=True
                )
                history = history + [
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": answer},
                ]
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


def professor_login_view(request):
    if request.session.get("professor_id"):
        return redirect("professor_dashboard")
    form = ProfessorLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        p = Professor.objects.filter(siape=form.cleaned_data["siape"]).first()
        if p and p.password == form.cleaned_data["password"]:
            request.session["professor_id"] = p.pk
            messages.success(request, "Bem-vindo(a).")
            return redirect("professor_dashboard")
        messages.error(request, "SIAPE ou senha incorretos.")
    return render(request, "website/professor/login.html", {"form": form})


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
