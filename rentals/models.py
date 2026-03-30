import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class LandlordProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="landlord_profile",
    )
    phone = models.CharField(max_length=32, blank=True)
    organization_name = models.CharField(max_length=255, blank=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"LandlordProfile({self.user.username})"


class TenantProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tenant_profile",
    )
    phone = models.CharField(max_length=32, blank=True)

    def __str__(self):
        return f"TenantProfile({self.user.username})"


class TenantInvitation(models.Model):
    """Landlord-issued invite for a tenant to register with a known email."""

    landlord = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tenant_invitations",
    )
    email = models.EmailField()
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    redeemed_at = models.DateTimeField(null=True, blank=True)
    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="redeemed_invitations",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite {self.email} ({self.landlord_id})"

    def save(self, *args, **kwargs):
        if self.expires_at is None:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)


class RentalAgreement(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"

    landlord = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="landlord_agreements",
    )
    tenant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tenant_agreements",
    )
    property_address = models.TextField()
    lease_start = models.DateField()
    lease_end = models.DateField(null=True, blank=True)
    monthly_rent = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Agreement {self.pk}: {self.landlord_id} → {self.tenant_id}"


class ConsentRecord(models.Model):
    """Tenant consent before rental data can be reported (per agreement)."""

    agreement = models.OneToOneField(
        RentalAgreement,
        on_delete=models.CASCADE,
        related_name="consent",
    )
    signed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consent_signatures",
    )
    consent_version = models.CharField(max_length=32, default="1.0")
    signed_at = models.DateTimeField(auto_now_add=True)
    # PNG data URL or raw base64 from signature pad (audit / dispute evidence)
    signature_image = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Consent(agreement={self.agreement_id})"


class RentalReport(models.Model):
    class ReportType(models.TextChoices):
        LATE_PAYMENT = "late_payment", "Late payment"
        DEFAULT = "default", "Default"
        LEASE_VIOLATION = "lease_violation", "Lease violation"

    agreement = models.ForeignKey(
        RentalAgreement,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submitted_reports",
    )
    report_type = models.CharField(max_length=32, choices=ReportType.choices)
    description = models.TextField(blank=True)
    amount_outstanding = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    reported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reported_at"]

    def __str__(self):
        return f"Report {self.pk} ({self.report_type})"


class Dispute(models.Model):
    """Tenant-filed dispute about a report or agreement; admins resolve."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        UNDER_REVIEW = "under_review", "Under review"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    filed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="filed_disputes",
    )
    agreement = models.ForeignKey(
        RentalAgreement,
        on_delete=models.CASCADE,
        related_name="disputes",
    )
    rental_report = models.ForeignKey(
        RentalReport,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="disputes",
    )
    reason = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Dispute {self.pk} ({self.status})"


class CreditScore(models.Model):
    tenant_profile = models.OneToOneField(
        TenantProfile,
        on_delete=models.CASCADE,
        related_name="credit_score",
    )
    score = models.PositiveSmallIntegerField(default=100)
    factors = models.JSONField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"CreditScore({self.tenant_profile.user.username})={self.score}"
