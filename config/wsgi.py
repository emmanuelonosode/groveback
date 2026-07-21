import os
from django.core.wsgi import get_wsgi_application

# WSGI is only used by the production server (gunicorn); `manage.py` sets its
# own default for local dev. Defaulting to production settings here means a
# deploy can never accidentally boot with DEBUG on, no HSTS/secure cookies and
# no whitenoise. `setdefault` still lets an explicit env var override it.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
application = get_wsgi_application()
