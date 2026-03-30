from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

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

User = get_user_model()


class ProfileUserSerializer(serializers.ModelSerializer):
    """Account fields nested on landlord/tenant profile responses."""

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "date_joined",
            "last_login",
        )
        read_only_fields = fields


class LandlordProfileSerializer(serializers.ModelSerializer):
    user = ProfileUserSerializer(read_only=True)

    class Meta:
        model = LandlordProfile
        fields = ("id", "user", "phone", "organization_name", "is_verified")
        read_only_fields = ("id", "user", "is_verified")


class TenantProfileSerializer(serializers.ModelSerializer):
    user = ProfileUserSerializer(read_only=True)

    class Meta:
        model = TenantProfile
        fields = ("id", "user", "phone")
        read_only_fields = ("id", "user")


class TenantSearchSerializer(serializers.ModelSerializer):
    """Limited fields for landlord search results."""

    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    credit_score = serializers.SerializerMethodField()

    class Meta:
        model = TenantProfile
        fields = ("id", "user_id", "username", "first_name", "last_name", "credit_score")

    def get_credit_score(self, obj):
        try:
            return obj.credit_score.score
        except CreditScore.DoesNotExist:
            return None


class TenantInvitationSerializer(serializers.ModelSerializer):
    invite_url = serializers.SerializerMethodField()
    redeemed_by_username = serializers.CharField(
        source="redeemed_by.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = TenantInvitation
        fields = (
            "id",
            "email",
            "token",
            "created_at",
            "expires_at",
            "redeemed_at",
            "redeemed_by_username",
            "invite_url",
        )
        read_only_fields = fields

    def get_invite_url(self, obj):
        base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
        return f"{base}/register?invite={obj.token}"


class TenantInvitationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantInvitation
        fields = ("email",)

    def validate_email(self, value):
        value = value.strip().lower()
        landlord = self.context["request"].user
        if TenantInvitation.objects.filter(
            landlord=landlord,
            email__iexact=value,
            redeemed_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).exists():
            raise serializers.ValidationError("An active invitation already exists for this email.")
        return value

    def create(self, validated_data):
        validated_data["landlord"] = self.context["request"].user
        return TenantInvitation.objects.create(**validated_data)


class RentalAgreementSerializer(serializers.ModelSerializer):
    landlord_name = serializers.CharField(source="landlord.username", read_only=True)
    tenant_name = serializers.CharField(source="tenant.username", read_only=True)
    has_consent = serializers.SerializerMethodField()

    class Meta:
        model = RentalAgreement
        fields = (
            "id",
            "landlord",
            "tenant",
            "landlord_name",
            "tenant_name",
            "property_address",
            "lease_start",
            "lease_end",
            "monthly_rent",
            "status",
            "has_consent",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "landlord",
            "landlord_name",
            "tenant_name",
            "has_consent",
            "created_at",
            "updated_at",
        )

    def get_has_consent(self, obj):
        return hasattr(obj, "consent")

    def validate_tenant(self, value):
        if value.role != User.Role.TENANT:
            raise serializers.ValidationError("The selected user must have the tenant role.")
        return value

    def validate(self, attrs):
        if self.instance is not None and "tenant" in attrs:
            new_tenant = attrs["tenant"]
            new_id = getattr(new_tenant, "pk", new_tenant)
            if new_id != self.instance.tenant_id:
                raise serializers.ValidationError(
                    {"tenant": "The tenant cannot be changed after the agreement is created."}
                )
        return attrs


class ConsentRecordSerializer(serializers.ModelSerializer):
    """`signature` is a PNG data URL from the tenant signature pad (required on create)."""

    signature = serializers.CharField(write_only=True)
    has_signature = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ConsentRecord
        fields = (
            "id",
            "agreement",
            "signed_by",
            "consent_version",
            "signed_at",
            "signature",
            "has_signature",
        )
        read_only_fields = ("id", "signed_by", "signed_at", "has_signature")

    def get_has_signature(self, obj):
        return bool(obj.signature_image and str(obj.signature_image).strip())

    def validate_signature(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("Please sign using the signature pad before submitting.")
        s = str(value).strip()
        if len(s) < 80:
            raise serializers.ValidationError("Signature data is too short.")
        if len(s) > 1_500_000:
            raise serializers.ValidationError("Signature image is too large.")
        if not (s.startswith("data:image/") or s.startswith("iVBOR")):
            raise serializers.ValidationError("Invalid signature image format.")
        return s

    def validate_agreement(self, agreement):
        if hasattr(agreement, "consent"):
            raise serializers.ValidationError(
                "A consent record already exists for this agreement."
            )
        return agreement

    def create(self, validated_data):
        signature = validated_data.pop("signature")
        instance = super().create(validated_data)
        instance.signature_image = signature
        instance.save(update_fields=["signature_image"])
        return instance


class RentalReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = RentalReport
        fields = (
            "id",
            "agreement",
            "submitted_by",
            "report_type",
            "description",
            "amount_outstanding",
            "reported_at",
        )
        read_only_fields = ("id", "submitted_by", "reported_at")

    def validate_agreement(self, agreement):
        if not hasattr(agreement, "consent"):
            raise serializers.ValidationError(
                "Tenant consent is required before landlords can submit reports for this agreement."
            )
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            if agreement.landlord_id != request.user.id:
                raise serializers.ValidationError(
                    "You can only file reports for agreements where you are the landlord."
                )
        return agreement


class CreditScoreSerializer(serializers.ModelSerializer):
    tenant_username = serializers.CharField(
        source="tenant_profile.user.username",
        read_only=True,
    )

    class Meta:
        model = CreditScore
        fields = ("id", "tenant_profile", "tenant_username", "score", "factors", "updated_at")
        read_only_fields = fields


class DisputeSerializer(serializers.ModelSerializer):
    filed_by_username = serializers.CharField(source="filed_by.username", read_only=True)
    property_address = serializers.CharField(source="agreement.property_address", read_only=True)
    rental_report_type = serializers.CharField(
        source="rental_report.report_type",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Dispute
        fields = (
            "id",
            "agreement",
            "property_address",
            "rental_report",
            "rental_report_type",
            "filed_by",
            "filed_by_username",
            "reason",
            "status",
            "resolution_notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DisputeCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dispute
        fields = ("agreement", "rental_report", "reason")

    def validate(self, attrs):
        request = self.context["request"]
        agreement = attrs["agreement"]
        if agreement.tenant_id != request.user.id:
            raise serializers.ValidationError(
                {"agreement": "You can only file disputes for your own lease agreements."}
            )
        rep = attrs.get("rental_report")
        if rep is not None and rep.agreement_id != agreement.id:
            raise serializers.ValidationError(
                {"rental_report": "The report must belong to the selected agreement."}
            )
        return attrs

    def create(self, validated_data):
        validated_data["filed_by"] = self.context["request"].user
        validated_data.setdefault("status", Dispute.Status.OPEN)
        return Dispute.objects.create(**validated_data)


class DisputeAdminUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dispute
        fields = ("status", "resolution_notes")
