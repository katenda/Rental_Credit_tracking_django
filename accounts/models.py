from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        LANDLORD = "landlord", "Landlord"
        TENANT = "tenant", "Tenant"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.TENANT,
        db_index=True,
    )

    def __str__(self):
        return f"{self.username} ({self.role})"
