from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="JobApplication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role_id", models.CharField(max_length=100)),
                ("role_title", models.CharField(max_length=200)),
                ("full_name", models.CharField(max_length=200)),
                ("email", models.EmailField(max_length=254)),
                ("phone", models.CharField(max_length=20)),
                ("linkedin_url", models.URLField(blank=True)),
                ("motivation", models.TextField()),
                ("extra_field_label", models.CharField(blank=True, max_length=200)),
                ("extra_field_value", models.CharField(blank=True, max_length=300)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("SUBMITTED", "Submitted"),
                            ("UNDER_REVIEW", "Under Review"),
                            ("INTERVIEW_SCHEDULED", "Interview Scheduled"),
                            ("HIRED", "Hired"),
                            ("REJECTED", "Rejected"),
                        ],
                        default="SUBMITTED",
                        max_length=30,
                    ),
                ),
                ("applied_at", models.DateTimeField(auto_now_add=True)),
                ("staff_notes", models.TextField(blank=True)),
                ("interview_date", models.DateTimeField(blank=True, null=True)),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_job_applications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Job Application",
                "verbose_name_plural": "Job Applications",
                "ordering": ["-applied_at"],
            },
        ),
    ]
