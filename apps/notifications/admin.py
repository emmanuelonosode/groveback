from django.contrib import admin, messages
from django.core.mail import EmailMessage
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from .models import EmailConfiguration


@admin.register(EmailConfiguration)
class EmailConfigurationAdmin(ModelAdmin):
    list_display  = ["display_name", "from_email", "smtp_host", "smtp_port", "status_badge", "updated_at"]
    readonly_fields = ["updated_at", "connection_help"]
    actions       = ["send_test_email"]

    fieldsets = (
        ("Sender Identity", {
            "description": "This name and address appear in the recipient's inbox.",
            "fields": ("display_name", "from_email"),
        }),
        ("SMTP Server", {
            "description": (
                "For Gmail use smtp.gmail.com / port 587 / TLS enabled. "
                "Do not change unless you know what you are doing."
            ),
            "fields": ("smtp_host", "smtp_port", "use_tls", "use_ssl"),
        }),
        ("Login Credentials", {
            "description": (
                "Enter the Gmail address and its App Password below. "
                "Generate an App Password at: myaccount.google.com → Security → "
                "2-Step Verification → App Passwords."
            ),
            "fields": ("email_host_user", "email_host_password"),
        }),
        ("Status", {
            "fields": ("is_active", "updated_at", "connection_help"),
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Render the password field as a password input so it isn't shown in plain text
        if "email_host_password" in form.base_fields:
            from django.forms import PasswordInput
            form.base_fields["email_host_password"].widget = PasswordInput(render_value=True)
        return form

    def status_badge(self, obj):
        if obj.is_active:
            return format_html(
                '<span style="background:#16a34a;color:#fff;padding:2px 10px;'
                'border-radius:9999px;font-size:11px;font-weight:600;">Active</span>'
            )
        return format_html(
            '<span style="background:#6b7280;color:#fff;padding:2px 10px;'
            'border-radius:9999px;font-size:11px;">Inactive</span>'
        )
    status_badge.short_description = "Status"

    def connection_help(self, obj):
        return format_html(
            '<div style="background:#eff4ff;border:1px solid #bfdbfe;border-radius:6px;'
            'padding:12px 16px;font-size:13px;line-height:1.8;color:#1e3a5f;">'
            '<strong>How to get a Gmail App Password:</strong><br>'
            '1. Go to <a href="https://myaccount.google.com/security" target="_blank" '
            'style="color:#1A56DB;">myaccount.google.com/security</a><br>'
            '2. Make sure <strong>2-Step Verification</strong> is turned on<br>'
            '3. Search for <strong>App Passwords</strong> in the search bar<br>'
            '4. Create a new App Password — select app: <em>Mail</em>, device: <em>Other</em><br>'
            '5. Copy the 16-character password and paste it above<br><br>'
            '<strong>Note:</strong> Use the App Password here, <em>not</em> your regular Gmail password.'
            '</div>'
        )
    connection_help.short_description = "Setup Guide"

    @admin.action(description="Send a test email to verify the configuration")
    def send_test_email(self, request, queryset):
        for config in queryset:
            try:
                connection = config.get_connection()
                msg = EmailMessage(
                    subject="Test Email — Hasker & Co. Realty Group",
                    body=(
                        f"Hi,\n\n"
                        f"This is a test email from Hasker & Co. Realty Group.\n\n"
                        f"Your email configuration is working correctly.\n\n"
                        f"Sender:  {config.get_from_header()}\n"
                        f"SMTP:    {config.smtp_host}:{config.smtp_port}\n"
                        f"TLS:     {'Yes' if config.use_tls else 'No'}\n\n"
                        f"— Hasker & Co. Realty Group Admin"
                    ),
                    from_email=config.get_from_header(),
                    to=[config.email_host_user],
                    connection=connection,
                )
                msg.send()
                self.message_user(
                    request,
                    f"Test email sent successfully to {config.email_host_user}. "
                    f"Check your inbox.",
                    level=messages.SUCCESS,
                )
            except Exception as e:
                self.message_user(
                    request,
                    f"Failed to send test email: {e}",
                    level=messages.ERROR,
                )
