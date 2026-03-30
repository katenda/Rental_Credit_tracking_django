from django.contrib import admin

from .models import (
    ConsentRecord,
    CreditScore,
    Dispute,
    LandlordProfile,
    RentalAgreement,
    RentalReport,
    TenantInvitation,
    TenantProfile,
)


@admin.register(LandlordProfile)
class LandlordProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "organization_name", "is_verified", "phone")
    list_filter = ("is_verified",)


@admin.register(TenantProfile)
class TenantProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone")


@admin.register(TenantInvitation)
class TenantInvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "landlord", "expires_at", "redeemed_at", "created_at")
    list_filter = ("redeemed_at",)
    search_fields = ("email", "token")
    readonly_fields = ("token", "created_at")


@admin.register(RentalAgreement)
class RentalAgreementAdmin(admin.ModelAdmin):
    list_display = ("id", "landlord", "tenant", "status", "lease_start", "monthly_rent")
    list_filter = ("status",)


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ("agreement", "signed_by", "consent_version", "signed_at", "has_signature_data")
    readonly_fields = ("signed_at", "signature_image")

    @admin.display(boolean=True, description="Signature on file")
    def has_signature_data(self, obj):
        return bool(obj.signature_image and str(obj.signature_image).strip())


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = ("id", "agreement", "filed_by", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("reason", "resolution_notes")


@admin.register(RentalReport)
class RentalReportAdmin(admin.ModelAdmin):
    list_display = ("id", "agreement", "report_type", "submitted_by", "reported_at")
    list_filter = ("report_type",)


@admin.register(CreditScore)
class CreditScoreAdmin(admin.ModelAdmin):
    list_display = ("tenant_profile", "score", "updated_at")
