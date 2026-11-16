from django.urls import path

from . import views

urlpatterns = [
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
    path(
        "estudante/materiais/<int:material_id>/download/",
        views.StudentMaterialDownloadView.as_view(),
        name="student_material_download",
    ),
]
