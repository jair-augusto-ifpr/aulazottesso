from django.urls import path

from . import views

urlpatterns = [
    path("", views.IndexView.as_view(), name="home"),
    path("sobre/", views.SobreView.as_view(), name="sobre"),
    path("contato/", views.ContatoView.as_view(), name="contato"),
    path("sair/", views.PortalLogoutView.as_view(), name="logout"),
    path(
        "conta/senha/alterar/",
        views.PortalPasswordChangeView.as_view(),
        name="password_change",
    ),
    # Estudante — autenticação
    path("estudante/cadastrar/", views.StudentSignupView.as_view(), name="student_signup"),
    path("estudante/entrar/", views.StudentLoginView.as_view(), name="student_login"),
    path(
        "estudante/",
        views.StudentDashboardView.as_view(),
        name="student_dashboard",
    ),
    path(
        "estudante/conversas/",
        views.StudentConversationListView.as_view(),
        name="student_conversation_list",
    ),
    path(
        "estudante/conversas/<int:pk>/excluir/",
        views.StudentConversationDeleteView.as_view(),
        name="student_conversation_delete",
    ),
    path(
        "estudante/chat/<int:chatbot_id>/",
        views.StudentChatView.as_view(),
        name="student_chat",
    ),
    path(
        "estudante/chat/<int:chatbot_id>/send/",
        views.StudentChatSendView.as_view(),
        name="student_chat_send",
    ),
    path(
        "estudante/chat/<int:chatbot_id>/conversas/nova/",
        views.StudentConversationCreateView.as_view(),
        name="student_conversation_create",
    ),
    path(
        "estudante/chat/<int:chatbot_id>/conversas/<int:conversation_id>/mensagens/",
        views.StudentConversationMessagesView.as_view(),
        name="student_conversation_messages",
    ),
    # Professor — autenticação
    path(
        "professor/cadastrar/",
        views.ProfessorSignupView.as_view(),
        name="professor_signup",
    ),
    path("professor/entrar/", views.ProfessorLoginView.as_view(), name="professor_login"),
    path(
        "professor/",
        views.ProfessorDashboardView.as_view(),
        name="professor_dashboard",
    ),
    path(
        "professor/configuracao/",
        views.ProfessorConfigUpdateView.as_view(),
        name="professor_config",
    ),
    # Professor — monitoramento de conversas
    path(
        "professor/conversas/",
        views.ProfessorConversationListView.as_view(),
        name="professor_conversation_list",
    ),
    path(
        "professor/conversas/<int:pk>/",
        views.ProfessorConversationDetailView.as_view(),
        name="professor_conversation_detail",
    ),
    # Professor — cursos
    path(
        "professor/cursos/",
        views.CourseListView.as_view(),
        name="professor_course_list",
    ),
    path(
        "professor/cursos/novo/",
        views.CourseCreateView.as_view(),
        name="professor_course_new",
    ),
    path(
        "professor/cursos/<int:pk>/",
        views.CourseDetailView.as_view(),
        name="professor_course_detail",
    ),
    path(
        "professor/cursos/<int:pk>/editar/",
        views.CourseUpdateView.as_view(),
        name="professor_course_edit",
    ),
    path(
        "professor/cursos/<int:pk>/excluir/",
        views.CourseDeleteView.as_view(),
        name="professor_course_delete",
    ),
    # Professor — materiais
    path(
        "professor/materiais/",
        views.MaterialListView.as_view(),
        name="professor_material_list",
    ),
    path(
        "professor/materiais/novo/",
        views.MaterialCreateView.as_view(),
        name="professor_material_new",
    ),
    path(
        "professor/materiais/<int:pk>/",
        views.MaterialDetailView.as_view(),
        name="professor_material_detail",
    ),
    path(
        "professor/materiais/<int:pk>/editar/",
        views.MaterialUpdateView.as_view(),
        name="professor_material_edit",
    ),
    path(
        "professor/materiais/<int:pk>/excluir/",
        views.MaterialDeleteView.as_view(),
        name="professor_material_delete",
    ),
    # Professor — chatbots
    path(
        "professor/chatbots/",
        views.ChatBotListView.as_view(),
        name="professor_chatbot_list",
    ),
    path(
        "professor/chatbot/novo/",
        views.ChatBotCreateView.as_view(),
        name="professor_chatbot_new",
    ),
    path(
        "professor/chatbots/<int:pk>/",
        views.ChatBotDetailView.as_view(),
        name="professor_chatbot_detail",
    ),
    path(
        "professor/chatbot/<int:pk>/editar/",
        views.ChatBotUpdateView.as_view(),
        name="professor_chatbot_edit",
    ),
    path(
        "professor/chatbot/<int:pk>/excluir/",
        views.ChatBotDeleteView.as_view(),
        name="professor_chatbot_delete",
    ),
]
