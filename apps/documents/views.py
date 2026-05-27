from rest_framework import generics, permissions
from .models import ClientDocument
from .serializers import ClientDocumentSerializer


class MyDocumentsView(generics.ListAPIView):
    """GET /api/v1/documents/my-documents/"""
    serializer_class   = ClientDocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from apps.crm.models import Client
        client = Client.objects.filter(user=self.request.user).first()
        if not client:
            return ClientDocument.objects.none()
        return ClientDocument.objects.filter(client=client).select_related("uploaded_by")
