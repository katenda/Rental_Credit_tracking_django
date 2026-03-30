from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from rentals.scoring import recalculate_tenant_credit_score

User = get_user_model()


class Command(BaseCommand):
    help = "Recompute rental credit scores for all tenant users from existing reports."

    def handle(self, *args, **options):
        ids = list(User.objects.filter(role=User.Role.TENANT).values_list("id", flat=True))
        for uid in ids:
            recalculate_tenant_credit_score(uid)
        self.stdout.write(self.style.SUCCESS(f"Updated scores for {len(ids)} tenant(s)."))
