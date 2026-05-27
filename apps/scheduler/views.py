from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from apps.accounts.permissions import IsAgentOrAbove
from .models import Viewing
from .serializers import ViewingSerializer


class ViewingListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/viewings/"""
    serializer_class = ViewingSerializer
    permission_classes = [IsAgentOrAbove]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["status", "agent", "property"]
    ordering_fields = ["scheduled_at", "created_at"]
    ordering = ["scheduled_at"]

    def get_queryset(self):
        qs = Viewing.objects.select_related("lead", "property", "agent")
        user = self.request.user
        if user.role == "AGENT":
            return qs.filter(agent=user)
        return qs

    def perform_create(self, serializer):
        viewing = serializer.save()
        # Log activity on the lead
        try:
            from apps.crm.models import LeadActivity
            LeadActivity.objects.create(
                lead=viewing.lead,
                agent=self.request.user,
                activity_type="VIEWING_BOOKED",
                note=f"Viewing booked at {viewing.property.title} on {viewing.scheduled_at:%Y-%m-%d %H:%M}.",
            )
        except Exception:
            pass


class ViewingDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/viewings/{id}/"""
    serializer_class = ViewingSerializer
    permission_classes = [IsAgentOrAbove]

    def get_queryset(self):
        qs = Viewing.objects.select_related("lead", "property", "agent")
        user = self.request.user
        if user.role == "AGENT":
            return qs.filter(agent=user)
        return qs


@api_view(["GET"])
@permission_classes([IsAgentOrAbove])
def viewing_calendar(request):
    """GET /api/v1/viewings/calendar/?start=2025-01-01&end=2025-01-31"""
    from datetime import datetime

    start = request.query_params.get("start")
    end = request.query_params.get("end")

    qs = Viewing.objects.select_related("lead", "property", "agent")
    if request.user.role == "AGENT":
        qs = qs.filter(agent=request.user)

    if start:
        try:
            qs = qs.filter(scheduled_at__date__gte=datetime.strptime(start, "%Y-%m-%d").date())
        except ValueError:
            pass
    if end:
        try:
            qs = qs.filter(scheduled_at__date__lte=datetime.strptime(end, "%Y-%m-%d").date())
        except ValueError:
            pass

    serializer = ViewingSerializer(qs, many=True)
    return Response(serializer.data)
