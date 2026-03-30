from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CreditScore, LandlordProfile, TenantProfile

User = get_user_model()


@receiver(post_save, sender=User)
def create_role_profile(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.role == User.Role.LANDLORD:
        LandlordProfile.objects.get_or_create(user=instance)
    elif instance.role == User.Role.TENANT:
        profile, _ = TenantProfile.objects.get_or_create(user=instance)
        CreditScore.objects.get_or_create(
            tenant_profile=profile,
            defaults={"score": 100},
        )
