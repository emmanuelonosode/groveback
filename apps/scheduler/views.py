import os

from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from django.core.files.storage import default_storage

from apps.accounts.permissions import IsAgentOrAbove
from .models import Viewing, TourRequest, TourRequestStatus
from .serializers import ViewingSerializer, TourRequestCreateSerializer


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


# ── Public tour requests (lead-first + ID verification) ───────────────────────

class TourRequestCreateView(generics.CreateAPIView):
    """
    POST /api/v1/viewings/tour-requests/ — public.
    Step 1 of booking a self-tour: captures the lead immediately and creates the
    tour request (status AWAITING_ID). The ID is uploaded next via verify-id.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = TourRequestCreateSerializer
    queryset = TourRequest.objects.all()


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def upload_tour_id(request, public_id):
    """
    POST /api/v1/viewings/tour-requests/<public_id>/verify-id/ — public.
    Step 2: attach the government-ID image(s) to a tour request and move it to
    PENDING_REVIEW for admin approval. Files are stored with the unguessable
    public_id as the filename prefix.
    """
    try:
        tour = TourRequest.objects.select_related("property").get(public_id=public_id)
    except (TourRequest.DoesNotExist, ValueError):
        return Response({"detail": "Tour request not found."}, status=404)

    front = request.FILES.get("id_front")
    back = request.FILES.get("id_back")
    if not front:
        return Response({"detail": "An ID photo is required."}, status=400)

    def _store(file_obj, suffix):
        ext = os.path.splitext(getattr(file_obj, "name", ""))[1].lower() or ".jpg"
        saved = default_storage.save(f"tour_ids/{tour.public_id}_{suffix}{ext}", file_obj)
        return default_storage.url(saved)

    try:
        tour.id_front = _store(front, "front")
        if back:
            tour.id_back = _store(back, "back")
    except Exception as exc:  # noqa: BLE001
        return Response({"detail": f"Upload failed: {exc}"}, status=400)

    tour.status = TourRequestStatus.PENDING_REVIEW
    tour.save(update_fields=["id_front", "id_back", "status", "updated_at"])

    # Tell staff an ID is ready to review.
    try:
        from apps.notifications.tasks import send_admin_alert
        send_admin_alert(f"Tour ID submitted — {tour.full_name}", [
            ("Property", tour.property.title),
            ("Preferred date", str(tour.preferred_date or "Flexible")),
            ("Preferred time", tour.preferred_time or "Flexible"),
            ("Phone", tour.phone or "—"),
            ("Action", "Review ID in admin → approve to book the self-tour"),
        ])
    except Exception:
        pass

    return Response({"status": "received", "public_id": str(tour.public_id)})
