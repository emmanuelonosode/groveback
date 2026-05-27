from django.apps import AppConfig


class CrmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.crm"

    def ready(self):
        from apps.crm.signals import connect_signals
        connect_signals()
