import os
from django.core.asgi import get_asgi_application

# Same rationale as wsgi.py: ASGI is a production entrypoint, so default to
# production settings rather than base. An explicit env var still wins.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
application = get_asgi_application()
