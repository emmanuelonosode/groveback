
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from .models import CustomUser, AgentProfile, Role


class AgentProfileInline(TabularInline):
    model = AgentProfile
    extra = 0
    fields = ["avatar", "bio", "license_number", "specialties", "languages", "commission_rate", "total_sales", "years_experience"]


@admin.register(CustomUser)
class CustomUserAdmin(ModelAdmin, UserAdmin):
    """
    Admin for our email-based CustomUser.
    Inherits from UserAdmin to get password management (create with password1/password2,
    change-password view). We override every fieldset so `username` never appears in forms.
    The `username` property on CustomUser satisfies any remaining template lookups.
    """
    list_display = ["email", "full_name_display", "role_badge", "is_active", "is_staff", "date_joined"]
    list_filter = ["role", "is_active", "is_staff", "date_joined"]
    search_fields = ["email", "first_name", "last_name", "phone"]
    ordering = ["-date_joined"]
    inlines = [AgentProfileInline]

    # Override UserAdmin fieldsets — remove `username`, add `email` and `role`
    fieldsets = (
        (None, {
            "fields": ("email", "password"),
        }),
        ("Personal Info", {
            "fields": ("first_name", "last_name", "phone", "avatar"),
        }),
        ("Role & Permissions", {
            "fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
        }),
        ("Dates", {
            "fields": ("date_joined", "last_login"),
        }),
    )

    # Override UserAdmin add_fieldsets — no `username`, uses email + role
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "role", "password1", "password2"),
        }),
    )

    readonly_fields = ["date_joined", "last_login"]

    def get_inlines(self, request, obj=None):
        if obj and obj.role == Role.AGENT:
            return [AgentProfileInline]
        return []

    def full_name_display(self, obj):
        return obj.full_name
    full_name_display.short_description = "Name"

    def role_badge(self, obj):
        colors = {
            Role.ADMIN: "#dc2626",
            Role.MANAGER: "#7c3aed",
            Role.AGENT: "#2563eb",
            Role.ACCOUNTANT: "#0891b2",
            Role.CLIENT: "#16a34a",
        }
        color = colors.get(obj.role, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:9999px;font-size:11px">{}</span>',
            color, obj.get_role_display()
        )
    role_badge.short_description = "Role"


@admin.register(AgentProfile)
class AgentProfileAdmin(ModelAdmin):
    list_display = ["user", "license_number", "years_experience", "total_sales_display"]
    search_fields = ["user__email", "user__first_name", "user__last_name", "license_number"]
    readonly_fields = ["total_sales"]

    fieldsets = (
        ("Agent", {
            "fields": ("user", "license_number", "years_experience", "commission_rate"),
        }),
        ("Profile", {
            "fields": ("avatar", "bio"),
        }),
        ("Performance", {
            "fields": ("total_sales",),
        }),
        ("Attributes", {
            "fields": ("specialties", "languages", "social_links"),
            "classes": ("collapse",),
        }),
    )

    def total_sales_display(self, obj):
        return f"${obj.total_sales:,.0f}"
    total_sales_display.short_description = "Total Sales"
