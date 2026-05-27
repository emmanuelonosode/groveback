import django as _django
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# ── Apps ──────────────────────────────────────────────────────────────────────
DJANGO_APPS = [
    "unfold",                          # must be before django.contrib.admin
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "cloudinary",
    "cloudinary_storage",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.properties",
    "apps.crm",
    "apps.transactions",
    "apps.scheduler",
    "apps.documents",
    "apps.notifications",
    "apps.analytics",
    "apps.blog",
    "apps.maintenance",
    "apps.careers",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ── Middleware ─────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.accounts.middleware.DisableCSRFForAPI",   # must be before CsrfViewMiddleware
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ── Templates ─────────────────────────────────────────────────────────────────
_DJANGO_FORMS_TEMPLATES = Path(_django.__file__).parent / "forms" / "templates"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates", _DJANGO_FORMS_TEMPLATES],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ── Database ───────────────────────────────────────────────────────────────────
DATABASE_URL = config("DATABASE_URL", default=f"sqlite:///{BASE_DIR}/db.sqlite3")

if DATABASE_URL.startswith("sqlite"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    import dj_database_url
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL)}
    if DATABASE_URL.startswith("mysql"):
        DATABASES["default"].setdefault("OPTIONS", {}).update({
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        })

# ── Auth ───────────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = "accounts.CustomUser"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Internationalisation ───────────────────────────────────────────────────────
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles"
USE_I18N = True
USE_TZ = True

# ── Static & Media ─────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Use the project's TEMPLATES settings (including custom DIRS) for form widget rendering.
# Required so unfold/widgets/*.html templates in the project templates dir are found.
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# ── Cloudinary ─────────────────────────────────────────────────────────────────
CLOUDINARY_CLOUD_NAME = config("CLOUDINARY_CLOUD_NAME", default="")
CLOUDINARY_API_KEY    = config("CLOUDINARY_API_KEY", default="")
CLOUDINARY_API_SECRET = config("CLOUDINARY_API_SECRET", default="")

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": CLOUDINARY_CLOUD_NAME,
    "API_KEY":    CLOUDINARY_API_KEY,
    "API_SECRET": CLOUDINARY_API_SECRET,
    "SECURE":     True,               # always return https:// URLs
}
DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"

# Initialise the Cloudinary SDK immediately so cloudinary.uploader works in
# Celery tasks and management commands (before Django's app-registry ready()).
import cloudinary
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True,
)

# ── DRF ────────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 12,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# ── JWT ────────────────────────────────────────────────────────────────────────
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=4),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ── CORS ───────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3003,http://localhost:3000",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

# ── Celery ─────────────────────────────────────────────────────────────────────
CELERY_BROKER_URL = config("REDIS_URL", default="redis://:qwjiBno7nAJiJdJW4ec@127.0.0.1:35717/0")
CELERY_RESULT_BACKEND = config("REDIS_URL", default="redis://:qwjiBno7nAJiJdJW4ec@127.0.0.1:35717/0")
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    # Every 6 hours — nudge applicants who left their form unfinished for 48h+
    "recover-abandoned-applications": {
        "task": "apps.notifications.tasks.recover_abandoned_applications",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    # Every Monday 8 AM — follow up with leads that haven't responded in 7 days
    "weekly-lead-followup": {
        "task": "apps.notifications.tasks.weekly_lead_followup",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),
    },
    # Every hour — send 24h reminders for upcoming property viewings
    "schedule-viewing-reminders": {
        "task": "apps.notifications.tasks.schedule_viewing_reminders",
        "schedule": crontab(minute=0),
    },
}

# ── Email ──────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="info@haskerrealtygroup.com")


# ── Frontend ───────────────────────────────────────────────────────────────────
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3003")

# ── Hasker Mailer Integration ──────────────────────────────────────────────────
# Shared secret key for the /api/v1/mailer/* sync endpoints
MAILER_SYNC_KEY = config("MAILER_SYNC_KEY", default="")
# Base URL of the deployed Hasker Mailer application
MAILER_APP_URL = config("MAILER_APP_URL", default="http://localhost:3001")


# ── Django Unfold Admin ────────────────────────────────────────────────────────
UNFOLD = {
    "SITE_TITLE": "Hasker & Co. Realty Group",
    "SITE_HEADER": "Hasker & Co. Realty Group",
    "SITE_SUBHEADER": "CRM & Operations Dashboard",
    "SITE_URL": FRONTEND_URL,
    "SITE_ICON": None,
    "SCRIPTS": ["/static/js/fix_icons.js"],
    "COLORS": {
        "primary": {
            "50": "239 246 255",
            "100": "219 234 254",
            "200": "191 219 254",
            "300": "147 197 253",
            "400": "96 165 250",
            "500": "59 130 246",
            "600": "37 99 235",
            "700": "29 78 216",
            "800": "30 64 175",
            "900": "30 58 138",
            "950": "23 37 84",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Operations",
                "items": [
                    {"title": "Dashboard",           "icon": "home",           "link": "/admin/"},
                    {"title": "Leads",               "icon": "group",          "link": "/admin/crm/lead/"},
                    {"title": "Clients",             "icon": "how_to_reg",     "link": "/admin/crm/client/"},
                    {"title": "Viewings",            "icon": "calendar_month", "link": "/admin/scheduler/viewing/"},
                    {"title": "Rental Applications", "icon": "assignment",     "link": "/admin/crm/rentalapplication/"},
                ],
            },
            {
                "title": "Listings",
                "items": [
                    {"title": "Properties", "icon": "apartment", "link": "/admin/properties/property/"},
                ],
            },
            {
                "title": "Finance",
                "items": [
                    {"title": "Transactions", "icon": "payments", "link": "/admin/transactions/transaction/"},
                    {"title": "Payments", "icon": "credit_card", "link": "/admin/transactions/payment/"},
                    {"title": "Invoices", "icon": "receipt_long", "link": "/admin/transactions/invoice/"},
                ],
            },
            {
                "title": "Team",
                "items": [
                    {"title": "Staff Users", "icon": "admin_panel_settings", "link": "/admin/accounts/customuser/"},
                    {"title": "Agent Profiles", "icon": "badge", "link": "/admin/accounts/agentprofile/"},
                ],
            },
            {
                "title": "Documents",
                "items": [
                    {"title": "Client Docs", "icon": "folder_open", "link": "/admin/documents/clientdocument/"},
                ],
            },
            {
                "title": "Content",
                "items": [
                    {"title": "Blog Posts", "icon": "article", "link": "/admin/blog/post/"},
                ],
            },
        ],
    },
}
