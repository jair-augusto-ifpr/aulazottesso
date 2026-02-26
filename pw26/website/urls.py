from django.urls import path
from django.views import Index

urlpatterns = [
    path("home", Index.as_view(), name="home"),
]
    