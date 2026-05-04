from django.urls import path

from . import views

urlpatterns = [
    path("", views.Index.as_view(), name="home"),
    path("sobre/", views.Sobre.as_view(), name="sobre"),
    path("contato/", views.Contato.as_view(), name="contato"),
    path("estudante/cadastrar/", views.student_signup_view, name="student_signup"),
    path("estudante/entrar/", views.student_login_view, name="student_login"),
    path("estudante/sair/", views.student_logout_view, name="student_logout"),
    path("estudante/", views.student_dashboard_view, name="student_dashboard"),
    path(
        "estudante/chat/<int:chatbot_id>/",
        views.student_chat_view,
        name="student_chat",
    ),
    path(
        "estudante/chat/<int:chatbot_id>/send/",
        views.student_chat_send_view,
        name="student_chat_send",
    ),
    path("professor/cadastrar/", views.professor_signup_view, name="professor_signup"),
    path("professor/entrar/", views.professor_login_view, name="professor_login"),
    path("professor/sair/", views.professor_logout_view, name="professor_logout"),
    path(
        "professor/chatbot/novo/",
        views.professor_chatbot_create_view,
        name="professor_chatbot_new",
    ),
    path(
        "professor/chatbot/<int:chatbot_id>/editar/",
        views.professor_chatbot_edit_view,
        name="professor_chatbot_edit",
    ),
    path(
        "professor/chatbot/<int:chatbot_id>/excluir/",
        views.professor_chatbot_delete_view,
        name="professor_chatbot_delete",
    ),
    path(
        "professor/material/novo/",
        views.professor_material_create_view,
        name="professor_material_new",
    ),
    path("professor/", views.professor_dashboard_view, name="professor_dashboard"),
]
