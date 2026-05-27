from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0003_paymentmethodconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentmethodconfig",
            name="recipient_name",
            field=models.CharField(blank=True, max_length=200, help_text="e.g. Jerry Michael Skelton"),
        ),
        migrations.AddField(
            model_name="paymentmethodconfig",
            name="bank_name",
            field=models.CharField(blank=True, max_length=100, help_text="e.g. Renasant Bank"),
        ),
        migrations.AddField(
            model_name="paymentmethodconfig",
            name="account_type",
            field=models.CharField(blank=True, max_length=50, help_text="e.g. Checking Account"),
        ),
        migrations.AddField(
            model_name="paymentmethodconfig",
            name="account_number",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="paymentmethodconfig",
            name="routing_number",
            field=models.CharField(blank=True, max_length=20, help_text="Wire / ABA routing number"),
        ),
        migrations.AddField(
            model_name="paymentmethodconfig",
            name="swift_bic",
            field=models.CharField(blank=True, max_length=20, verbose_name="SWIFT / BIC Code"),
        ),
        migrations.AddField(
            model_name="paymentmethodconfig",
            name="bank_address",
            field=models.TextField(blank=True, help_text="Full bank branch address"),
        ),
        migrations.AddField(
            model_name="paymentmethodconfig",
            name="recipient_address",
            field=models.TextField(blank=True, help_text="Recipient's mailing address"),
        ),
        migrations.AlterField(
            model_name="paymentmethodconfig",
            name="handle",
            field=models.CharField(
                blank=True,
                max_length=200,
                help_text='e.g. "@HaskerRealty" or "payments@haskerrealtygroup.com"',
            ),
        ),
    ]
