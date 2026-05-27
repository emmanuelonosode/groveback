from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from .models import Post, PostCategory


@admin.register(Post)
class PostAdmin(ModelAdmin):
    list_display        = ["title", "category_badge", "author", "is_featured", "published_badge", "published_at"]
    list_filter         = ["is_published", "is_featured", "category", "author"]
    search_fields       = ["title", "excerpt", "content"]
    ordering            = ["-created_at"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields     = ["created_at", "updated_at", "published_at"]
    actions             = ["publish_posts", "unpublish_posts", "mark_featured", "unmark_featured"]

    fieldsets = (
        ("Content", {
            "fields": ("title", "slug", "excerpt", "content"),
        }),
        ("Media & Meta", {
            "fields": ("featured_image", "category", "author", "tags", "read_time_minutes"),
        }),
        ("Publishing", {
            "fields": ("is_published", "is_featured", "published_at"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def category_badge(self, obj):
        colors = {
            PostCategory.MARKET_ANALYSIS: "#0891b2",
            PostCategory.BUYERS_GUIDE:    "#16a34a",
            PostCategory.SELLERS_GUIDE:   "#7c3aed",
            PostCategory.INVESTMENT:      "#d97706",
            PostCategory.MARKET_UPDATE:   "#2563eb",
        }
        color = colors.get(obj.category, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:9999px;font-size:11px">{}</span>',
            color, obj.get_category_display(),
        )
    category_badge.short_description = "Category"

    def published_badge(self, obj):
        if obj.is_published:
            return format_html(
                '<span style="background:#dcfce7;color:#166534;padding:2px 8px;'
                'border-radius:9999px;font-size:11px">Published</span>'
            )
        return format_html(
            '<span style="background:#f3f4f6;color:#374151;padding:2px 8px;'
            'border-radius:9999px;font-size:11px">Draft</span>'
        )
    published_badge.short_description = "Status"

    @admin.action(description="Publish selected posts")
    def publish_posts(self, request, queryset):
        now = timezone.now()
        updated = 0
        for post in queryset.filter(is_published=False):
            post.is_published = True
            if not post.published_at:
                post.published_at = now
            post.save(update_fields=["is_published", "published_at"])
            updated += 1
        self.message_user(request, f"{updated} post(s) published.")

    @admin.action(description="Move selected posts to draft")
    def unpublish_posts(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"{updated} post(s) moved to draft.")

    @admin.action(description="Mark as Featured")
    def mark_featured(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f"{updated} post(s) marked as featured.")

    @admin.action(description="Remove from Featured")
    def unmark_featured(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(request, f"{updated} post(s) removed from featured.")
