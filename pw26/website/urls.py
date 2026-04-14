from django.urls import path

from . import views

urlpatterns = [
    path("", views.Index.as_view(), name="home"),
    path("sobre/", views.Sobre.as_view(), name="sobre"),
    path("contato/", views.Contato.as_view(), name="contato"),
    path("estudante/entrar/", views.student_login_view, name="student_login"),
    path("estudante/sair/", views.student_logout_view, name="student_logout"),
    path("estudante/", views.student_dashboard_view, name="student_dashboard"),
    path(
        "estudante/chat/<int:chatbot_id>/",
        views.student_chat_view,
        name="student_chat",
    ),
    path("professor/entrar/", views.professor_login_view, name="professor_login"),
    path("professor/sair/", views.professor_logout_view, name="professor_logout"),
    path(
        "professor/material/novo/",
        views.professor_material_create_view,
        name="professor_material_new",
    ),
    path("professor/", views.professor_dashboard_view, name="professor_dashboard"),
]
