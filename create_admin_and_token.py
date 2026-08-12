import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from apps.accounts.models import CustomUser, Role
from rest_framework_simplejwt.tokens import RefreshToken

# Create user
user, created = CustomUser.objects.get_or_create(email="admin_test@prime.com")
if created:
    user.set_password("admin123")
    user.is_superuser = True
    user.is_staff = True
    user.role = Role.ADMIN
    user.save()

# Generate token
refresh = RefreshToken.for_user(user)
print("TOKEN:", str(refresh.access_token))
