from django.urls import path
from . import views

urlpatterns = [
    path("<int:agent_id>/listings/", views.AgentListingsView.as_view(), name="agent-listings"),
    path("<int:agent_id>/inquiries/", views.agent_inquiry, name="agent-inquiry"),
]
