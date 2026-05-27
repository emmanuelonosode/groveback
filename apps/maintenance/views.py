from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied
from .models import MaintenanceRequest
from .serializers import MaintenanceRequestListSerializer, MaintenanceRequestDetailSerializer


def _get_client(user):
    from apps.crm.models import Client
    return Client.objects.filter(user=user).first()


class MaintenanceRequestListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/maintenance/"""
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return MaintenanceRequestDetailSerializer if self.request.method == "POST" else MaintenanceRequestListSerializer

    def get_queryset(self):
        client = _get_client(self.request.user)
        if not client:
            return MaintenanceRequest.objects.none()
        return MaintenanceRequest.objects.filter(client=client)

    def perform_create(self, serializer):
        client = _get_client(self.request.user)
        if not client:
            raise PermissionDenied("Your account is not linked to a tenancy. Contact our team.")
        serializer.save(client=client)


class MaintenanceRequestDetailView(generics.RetrieveAPIView):
    """GET /api/v1/maintenance/{id}/"""
    serializer_class   = MaintenanceRequestDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        client = _get_client(self.request.user)
        if not client:
            return MaintenanceRequest.objects.none()
        return MaintenanceRequest.objects.filter(client=client)
