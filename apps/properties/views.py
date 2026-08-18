from collections import defaultdict

from django.db.models import Avg, Count, Max, Min, OuterRef, Q, Subquery
from django.utils.text import slugify
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Property, PropertyImage, FavoriteProperty
from .serializers import PropertyListSerializer, PropertyDetailSerializer, FavoritePropertySerializer, _resolve_image_url
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
    # Only DjangoFilterBackend — PropertyFilter owns search (q) AND sort. The global
    # OrderingFilter must NOT run here: it would override our sort with -created_at.
    filter_backends = [DjangoFilterBackend]
    filterset_class = PropertyFilter
    pagination_class = FlexiblePageSize

    def get_serializer_class(self):
        return PropertyDetailSerializer if self.request.method == "POST" else PropertyListSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.AllowAny()]
        return [IsAgentOrAbove()]

    def get_queryset(self):
        qs = super().get_queryset()
        # Public users only see published, active listings. Rented/sold rows stay
        # published for a 60-day grace period (SEO: detail pages keep serving a
        # "no longer available" banner) but must never appear in lists/search.
        if (
            not self.request.user
            or not self.request.user.is_authenticated
            or self.request.user.role == "CLIENT"
        ):
            return qs.filter(is_published=True, status__in=["available", "under-contract"])
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

    def get_queryset(self):
        qs = super().get_queryset()
        # Anonymous/client users must never see unpublished drafts. Rented/sold
        # listings stay visible while published (60-day grace period) — the
        # frontend shows the "no longer available" banner for them.
        user = self.request.user
        if not user or not user.is_authenticated or getattr(user, "role", "CLIENT") == "CLIENT":
            return qs.filter(is_published=True)
        return qs


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


class MapPinsView(generics.ListAPIView):
    """
    GET /api/v1/properties/map-pins/
    Returns lightweight map pin data, including primary image URL.
    """
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_class = PropertyFilter
    pagination_class = None

    def get_queryset(self):
        return (
            Property.objects
            .filter(is_published=True)
            .exclude(latitude=None)
            .exclude(longitude=None)
            .prefetch_related("images")
        )

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        out = []
        for p in qs:
            images = p.images.all()
            img = next((i for i in images if i.is_primary), None) or next(iter(images), None)
            img_url = _resolve_image_url(img.image) if img and img.image else None
            out.append({
                "slug": p.slug,
                "price": p.price,
                "price_label": p.price_label,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "bedrooms": p.bedrooms,
                "bathrooms": p.bathrooms,
                "city": p.city,
                "state": p.state,
                "listing_type": p.listing_type,
                "image_url": img_url,
            })
        return Response(out)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def property_sitemap(request):
    """
    GET /api/v1/properties/sitemap/
    Returns slug + updated_at for active properties only — no pagination.
    Excludes sold/rented/off-market to avoid wasting Google's crawl budget on dead pages.
    Used exclusively by the Next.js sitemap generator.
    """
    # Primary image per property (one query via subquery) so the sitemap can
    # emit <image:image> entries — this is what gets listing photos into Google
    # Images and as result thumbnails.
    primary_image = (
        PropertyImage.objects
        .filter(property=OuterRef("pk"))
        .order_by("-is_primary", "order", "id")
        .values("image")[:1]
    )
    rows = (
        Property.objects
        .filter(is_published=True, status__in=["available", "under-contract"])
        .annotate(_primary_image=Subquery(primary_image))
        .values("slug", "updated_at", "_primary_image", "title", "city", "state")
        .order_by("slug")
    )
    out = [
        {
            "slug": r["slug"],
            "updated_at": r["updated_at"],
            "image": _resolve_image_url(r["_primary_image"]) or "",
            "title": r["title"],
            "city": r["city"],
            "state": r["state"],
        }
        for r in rows
    ]
    return Response(out)


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
    # Count only active inventory — rented/sold rows stay published during their
    # 60-day SEO grace period but must not inflate city counts (city pages and
    # the sitemap key off these numbers).
    _active = dict(is_published=True, listing_type__in=["for-rent", "for-lease"],
                   status__in=["available", "under-contract"])
    active = Property.objects.filter(**_active)
    qs = (
        active
        .values("city", "state")
        .annotate(
            count=Count("id"),
            avg_price=Avg("price"),
            min_price=Min("price"),
            max_price=Max("price"),
            # sqft=0 means "unknown", not a 0 sq ft home — filtered aggregates
            # compile to CASE WHEN, portable across MySQL and SQLite.
            min_sqft=Min("sqft", filter=Q(sqft__gt=0)),
            max_sqft=Max("sqft", filter=Q(sqft__gt=0)),
            avg_sqft=Avg("sqft", filter=Q(sqft__gt=0)),
            newest_listed=Max("created_at"),
            last_updated=Max("updated_at"),
        )
        .order_by("-count")
    )

    lt_map: dict = defaultdict(set)
    for row in active.values("city", "state", "listing_type").distinct():
        lt_map[(row["city"], row["state"])].add(row["listing_type"])

    # Per-city facts for unique landing-page content. Grouped in Python rather
    # than GROUP_CONCAT/ArrayAgg so the same code runs on MySQL and SQLite.
    bed_map: dict = defaultdict(dict)
    for row in active.values("city", "state", "bedrooms").annotate(n=Count("id")):
        if row["bedrooms"]:
            bed_map[(row["city"], row["state"])][str(row["bedrooms"])] = row["n"]

    type_map: dict = defaultdict(dict)
    for row in active.values("city", "state", "type").annotate(n=Count("id")):
        if row["type"]:
            type_map[(row["city"], row["state"])][row["type"]] = row["n"]

    zip_map: dict = defaultdict(list)
    for row in (
        active.exclude(zip_code="")
        .values("city", "state", "zip_code")
        .annotate(n=Count("id"))
        .order_by("-n", "zip_code")
    ):
        zip_map[(row["city"], row["state"])].append(row["zip_code"])

    hood_map: dict = defaultdict(list)
    for row in (
        active.exclude(neighborhood="")
        .values("city", "state", "neighborhood")
        .annotate(n=Count("id"))
        .order_by("-n", "neighborhood")
    ):
        hood_map[(row["city"], row["state"])].append(row["neighborhood"])

    # One representative photo per city (newest listing's primary image) so
    # generic city pages stop sharing a single stock hero.
    primary_image = (
        PropertyImage.objects
        .filter(property=OuterRef("pk"))
        .order_by("-is_primary", "order", "id")
        .values("image")[:1]
    )
    img_map: dict = {}
    for row in (
        active
        .annotate(_img=Subquery(primary_image))
        .exclude(_img=None)
        .values("city", "state", "_img", "created_at")
        .order_by("city", "state", "-created_at")
    ):
        img_map.setdefault((row["city"], row["state"]), row["_img"])

    def _sqft(r):
        if not r["min_sqft"]:
            return None
        return {"min": r["min_sqft"], "max": r["max_sqft"],
                "avg": int(round(float(r["avg_sqft"])))}

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
            "bedrooms": bed_map.get((r["city"], r["state"]), {}),
            "types": type_map.get((r["city"], r["state"]), {}),
            "sqft": _sqft(r),
            "zips": zip_map.get((r["city"], r["state"]), [])[:6],
            "neighborhoods": hood_map.get((r["city"], r["state"]), [])[:5],
            "newest_listed": r["newest_listed"],
            "last_updated": r["last_updated"],
            "image": _resolve_image_url(img_map.get((r["city"], r["state"]))) or "",
        }
        for r in qs
    ])


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def parse_query(request):
    """
    POST /api/v1/properties/parse-query/   body: {"q": "..."}
    Parses a natural-language search into structured filters via Claude Haiku.
    Returns {"ok": true, "filters": {...}} or {"ok": false} so the frontend
    falls back to sending the raw `q` to the regex parser.
    """
    from django.core.cache import cache
    from .ai_search import parse_query as ai_parse

    q = (request.data.get("q") or "").strip()
    if not q:
        return Response({"ok": False})

    # Lightweight per-IP rate limit: 30 AI parses / minute.
    ip = (
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR", "")
        or "anon"
    )
    rl_key = f"ai_search_rl:{ip}"
    count = cache.get(rl_key, 0)
    if count >= 30:
        return Response({"ok": False})
    cache.set(rl_key, count + 1, 60)

    filters = ai_parse(q)
    if not filters:
        return Response({"ok": False})
    return Response({"ok": True, "filters": filters})


