from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0008_remove_lead_email_marketing_opted_out_and_more"),
    ]

    operations = [
        # ── Personal ──────────────────────────────────────────────────────────
        migrations.AddField(
            model_name="rentalapplication",
            name="marital_status",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="preferred_contact",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="phone_type",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="emergency_contact_name",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="emergency_contact_relationship",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="emergency_contact_phone",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="emergency_contact_phone_type",
            field=models.CharField(blank=True, max_length=10),
        ),
        # ── Identity ──────────────────────────────────────────────────────────
        migrations.AddField(
            model_name="rentalapplication",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="id_type",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="ssn_last4",
            field=models.CharField(blank=True, max_length=4),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="ein",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="has_drivers_license",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="drivers_license_number",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="drivers_license_state",
            field=models.CharField(blank=True, max_length=2),
        ),
        # ── Income / Employment ───────────────────────────────────────────────
        migrations.AddField(
            model_name="rentalapplication",
            name="gross_monthly_income",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="employer_name",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="employer_phone",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="job_title",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="employment_start_date",
            field=models.DateField(blank=True, null=True),
        ),
        # ── Address History ───────────────────────────────────────────────────
        migrations.AddField(
            model_name="rentalapplication",
            name="how_long_at_address",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="reason_for_leaving",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="current_landlord_name",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="current_landlord_phone",
            field=models.CharField(blank=True, max_length=20),
        ),
        # ── Household ─────────────────────────────────────────────────────────
        migrations.AddField(
            model_name="rentalapplication",
            name="has_vehicles",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="number_of_vehicles",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="animals",
            field=models.JSONField(blank=True, default=list),
        ),
        # ── Background ────────────────────────────────────────────────────────
        migrations.AddField(
            model_name="rentalapplication",
            name="has_felony_eviction_bankruptcy",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="is_active_military",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="rentalapplication",
            name="has_housing_assistance",
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
