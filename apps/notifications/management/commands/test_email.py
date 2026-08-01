"""
Management command: test_email

Diagnoses outgoing mail end to end, in the order things actually break.

    python manage.py test_email                        # report config + test SMTP login
    python manage.py test_email --to you@example.com   # ...and send a real message
    python manage.py test_email --use-settings         # ignore the DB row, test settings only

WHAT IT CHECKS, IN ORDER
------------------------
  1. Which backend is active — local.py forces the console backend, so mail
     "sends" successfully and silently goes nowhere.
  2. Whether an active EmailConfiguration row exists. Credentials live in the
     DATABASE (singleton model), not just in settings. A database restore that
     didn't include that table leaves the app falling back to settings without
     any error — mail simply stops.
  3. Whether the resolved credentials actually authenticate, by opening a real
     SMTP connection. This is where a rotated or revoked Gmail App Password shows
     up, and it fails the same way whether the source was the DB or settings.
  4. Optionally, a real send.

Nothing is sent unless --to is given.
"""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.management.base import BaseCommand, CommandError


def mask(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


class Command(BaseCommand):
    help = "Diagnose and optionally test outgoing email."

    def add_arguments(self, parser):
        parser.add_argument("--to", help="Send a real test message to this address.")
        parser.add_argument(
            "--use-settings", action="store_true",
            help="Ignore the EmailConfiguration row and test settings.py credentials only.",
        )

    def handle(self, *args, **opts):
        ok = self.style.SUCCESS
        bad = self.style.ERROR
        warn = self.style.WARNING

        # ── 1. Backend ───────────────────────────────────────────────────────
        backend = getattr(settings, "EMAIL_BACKEND", "(unset)")
        self.stdout.write(f"\n1. Backend\n   {backend}")
        if "console" in backend:
            self.stdout.write(warn(
                "   Console backend: mail is PRINTED, never delivered.\n"
                "   That is config.settings.local. Run with\n"
                "     DJANGO_SETTINGS_MODULE=config.settings.production manage.py test_email"
            ))
        elif "locmem" in backend or "dummy" in backend:
            self.stdout.write(bad("   Mail is discarded by this backend."))

        # ── 2. Credential source ─────────────────────────────────────────────
        self.stdout.write("\n2. Credential source")
        config = None
        if not opts["use_settings"]:
            try:
                from apps.notifications.models import EmailConfiguration
                config = EmailConfiguration.get_active()
            except Exception as exc:
                self.stdout.write(bad(f"   Could not read EmailConfiguration: {exc}"))

        if config:
            host, port = config.smtp_host, config.smtp_port
            user, password = config.email_host_user, config.email_host_password
            use_tls, use_ssl = config.use_tls, config.use_ssl
            from_header = config.get_from_header()
            self.stdout.write(ok("   Database EmailConfiguration (active row)"))
        else:
            host = getattr(settings, "EMAIL_HOST", "")
            port = getattr(settings, "EMAIL_PORT", None)
            user = getattr(settings, "EMAIL_HOST_USER", "")
            password = getattr(settings, "EMAIL_HOST_PASSWORD", "")
            use_tls = getattr(settings, "EMAIL_USE_TLS", False)
            use_ssl = getattr(settings, "EMAIL_USE_SSL", False)
            from_header = getattr(settings, "DEFAULT_FROM_EMAIL", "")
            if opts["use_settings"]:
                self.stdout.write("   settings.py (forced with --use-settings)")
            else:
                self.stdout.write(warn(
                    "   NO active EmailConfiguration row — falling back to settings.\n"
                    "   Credentials live in the database, so a restore that skipped that\n"
                    "   table silently disables mail. Recreate it in Django admin under\n"
                    "   Notifications > Email Configuration."
                ))

        self.stdout.write(
            f"\n3. Resolved settings\n"
            f"   host      : {host or '(empty)'}\n"
            f"   port      : {port}\n"
            f"   tls / ssl : {use_tls} / {use_ssl}\n"
            f"   username  : {user or '(empty)'}\n"
            f"   password  : {mask(password)}  (len={len(password or '')})\n"
            f"   from      : {from_header or '(empty)'}"
        )

        if use_tls and use_ssl:
            self.stdout.write(bad("   TLS and SSL are BOTH on — pick one (587=TLS, 465=SSL)."))
        if not user or not password:
            self.stdout.write(bad("   Missing username or password — authentication cannot succeed."))
            return
        # Gmail App Passwords are 16 chars; the regular account password will be rejected.
        if "gmail" in (host or "") and len(password.replace(" ", "")) != 16:
            self.stdout.write(warn(
                f"   Gmail expects a 16-character App Password; this one is "
                f"{len(password.replace(' ', ''))}. A normal account password is rejected."
            ))

        # ── 4. Real SMTP login ───────────────────────────────────────────────
        self.stdout.write("\n4. SMTP connection")
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=host, port=port, username=user, password=password,
            use_tls=use_tls, use_ssl=use_ssl, fail_silently=False, timeout=20,
        )
        try:
            connection.open()
            self.stdout.write(ok(f"   Connected and authenticated to {host}:{port}"))
        except Exception as exc:
            self.stdout.write(bad(f"   FAILED — {type(exc).__name__}: {exc}"))
            self.stdout.write(
                "\n   Common causes:\n"
                "     535 auth failed  -> App Password revoked/rotated, or 2FA changed\n"
                "     timeout          -> host firewall blocks outbound 587/465\n"
                "     ssl wrong version-> port/TLS mismatch (587=TLS, 465=SSL)"
            )
            return

        # ── 5. Optional send ─────────────────────────────────────────────────
        if not opts["to"]:
            connection.close()
            self.stdout.write(ok("\nConfiguration is valid. Re-run with --to <address> to send a real message."))
            return

        try:
            msg = EmailMultiAlternatives(
                subject="PrimeFamilyHousing — test email",
                body=(
                    "This is a test message from `manage.py test_email`.\n\n"
                    f"Sent via {host}:{port} as {user}.\n"
                    "If you are reading this, outgoing mail is working."
                ),
                from_email=from_header,
                to=[opts["to"]],
                connection=connection,
            )
            sent = msg.send()
            if sent:
                self.stdout.write(ok(f"\nSent 1 message to {opts['to']}. Check inbox and spam."))
            else:
                self.stdout.write(bad("\nsend() reported 0 messages sent."))
        except Exception as exc:
            self.stdout.write(bad(f"\nSend FAILED — {type(exc).__name__}: {exc}"))
        finally:
            connection.close()
