from django.urls import path
from .views import Index, Sobre, Contato

urlpatterns = [
    path("home", Index.as_view(), name="home"),
    path("sobre", Sobre.as_view(), name="sobre"),
    path("contato", Contato.as_view(), name="contato"),
]
