from .base import *  # noqa
from decouple import config, Csv


DEBUG = True

# Hardcoded production domains to prevent DisallowedHost errors
ALLOWED_HOSTS = [
    "admin.haskerrealtygroup.com",
    "www.haskerrealtygroup.com",
    "haskerrealtygroup.com",
    "api.haskerrealtygroup.com",
    "localhost",
    "127.0.0.1",
]

# Supplement with any additional hosts from environment variables
_extra_hosts = config("ALLOWED_HOSTS", default="", cast=Csv())
for host in _extra_hosts:
    if host and host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
] + MIDDLEWARE[1:]  # noqa — replace SecurityMiddleware with whitenoise version

STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# SSL & Security
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Required for admin login & forms in production SSL
CSRF_TRUSTED_ORIGINS = [
    "https://admin.haskerrealtygroup.com",
    "https://www.haskerrealtygroup.com",
    "https://haskerrealtygroup.com",
]

# CORS fallbacks for production
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="https://www.haskerrealtygroup.com,https://haskerrealtygroup.com",
    cast=Csv()
)

# SMTP Email Configuration
_EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_PORT = _EMAIL_PORT

# Intelligent defaults based on port
if _EMAIL_PORT == 465:
    EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=True, cast=bool)
    EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=False, cast=bool)
else:
    EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)
    EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)

EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="Hasker & Co. <info@haskerrealtygroup.com>")

SENTRY_DSN = config("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.2)
