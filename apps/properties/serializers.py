import ast
import json
from datetime import date

from rest_framework import serializers
from .models import Property, PropertyImage, PropertyAmenity, AmenityCategory
from .sanitize import sanitize_text, brand_image_url
from apps.accounts.serializers import PublicAgentSerializer


def _parse_raw_data(raw):
    """`raw_data` is double-encoded: a JSON string wrapping a Python repr.

    Stored that way by the scraper, so json.loads alone yields a string, not a
    dict. literal_eval only evaluates literals, so this is safe on feed data.
    """
    if not raw:
        return {}
    try:
        inner = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        inner = raw
    if isinstance(inner, dict):
        return inner
    if isinstance(inner, str):
        try:
            parsed = ast.literal_eval(inner)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            return {}
    return {}

def _resolve_image_url(image_field):
    if not image_field:
        return None
    val = str(image_field)
    if val.startswith("image/upload/http"):
        val = val[len("image/upload/"):]
    
    # Branded URL handling -> point to official backend media host
    if val.startswith("https://admin.primefamilyhousing.com/media/"):
        return val
    if val.startswith("https://primefamilyhousing.com/media/"):
        return "https://admin.primefamilyhousing.com" + val[len("https://primefamilyhousing.com"):]
    if val.startswith("http://primefamilyhousing.com/media/"):
        return "https://admin.primefamilyhousing.com" + val[len("http://primefamilyhousing.com"):]
    if val.startswith("/media/"):
        return "https://admin.primefamilyhousing.com" + val

    # Anything still on a third-party CDN is re-pointed at our own proxy rather
    # than handed to the browser. Rows predating the de-branding sync still hold
    # origin URLs, and serving one names the upstream operator in public HTML.
    branded = brand_image_url(val)
    if branded.startswith("/media/"):
        return "https://admin.primefamilyhousing.com" + branded

    return val


class PropertyImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = PropertyImage
        fields = ["id", "image_url", "caption", "is_primary", "order"]

    def get_image_url(self, obj):
        return _resolve_image_url(obj.image)


class PropertyAmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyAmenity
        fields = ["id", "name"]


class PropertyListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    primary_image_url = serializers.SerializerMethodField()
    image_urls = serializers.SerializerMethodField()
    agent_name = serializers.SerializerMethodField()
    # DecimalField serializes as a string by default; override so the map's
    # Number.isFinite() check receives actual JSON numbers, not "33.749000".
    latitude = serializers.FloatField(read_only=True, allow_null=True)
    longitude = serializers.FloatField(read_only=True, allow_null=True)

    class Meta:
        model = Property
        fields = [
            "id", "slug", "title", "type", "listing_type", "status",
            "price", "price_label", "bedrooms", "bathrooms", "sqft",
            "address", "city", "state", "neighborhood",
            "is_featured", "primary_image_url", "image_urls", "agent_name", "created_at",
            "latitude", "longitude",
        ]

    def get_primary_image_url(self, obj):
        # Use prefetched images to avoid N+1; find primary without extra query
        images = obj.images.all()
        img = next((i for i in images if i.is_primary), None) or next(iter(images), None)
        if not img or not img.image:
            return None
        return _resolve_image_url(img.image)

    def get_image_urls(self, obj):
        # Up to 6 image URLs for the card carousel — primary first, then by order.
        # Uses the prefetched `images` (already ordered by order, id) — no extra queries.
        images = sorted(obj.images.all(), key=lambda i: (not i.is_primary,))
        urls = []
        for img in images:
            if img.image:
                u = _resolve_image_url(img.image)
                if u:
                    urls.append(u)
            if len(urls) >= 6:
                break
        return urls

    def get_agent_name(self, obj):
        return obj.agent.full_name if obj.agent_id else ""

class FavoritePropertySerializer(serializers.ModelSerializer):
    property = PropertyListSerializer(read_only=True)
    property_id = serializers.PrimaryKeyRelatedField(
        queryset=__import__("apps.properties.models", fromlist=["Property"]).Property.objects.filter(is_published=True),
        source="property",
        write_only=True
    )

    class Meta:
        from .models import FavoriteProperty
        model = FavoriteProperty
        fields = ["id", "property", "property_id", "created_at"]
        read_only_fields = ["id", "created_at"]

