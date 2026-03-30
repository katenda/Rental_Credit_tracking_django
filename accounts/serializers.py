from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from rentals.models import TenantInvitation

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "role")
        read_only_fields = ("id", "role")


class UserBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "role", "is_active", "date_joined")
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(choices=User.Role.choices)
    invite_token = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
            "role",
            "invite_token",
        )

    def validate(self, attrs):
        token = attrs.get("invite_token")
        if token is not None:
            if attrs.get("role") != User.Role.TENANT:
                raise serializers.ValidationError(
                    {"role": "Invited users must register as a tenant."}
                )
            try:
                inv = TenantInvitation.objects.select_related("landlord").get(token=token)
            except TenantInvitation.DoesNotExist:
                raise serializers.ValidationError({"invite_token": "Invalid invitation."})
            if inv.redeemed_at is not None:
                raise serializers.ValidationError(
                    {"invite_token": "This invitation was already used."}
                )
            if inv.expires_at < timezone.now():
                raise serializers.ValidationError(
                    {"invite_token": "This invitation has expired."}
                )
            email = (attrs.get("email") or "").strip().lower()
            if email != inv.email.lower():
                raise serializers.ValidationError(
                    {"email": "Email must match the invitation."}
                )
        return attrs

    def validate_role(self, value):
        if value == User.Role.ADMIN:
            raise serializers.ValidationError("Admin accounts cannot be created via registration.")
        return value

    def create(self, validated_data):
        invite_token = validated_data.pop("invite_token", None)
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        if invite_token is not None:
            inv = TenantInvitation.objects.get(token=invite_token)
            inv.redeemed_at = timezone.now()
            inv.redeemed_by = user
            inv.save(update_fields=["redeemed_at", "redeemed_by"])
        return user


class RoleTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data
