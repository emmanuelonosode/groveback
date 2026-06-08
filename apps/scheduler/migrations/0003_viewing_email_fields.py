from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scheduler", "0002_viewing_confirmation_sent"),
    ]

    operations = [
        migrations.AddField(
            model_name="viewing",
            name="lease_term",
            field=models.CharField(
                blank=True,
                help_text='Shown in the confirmation email, e.g. "24 months". Leave blank to hide.',
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="viewing",
            name="access_code",
            field=models.CharField(
                blank=True,
                help_text="Self-tour entry code. If set, it appears in the confirmation email; "
                          "if blank, the email says the code will be sent before the tour.",
                max_length=20,
            ),
        ),
    ]
