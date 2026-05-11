import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("rentals", "0006_rentalreport_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="DisputeAuditEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("previous_status", models.CharField(max_length=20)),
                ("new_status", models.CharField(max_length=20)),
                ("previous_resolution_notes", models.TextField(blank=True, default="")),
                ("new_resolution_notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dispute_audit_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "dispute",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_entries",
                        to="rentals.dispute",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="disputeauditentry",
            index=models.Index(fields=["dispute", "created_at"], name="rentals_dis_dispute_6b5c8e_idx"),
        ),
    ]
