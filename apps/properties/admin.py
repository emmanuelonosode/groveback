from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from .models import Property, PropertyImage, PropertyAmenity, AmenityCategory, FavoriteProperty


@admin.register(FavoriteProperty)
class FavoritePropertyAdmin(ModelAdmin):
    list_display = ["user", "property", "created_at"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "property__title"]
    list_filter = ["created_at"]

class PropertyImageInline(TabularInline):
    model = PropertyImage
    extra = 1
    fields = ["image", "caption", "is_primary", "order"]
    ordering = ["order"]


class PropertyAmenityInline(TabularInline):
    model = PropertyAmenity
    extra = 3
    fields = ["name", "category"]
    autocomplete_fields = []


@admin.register(AmenityCategory)
class AmenityCategoryAdmin(ModelAdmin):
    list_display = ["name", "icon", "order"]
    ordering = ["order"]
    search_fields = ["name"]
    fields = ["name", "icon", "order"]


@admin.register(Property)
class PropertyAdmin(ModelAdmin):
    list_display = [
        "title", "type", "listing_type", "status_badge",
        "price_display", "city", "state", "condition",
        "homepage_featured", "is_featured", "is_published", "created_at",
    ]
    list_filter = [
        "type", "listing_type", "status", "condition",
        "homepage_featured", "is_featured", "is_published", "state",
    ]
    search_fields = [
        "title", "address", "city", "neighborhood", "zip_code",
        "agent__email", "agent__first_name", "agent__last_name",
    ]
    ordering = ["-created_at"]
    readonly_fields = ["slug", "created_at", "updated_at"]
    date_hierarchy = "created_at"
    inlines = [PropertyImageInline, PropertyAmenityInline]
    actions = [
        "publish_properties", "unpublish_properties",
        "mark_featured", "unmark_featured",
        "add_to_homepage", "remove_from_homepage",
    ]

    fieldsets = (
        ("Listing Info", {
            "fields": (
                "title", "slug", "description",
                "type", "listing_type", "status", "condition",
                "agent",
            ),
        }),
        ("Pricing", {
            "fields": ("price", "price_label"),
        }),
        ("Physical Details", {
            "fields": (
                "bedrooms", "bathrooms", "sqft",
                "lot_size", "year_built", "garage", "stories",
            ),
        }),
        ("Location", {
            "fields": (
                "address", "cross_street", "city", "state",
                "zip_code", "neighborhood",
                "latitude", "longitude",
            ),
            "description": "Enter the full street address. Cross street helps buyers orient the property.",
        }),
        ("Virtual Tours & 360-degree", {
            "fields": ("virtual_tour_url", "tour_360_url"),
            "description": (
                "virtual_tour_url: paste a Matterport/Zillow embed URL for the in-page 360-degree viewer. "
                "tour_360_url: paste any external 3D tour link (opens in new tab)."
            ),
        }),
        ("Visibility", {
            "fields": ("is_published", "is_featured", "homepage_featured"),
            "description": (
                "is_published: makes the property visible on the site. "
                "is_featured: shows the 'Featured' badge on property cards. "
                "homepage_featured: shows this property in the 'Available Now' section on the homepage (max 6)."
            ),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def status_badge(self, obj):
        colors = {
            "available": "#16a34a",
            "under-contract": "#d97706",
            "sold": "#dc2626",
            "rented": "#2563eb",
            "off-market": "#6b7280",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:9999px;font-size:11px">{}</span>',
            color, obj.get_status_display(),
        )
    status_badge.short_description = "Status"

    def price_display(self, obj):
        return f"${obj.price:,.0f}{obj.price_label}"
    price_display.short_description = "Price"

    @admin.action(description="Publish selected properties")
    def publish_properties(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f"{updated} properties published.")

    @admin.action(description="Unpublish selected properties")
    def unpublish_properties(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"{updated} properties unpublished.")

    @admin.action(description="Mark as featured")
    def mark_featured(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f"{updated} properties marked as featured.")

    @admin.action(description="Remove from featured")
    def unmark_featured(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(request, f"{updated} properties removed from featured.")

    @admin.action(description="Add to homepage 'Available Now'")
    def add_to_homepage(self, request, queryset):
        updated = queryset.update(homepage_featured=True)
        self.message_user(request, f"{updated} properties added to the homepage.")

    @admin.action(description="Remove from homepage 'Available Now'")
    def remove_from_homepage(self, request, queryset):
        updated = queryset.update(homepage_featured=False)
        self.message_user(request, f"{updated} properties removed from the homepage.")
