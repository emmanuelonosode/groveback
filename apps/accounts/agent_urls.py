from django.urls import path
from . import views

urlpatterns = [
    path("", views.AgentListView.as_view(), name="agent-list"),
    path("<int:pk>/", views.AgentDetailView.as_view(), name="agent-detail"),
]