import os
import urllib.request
from django.http import HttpResponse, Http404
from django.conf import settings
from django.views.decorators.cache import cache_control

@cache_control(public=True, max_age=31536000, immutable=True)
def proxy_property_image(request, slug, filename):
    """
    Branded Image Proxy for Prime Family Housing.
    Serves images under https://primefamilyhousing.com/media/properties/{slug}/{filename}
    without exposing third-party CDN domains to Google crawlers or visitors.
    """
    local_dir = os.path.join(settings.MEDIA_ROOT, "properties", slug)
    local_path = os.path.join(local_dir, filename)
    if os.path.exists(local_path):
        with open(local_path, "rb") as f:
            content = f.read()
        content_type = "image/jpeg"
        if filename.lower().endswith(".png"):
            content_type = "image/png"
        elif filename.lower().endswith(".webp"):
            content_type = "image/webp"
        resp = HttpResponse(content, content_type=content_type)
        resp["Cache-Control"] = "public, max-age=31536000, immutable"
        resp["X-Robots-Tag"] = "index, follow, max-image-preview:large"
        return resp

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }

    candidates = [
        f"https://images.invitationhomes.com/web/w_1500,h_1000,c_limit,q_auto/{slug}/{filename}",
        f"https://images.invitationhomes.com/web/w_1500,h_1000,c_limit,q_auto/{filename}",
        f"https://images.invitationhomes.com/{slug}/{filename}",
    ]

    for candidate_url in candidates:
        try:
            req = urllib.request.Request(candidate_url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    data = resp.read()
                    try:
                        os.makedirs(local_dir, exist_ok=True)
                        with open(local_path, "wb") as f:
                            f.write(data)
                    except Exception:
                        pass
                    content_type = resp.headers.get("Content-Type") or "image/jpeg"
                    http_resp = HttpResponse(data, content_type=content_type)
                    http_resp["Cache-Control"] = "public, max-age=31536000, immutable"
                    http_resp["X-Robots-Tag"] = "index, follow, max-image-preview:large"
                    return http_resp
        except Exception:
            continue

    return HttpResponse("Image not found", status=404)