class PropertyDetailSerializer(serializers.ModelSerializer):
    """Full serializer for detail views."""
    images = PropertyImageSerializer(many=True, read_only=True)
    amenities = PropertyAmenitySerializer(many=True, read_only=True)
    amenity_categories = serializers.SerializerMethodField()
    recent_view_count = serializers.SerializerMethodField()
    leasing_special = serializers.SerializerMethodField()
    agent = PublicAgentSerializer(read_only=True)
    latitude = serializers.FloatField(read_only=True, allow_null=True)
    longitude = serializers.FloatField(read_only=True, allow_null=True)
    agent_id = serializers.PrimaryKeyRelatedField(
        queryset=__import__("apps.accounts.models", fromlist=["CustomUser"]).CustomUser.objects.filter(role="AGENT"),
        source="agent",
        write_only=True,
        required=False,
    )
    # These four are verbatim feed blobs. `sync_from_supabase` scrubs them on the
    # way in, but rows imported before that still carry the upstream brand and
    # its CDN URLs — floor_plans in particular is a list of origin image links.
    # Sanitising on output too means a stale row can never leak through an
    # endpoint, whatever put it in the table.
    schools = serializers.SerializerMethodField()
    fees = serializers.SerializerMethodField()
    floor_plans = serializers.SerializerMethodField()
    office_info = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            "id", "slug", "title", "description", "type", "listing_type", "status", "condition",
            "price", "price_label",
            "bedrooms", "bathrooms", "sqft", "lot_size", "year_built", "garage", "stories",
            "address", "cross_street", "city", "state", "zip_code", "latitude", "longitude", "neighborhood",
            "virtual_tour_url", "tour_360_url", "is_featured", "is_published",
            "images", "amenities", "amenity_categories", "agent", "agent_id",
            "created_at", "updated_at", "recent_view_count",
            "is_pet_friendly", "has_pool", "allow_selfshow", "available_on",
            "schools", "fees", "floor_plans", "office_info",
            "leasing_special",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]

    def _clean_blob(self, value):
        """Scrub a feed blob and re-point any image URL inside it at our proxy."""
        cleaned = sanitize_text(value)
        if isinstance(cleaned, list):
            return [self._clean_blob(v) for v in cleaned]
        if isinstance(cleaned, dict):
            return {
                k: (_resolve_image_url(v) if isinstance(v, str) and "url" in k.lower() else self._clean_blob(v))
                for k, v in cleaned.items()
            }
        return cleaned

    def get_schools(self, obj):
        return self._clean_blob(obj.schools)

    def get_fees(self, obj):
        return self._clean_blob(obj.fees)

    def get_floor_plans(self, obj):
        return self._clean_blob(obj.floor_plans)

    def get_office_info(self, obj):
        return self._clean_blob(obj.office_info)

    def get_recent_view_count(self, obj):
        """Distinct visitor sessions that viewed this listing in the last 30 days.
        Powers the 'X people viewed this home' social proof (frontend gates by a
        minimum threshold so small numbers are never shown)."""
        from datetime import timedelta
        from django.db.models import Q
        from django.utils import timezone
        from apps.analytics.models import PageVisit

        base = f"/houses-for-rent/{obj.slug}"
        cutoff = timezone.now() - timedelta(days=30)
        try:
            return (
                PageVisit.objects
                .filter(entry_time__gte=cutoff)
                .filter(Q(path=base) | Q(path__startswith=base + "?") | Q(path__startswith=base + "#"))
                .values("session_id").distinct().count()
            )
        except Exception:
            return 0

    def get_leasing_special(self, obj):
        """The concession currently running on this home, if any.

        Lives only in `raw_data` (the scraper keeps it out of the model), so it
        is read back out here. Offers carry start/end dates and roughly 5% of
        listings have one, so an expired offer is never returned: advertising a
        concession that has lapsed is worse than showing none.
        """
        special = _parse_raw_data(obj.raw_data).get("property", {}).get("leasing_special")
        if not isinstance(special, dict):
            return None

        title = (special.get("title") or "").strip()
        if not title:
            return None

        today = date.today()
        try:
            start = date.fromisoformat(str(special["start_at"])[:10])
            end = date.fromisoformat(str(special["end_at"])[:10])
        except (KeyError, TypeError, ValueError):
            return None
        if not (start <= today <= end):
            return None

        return {
            "title": title,
            "description": (special.get("description") or special.get("message") or "").strip(),
            "ends_on": end.isoformat(),
        }

    def get_amenity_categories(self, obj):
        all_amenities = obj.amenities.select_related("category").all()
        grouped: dict = {}
        uncategorized = []
        for amenity in all_amenities:
            if amenity.category_id:
                cat = amenity.category
                if cat.id not in grouped:
                    grouped[cat.id] = {
                        "id": cat.id,
                        "name": cat.name,
                        "icon": cat.icon,
                        "order": cat.order,
                        "amenities": [],
                    }
                grouped[cat.id]["amenities"].append({"id": amenity.id, "name": amenity.name})
            else:
                uncategorized.append({"id": amenity.id, "name": amenity.name})
        result = sorted(grouped.values(), key=lambda x: x.pop("order", 0))
        if uncategorized:
            result.append({"id": None, "name": "Other Features", "icon": "", "amenities": uncategorized})
        return result
