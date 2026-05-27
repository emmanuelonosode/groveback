from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # JWT auth
    path("api/v1/auth/token/", TokenObtainPairView.as_view(), name="token_obtain"),
    path("api/v1/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/auth/", include("apps.accounts.urls")),

    # App APIs — public
    path("api/v1/properties/", include("apps.properties.urls")),
    path("api/v1/agents/", include("apps.accounts.agent_urls")),
    # Agent listings & contact (mounted under agents/)
    path("api/v1/agents/", include("apps.properties.agent_urls")),

    # App APIs — staff
    path("api/v1/leads/", include("apps.crm.urls")),
    path("api/v1/clients/", include("apps.crm.client_urls")),
    path("api/v1/transactions/", include("apps.transactions.urls")),
    path("api/v1/viewings/", include("apps.scheduler.urls")),
    path("api/v1/analytics/", include("apps.analytics.urls")),

    # Blog (public)
    path("api/v1/blog/", include("apps.blog.urls")),

    # Careers — job applications (public submit, staff read)
    path("api/v1/careers/", include("apps.careers.urls")),

    # Tenant-facing
    path("api/v1/documents/", include("apps.documents.urls")),
    path("api/v1/maintenance/", include("apps.maintenance.urls")),

    # ── Hasker Mailer Integration ───────────────────────────────────────────
    # Secure sync API — protected by X-Mailer-Key header
    path("api/v1/mailer/", include("apps.crm.mailer_urls")),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    try:
        import debug_toolbar
        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass
