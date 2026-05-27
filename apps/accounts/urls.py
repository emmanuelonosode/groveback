from django.urls import path
from .views import MeView, AgentListView, AgentDetailView, RegisterView, VerifyEmailView, ResendOTPView, ChangePasswordView

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    path("register/", RegisterView.as_view(), name="register"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-otp/", ResendOTPView.as_view(), name="resend-otp"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
]

# Agent routes (also included via properties app for /agents/{id}/listings/)
agent_urlpatterns = [
    path("agents/", AgentListView.as_view(), name="agent-list"),
    path("agents/<int:pk>/", AgentDetailView.as_view(), name="agent-detail"),
]
