import logging

from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from apps.accounts.permissions import IsAgentOrAbove, IsManagerOrAbove

logger = logging.getLogger(__name__)
from .models import Lead, LeadActivity, Client, LeadStatus, RentalApplication, ApplicationStatus
from .serializers import (
    LeadCreateSerializer, LeadListSerializer, LeadDetailSerializer,
    LeadActivitySerializer, LeadAssignSerializer, ClientSerializer,
    RentalApplicationCreateSerializer, RentalApplicationAdminSerializer,
    RentalApplicationLatestProfileSerializer, RentalApplicationDraftSerializer,
)


# ... (keep other views)

class RentalApplicationLatestProfileView(generics.RetrieveAPIView):
    """GET /api/v1/leads/latest-profile/ — fetch most recent application for autofill."""
    serializer_class = RentalApplicationLatestProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        user = self.request.user
        application = RentalApplication.objects.filter(
            email=user.email
        ).order_by("-submitted_at").first()
        
        if not application:
            from django.http import Http404
            raise Http404("No previous application found.")
        return application


class SaveDraftView(generics.GenericAPIView):
    """
    POST /api/v1/leads/apply/save-draft/
    Creates or updates a DRAFT RentalApplication so admins can follow up
    with applicants who didn't complete the form.
    Body: partial form data + optional draft_id.
    Response: { draft_id: <int> }
    Permission: AllowAny — user may not be authenticated yet.
    """
    serializer_class = RentalApplicationDraftSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        draft_id = request.data.get("draft_id")

        if draft_id:
            draft = RentalApplication.objects.filter(
                pk=draft_id, status=ApplicationStatus.DRAFT
            ).first()
            if draft:
                serializer = self.get_serializer(draft, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                return Response({"draft_id": draft.id}, status=status.HTTP_200_OK)

        # No valid existing draft — create a new one
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = x_forwarded.split(",")[0].strip() if x_forwarded else request.META.get("REMOTE_ADDR")
        draft = serializer.save(status=ApplicationStatus.DRAFT, ip_address=ip)
        return Response({"draft_id": draft.id}, status=status.HTTP_201_CREATED)


class LeadListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/leads/  — staff see all or own leads
    POST /api/v1/leads/  — public (contact form submission)
    """
    queryset = Lead.objects.select_related("assigned_agent", "property_interest").all()
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "source", "interest_type", "assigned_agent"]
    search_fields = ["full_name", "email", "phone", "preferred_location"]
    ordering_fields = ["created_at", "last_contacted_at", "status"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return LeadCreateSerializer
        return LeadListSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.AllowAny()]
        return [IsAgentOrAbove()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user or not user.is_authenticated:
            return qs.none()
        # Agents see only their assigned leads
        if user.role == "AGENT":
            return qs.filter(assigned_agent=user)
        return qs

    def perform_create(self, serializer):
        lead = serializer.save()
        # Notify agent/managers of new lead
        try:
            from apps.notifications.tasks import send_lead_notification
            send_lead_notification(lead.id)
        except Exception as e:
            logger.error("send_lead_notification failed for lead %s: %s", lead.id, e)
        # Send acknowledgment email only when an email address was provided
        if lead.email:
            try:
                from apps.notifications.tasks import send_lead_acknowledgment_email
                send_lead_acknowledgment_email(lead.id)
            except Exception as e:
                logger.error("send_lead_acknowledgment_email failed for lead %s: %s", lead.id, e)


class LeadDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/leads/{id}/"""
    queryset = Lead.objects.select_related("assigned_agent", "property_interest", "agent_interest").prefetch_related("activities__agent")
    permission_classes = [IsAgentOrAbove]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return LeadDetailSerializer
        return LeadDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.role == "AGENT":
            return qs.filter(assigned_agent=user)
        return qs

    def perform_update(self, serializer):
        lead = serializer.save()
        # Track last_contacted_at if status changed from NEW
        if lead.status != LeadStatus.NEW:
            Lead.objects.filter(pk=lead.pk, last_contacted_at__isnull=True).update(
                last_contacted_at=timezone.now()
            )


@api_view(["POST"])
@permission_classes([IsManagerOrAbove])
def lead_assign(request, pk):
    """POST /api/v1/leads/{id}/assign/ — assign to an agent."""
    try:
        lead = Lead.objects.get(pk=pk)
    except Lead.DoesNotExist:
        return Response({"detail": "Lead not found."}, status=status.HTTP_404_NOT_FOUND)

    serializer = LeadAssignSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    from apps.accounts.models import CustomUser
    agent = CustomUser.objects.get(id=serializer.validated_data["agent_id"])
    lead.assigned_agent = agent
    lead.save(update_fields=["assigned_agent", "updated_at"])

    # Log the assignment as a NOTE activity
    LeadActivity.objects.create(
        lead=lead,
        agent=request.user,
        activity_type="NOTE",
        note=f"Lead assigned to {agent.full_name} by {request.user.full_name}.",
    )

    return Response({"detail": f"Lead assigned to {agent.full_name}."})


class LeadActivityListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/leads/{pk}/activity/"""
    serializer_class = LeadActivitySerializer
    permission_classes = [IsAgentOrAbove]

    def get_queryset(self):
        return LeadActivity.objects.filter(lead_id=self.kwargs["pk"]).select_related("agent")

    def perform_create(self, serializer):
        lead = Lead.objects.get(pk=self.kwargs["pk"])
        serializer.save(lead=lead, agent=self.request.user)
        # Update last_contacted_at
        lead.last_contacted_at = timezone.now()
        lead.save(update_fields=["last_contacted_at"])


@api_view(["GET"])
@permission_classes([IsAgentOrAbove])
def lead_pipeline(request):
    """GET /api/v1/leads/pipeline/ — kanban counts by status."""
    from django.db.models import Count

    qs = Lead.objects.all()
    if request.user.role == "AGENT":
        qs = qs.filter(assigned_agent=request.user)

    counts = qs.values("status").annotate(count=Count("id"))
    pipeline = {s[0]: 0 for s in LeadStatus.choices}
    for row in counts:
        pipeline[row["status"]] = row["count"]

    return Response({"pipeline": pipeline, "total": sum(pipeline.values())})


class ClientListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/clients/"""
    serializer_class = ClientSerializer
    permission_classes = [IsAgentOrAbove]

    def get_queryset(self):
        qs = Client.objects.select_related("lead", "preferred_agent", "user")
        user = self.request.user
        if user.role == "AGENT":
            return qs.filter(preferred_agent=user)
        return qs


class ClientDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/clients/{id}/"""
    serializer_class = ClientSerializer
    permission_classes = [IsAgentOrAbove]

    def get_queryset(self):
        qs = Client.objects.select_related("lead", "preferred_agent", "user")
        user = self.request.user
        if user.role == "AGENT":
            return qs.filter(preferred_agent=user)
        return qs


# ── Rental Application Views ───────────────────────────────────────────────────

class UserRentalApplicationListView(generics.ListAPIView):
    """GET /api/v1/leads/apply/my-applications/ — User's own applications."""
    serializer_class = RentalApplicationAdminSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return RentalApplication.objects.filter(
            email=self.request.user.email
        ).select_related("rental_property").order_by("-submitted_at")

class RentalApplicationCreateView(generics.CreateAPIView):
    """POST /api/v1/leads/apply/ — public form submission."""
    serializer_class   = RentalApplicationCreateSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        x_forwarded = self.request.META.get("HTTP_X_FORWARDED_FOR")
        ip = x_forwarded.split(",")[0].strip() if x_forwarded else self.request.META.get("REMOTE_ADDR")
        application = serializer.save(ip_address=ip, status=ApplicationStatus.SUBMITTED)
        try:
            from apps.notifications.tasks import send_application_submitted_email, generate_rental_application_pdf
            send_application_submitted_email(application.id)
            generate_rental_application_pdf(application.id)
        except Exception:
            pass


class RentalApplicationDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/leads/apply/<pk>/ — staff only."""
    serializer_class   = RentalApplicationAdminSerializer
    permission_classes = [IsAgentOrAbove]
    queryset           = RentalApplication.objects.select_related("rental_property", "lead")
