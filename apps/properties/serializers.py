from rest_framework import serializers
from .models import Property, PropertyImage, PropertyAmenity, AmenityCategory
from apps.accounts.serializers import PublicAgentSerializer


def _resolve_image_url(image_field):
    """
    Safely extract a full URL from a CloudinaryField value.

    CloudinaryField wraps stored strings in a CloudinaryResource object.
    In some Cloudinary SDK versions, str(resource) calls build_url() which
    reconstructs a mangled Cloudinary CDN URL from the stored string — this
    is why external CDN URLs (e.g. cloudfront.net) get truncated.

    Fix: read .public_id directly (the raw stored string), check it's a
    full URL, and only fall back to .url (Cloudinary-generated) if it isn't.
    """
    if not image_field:
        return None
    # CloudinaryResource stores the raw DB value in .public_id
    raw = getattr(image_field, "public_id", None)
    if raw and isinstance(raw, str) and raw.startswith("http"):
        return raw
    # Fallback: str() — works if SDK returns public_id from __str__
    val = str(image_field)
    if val and val.startswith("http"):
        return val
    # Last resort: Cloudinary-generated URL (only for native Cloudinary assets)
    try:
        return image_field.url
    except Exception:
        return None


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
            "is_featured", "primary_image_url", "agent_name", "created_at",
            "latitude", "longitude",
        ]

    def get_primary_image_url(self, obj):
        # Use prefetched images to avoid N+1; find primary without extra query
        images = obj.images.all()
        img = next((i for i in images if i.is_primary), None) or next(iter(images), None)
        if not img or not img.image:
            return None
        return _resolve_image_url(img.image)

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
    agent = PublicAgentSerializer(read_only=True)
    latitude = serializers.FloatField(read_only=True, allow_null=True)
    longitude = serializers.FloatField(read_only=True, allow_null=True)
    agent_id = serializers.PrimaryKeyRelatedField(
        queryset=__import__("apps.accounts.models", fromlist=["CustomUser"]).CustomUser.objects.filter(role="AGENT"),
        source="agent",
        write_only=True,
        required=False,
    )

    class Meta:
        model = Property
        fields = [
            "id", "slug", "title", "description", "type", "listing_type", "status", "condition",
            "price", "price_label",
            "bedrooms", "bathrooms", "sqft", "lot_size", "year_built", "garage", "stories",
            "address", "cross_street", "city", "state", "zip_code", "latitude", "longitude", "neighborhood",
            "virtual_tour_url", "tour_360_url", "is_featured", "is_published",
            "images", "amenities", "amenity_categories", "agent", "agent_id",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]

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
