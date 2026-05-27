from collections import defaultdict

from django.db.models import Avg, Count, Max, Min
from django.utils.text import slugify
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Property, FavoriteProperty
from .serializers import PropertyListSerializer, PropertyDetailSerializer, FavoritePropertySerializer
from .filters import PropertyFilter
from apps.accounts.permissions import IsAgentOrAbove


class FavoritePropertyListView(generics.ListCreateAPIView):
    """GET/POST /api/v1/properties/favorites/ - Manage favorite properties"""
    serializer_class = FavoritePropertySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return FavoriteProperty.objects.filter(user=self.request.user).select_related("property")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class FavoritePropertyDetailView(generics.DestroyAPIView):
    """DELETE /api/v1/properties/favorites/{property_id}/ - Remove a favorite"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        try:
            return FavoriteProperty.objects.get(
                user=self.request.user, 
                property_id=self.kwargs["property_id"]
            )
        except FavoriteProperty.DoesNotExist:
            from django.http import Http404
            raise Http404("Favorite not found")

class FlexiblePageSize(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 200


class PropertyListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/properties/  — public list with filters
    POST /api/v1/properties/  — staff only, create listing
    """
    queryset = Property.objects.select_related("agent", "agent__agent_profile").prefetch_related("images", "amenities").distinct()
    filterset_class = PropertyFilter
    ordering_fields = ["price", "created_at", "bedrooms", "sqft"]
    ordering = ["-created_at"]
    pagination_class = FlexiblePageSize

    def get_serializer_class(self):
        return PropertyDetailSerializer if self.request.method == "POST" else PropertyListSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.AllowAny()]
        return [IsAgentOrAbove()]

    def get_queryset(self):
        qs = super().get_queryset()
        # Public users only see published properties
        if not self.request.user or not self.request.user.is_authenticated:
            return qs.filter(is_published=True)
        if self.request.user.role == "CLIENT":
            return qs.filter(is_published=True)
        return qs


class PropertyDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/v1/properties/{slug}/"""
    queryset = Property.objects.select_related("agent", "agent__agent_profile").prefetch_related("images", "amenities")
    serializer_class = PropertyDetailSerializer
    lookup_field = "slug"

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.AllowAny()]
        return [IsAgentOrAbove()]


class FeaturedPropertiesView(generics.ListAPIView):
    """GET /api/v1/properties/featured/ — for homepage ISR."""
    serializer_class = PropertyListSerializer
    permission_classes = [permissions.AllowAny]
    queryset = (
        Property.objects
        .filter(is_featured=True, is_published=True, status="available")
        .select_related("agent")
        .prefetch_related("images")
        .order_by("-created_at")[:6]
    )


class HomepagePropertiesView(generics.ListAPIView):
    """
    GET /api/v1/properties/homepage/
    Returns up to 6 properties hand-picked by the admin (homepage_featured=True).
    Falls back to is_featured if no homepage_featured properties are set.
    """
    serializer_class = PropertyListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = (
            Property.objects
            .filter(homepage_featured=True, is_published=True, status="available")
            .select_related("agent")
            .prefetch_related("images")
            .order_by("-created_at")[:6]
        )
        if qs.count() == 0:
            # Fallback: use is_featured so the homepage never shows empty
            qs = (
                Property.objects
                .filter(is_featured=True, is_published=True, status="available")
                .select_related("agent")
                .prefetch_related("images")
                .order_by("-created_at")[:6]
            )
        return qs


class AgentListingsView(generics.ListAPIView):
    """GET /api/v1/agents/{agent_id}/listings/ — public agent listings."""
    serializer_class = PropertyListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return (
            Property.objects
            .filter(agent_id=self.kwargs["agent_id"], is_published=True)
            .select_related("agent")
            .prefetch_related("images")
            .order_by("-created_at")
        )


class MapPinsView(generics.GenericAPIView):
    """
    GET /api/v1/properties/map-pins/
    Returns only the fields needed to render map dots — no images, no amenities.
    Uses .values() to skip serializer overhead entirely.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        qs = (
            Property.objects
            .filter(is_published=True)
            .exclude(latitude=None)
            .exclude(longitude=None)
            .values(
                "slug", "price", "price_label", "latitude", "longitude",
                "bedrooms", "bathrooms", "city", "state", "listing_type",
            )
        )
        return Response(list(qs))


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def property_sitemap(request):
    """
    GET /api/v1/properties/sitemap/
    Returns slug + updated_at for active properties only — no pagination.
    Excludes sold/rented/off-market to avoid wasting Google's crawl budget on dead pages.
    Used exclusively by the Next.js sitemap generator.
    """
    qs = (
        Property.objects
        .filter(is_published=True, status__in=["available", "under-contract"])
        .values("slug", "updated_at")
        .order_by("slug")
    )
    return Response(list(qs))


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def property_inquiry(request, slug):
    """POST /api/v1/properties/{slug}/inquiries/ — creates a Lead from property detail page."""
    try:
        prop = Property.objects.get(slug=slug, is_published=True)
    except Property.DoesNotExist:
        return Response({"detail": "Property not found."}, status=status.HTTP_404_NOT_FOUND)

    from apps.crm.serializers import LeadCreateSerializer
    data = request.data.copy()
    data["source"] = "PROPERTY_INQUIRY"
    data["property_interest"] = prop.id
    data["interest_type"] = "BUY" if prop.listing_type == "for-sale" else "RENT"

    serializer = LeadCreateSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    lead = serializer.save()

    # Async: notify the listing agent
    from apps.notifications.tasks import send_lead_notification
    send_lead_notification(lead.id)

    return Response({"message": "Inquiry received. An advisor will contact you within 24 hours."}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def agent_inquiry(request, agent_id):
    """POST /api/v1/agents/{agent_id}/inquiries/ — contact a specific agent."""
    from apps.accounts.models import CustomUser, Role
    try:
        agent = CustomUser.objects.get(id=agent_id, role=Role.AGENT, is_active=True)
    except CustomUser.DoesNotExist:
        return Response({"detail": "Agent not found."}, status=status.HTTP_404_NOT_FOUND)

    from apps.crm.serializers import LeadCreateSerializer
    data = request.data.copy()
    data["source"] = "AGENT_INQUIRY"
    data["agent_interest"] = agent.id
    data["interest_type"] = data.get("interest_type", "BUY")

    serializer = LeadCreateSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    lead = serializer.save()

    from apps.notifications.tasks import send_lead_notification
    send_lead_notification(lead.id)

    return Response({"message": "Message sent. The advisor will be in touch shortly."}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def city_stats(request):
    """
    GET /api/v1/properties/cities/
    Returns distinct cities that have at least one published rental listing.
    Used by the Next.js front-end for programmatic SEO page generation.
    """
    qs = (
        Property.objects
        .filter(is_published=True, listing_type__in=["for-rent", "for-lease"])
        .values("city", "state")
        .annotate(
            count=Count("id"),
            avg_price=Avg("price"),
            min_price=Min("price"),
            max_price=Max("price"),
        )
        .order_by("-count")
    )

    lt_map: dict = defaultdict(set)
    for row in (
        Property.objects
        .filter(is_published=True, listing_type__in=["for-rent", "for-lease"])
        .values("city", "state", "listing_type")
        .distinct()
    ):
        lt_map[(row["city"], row["state"])].add(row["listing_type"])

    return Response([
        {
            "city": r["city"],
            "state": r["state"].upper() if r["state"] else "",
            "slug": slugify(f"{r['city']}-{r['state']}"),
            "count": r["count"],
            "avg_price": float(r["avg_price"]) if r["avg_price"] else None,
            "min_price": float(r["min_price"]) if r["min_price"] else None,
            "max_price": float(r["max_price"]) if r["max_price"] else None,
            "listing_types": sorted(lt_map.get((r["city"], r["state"]), [])),
        }
        for r in qs
    ])
