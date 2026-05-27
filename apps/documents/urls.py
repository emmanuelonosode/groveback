from django.urls import path
from . import views

urlpatterns = [
    path("my-documents/", views.MyDocumentsView.as_view(), name="my-documents"),
]
