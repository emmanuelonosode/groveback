from rest_framework import generics, permissions
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from apps.accounts.permissions import IsAgentOrAbove
from .models import JobApplication
from .serializers import JobApplicationCreateSerializer, JobApplicationAdminSerializer


class JobApplicationCreateView(generics.CreateAPIView):
    """POST /api/v1/careers/apply/ — public, no auth required."""
    serializer_class = JobApplicationCreateSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        application = serializer.save()
        try:
            from apps.notifications.tasks import send_job_application_notification
            send_job_application_notification(application.pk)
        except Exception:
            pass  # never let email failure block a successful submission


class JobApplicationListView(generics.ListAPIView):
    """GET /api/v1/careers/applications/ — staff only (AGENT and above)."""
    queryset = JobApplication.objects.select_related("reviewed_by").all()
    serializer_class = JobApplicationAdminSerializer
    permission_classes = [IsAgentOrAbove()]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "role_id"]
    search_fields = ["full_name", "email", "role_title", "phone"]
    ordering_fields = ["applied_at", "status", "role_title"]
    ordering = ["-applied_at"]


class JobApplicationDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/careers/applications/{id}/ — staff only."""
    queryset = JobApplication.objects.select_related("reviewed_by").all()
    serializer_class = JobApplicationAdminSerializer
    permission_classes = [IsAgentOrAbove()]

    def perform_update(self, serializer):
        serializer.save(reviewed_by=self.request.user)
