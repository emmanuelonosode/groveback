from django.urls import path
from . import mailer_views

urlpatterns = [
    path("contacts/", mailer_views.mailer_contacts, name="mailer-contacts"),
    path("webhook/", mailer_views.mailer_webhook, name="mailer-webhook"),
    path("optout/", mailer_views.mailer_optout_sync, name="mailer-optout"),
]
