from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rentals", "0005_dispute_landlord_response"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentalreport",
            name="status",
            field=models.CharField(
                choices=[("active", "Active"), ("void", "Void / retracted")],
                db_index=True,
                default="active",
                max_length=20,
            ),
        ),
    ]
