from django.db import models


class EmailConfiguration(models.Model):
    """
    Singleton model — stores the SMTP credentials used to send all
    Hasker & Co. Realty Group emails.  Only one active row should exist at a time.

    How to use:
      config = EmailConfiguration.get_active()
      if config:
          connection = config.get_connection()
          ...
    """

    display_name    = models.CharField(
        max_length=100,
        default="Hasker & Co. Realty Group",
        help_text="Sender name shown in the recipient's inbox.",
    )
    from_email      = models.EmailField(
        help_text="The email address emails are sent from (e.g. info@haskerrealtygroup.com).",
    )
    smtp_host       = models.CharField(
        max_length=200,
        default="smtp.gmail.com",
        help_text="SMTP server hostname. Gmail: smtp.gmail.com",
    )
    smtp_port       = models.PositiveIntegerField(
        default=587,
        help_text="SMTP port. Use 587 for TLS (recommended) or 465 for SSL.",
    )
    use_tls         = models.BooleanField(
        default=True,
        help_text="Enable TLS encryption (recommended for port 587).",
    )
    use_ssl         = models.BooleanField(
        default=False,
        help_text="Enable SSL encryption (use for port 465). Do not enable both TLS and SSL.",
    )
    email_host_user = models.EmailField(
        help_text="The Gmail (or other provider) account used to authenticate with the SMTP server.",
    )
    email_host_password = models.CharField(
        max_length=300,
        help_text=(
            "Gmail App Password — 16-character password generated at "
            "myaccount.google.com/apppasswords. Do NOT use your regular Gmail password."
        ),
    )
    is_active       = models.BooleanField(
        default=True,
        help_text="Only the active configuration is used. Disable to pause all outgoing email.",
    )
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Email Configuration"
        verbose_name_plural = "Email Configuration"

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.display_name} <{self.from_email}> [{status}]"

    def get_from_header(self) -> str:
        """Returns a properly formatted From header: 'Name <email>'"""
        return f"{self.display_name} <{self.from_email}>"

    def get_connection(self):
        """
        Returns an open SMTP connection using this configuration's credentials.
        Use as a context manager or pass directly to EmailMessage(connection=...).
        """
        from django.core.mail import get_connection
        return get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=self.smtp_host,
            port=self.smtp_port,
            username=self.email_host_user,
            password=self.email_host_password,
            use_tls=self.use_tls,
            use_ssl=self.use_ssl,
        )

    @classmethod
    def get_active(cls):
        """Returns the currently active EmailConfiguration, or None."""
        return cls.objects.filter(is_active=True).first()
