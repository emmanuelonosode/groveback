from .base import *  # noqa

DEBUG = True

try:
    import debug_toolbar  # noqa
    INSTALLED_APPS += ["debug_toolbar"]  # noqa
    MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE  # noqa
    INTERNAL_IPS = ["127.0.0.1", "localhost"]
except ImportError:
    pass

# Use console email backend in local dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Relax password validation locally
AUTH_PASSWORD_VALIDATORS = []

ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True

# SQLite fallback if no DATABASE_URL is set
# (base.py already handles this via DATABASE_URL detection)
