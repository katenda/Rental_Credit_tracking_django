from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    ConsentRecord,
    CreditScore,
    Dispute,
    DisputeAuditEntry,
    RentalAgreement,
    RentalReport,
    TenantInvitation,
    TenantProfile,
)
from .permissions import IsAdminRole, IsLandlord, IsTenant
from .serializers import (
    AdminRecalculateTenantCreditSerializer,
    ConsentRecordSerializer,
    CreditScoreSerializer,
    DisputeAdminUpdateSerializer,
    DisputeAuditEntrySerializer,
    DisputeCreateSerializer,
    DisputeLandlordUpdateSerializer,
    DisputeSerializer,
    LandlordProfileSerializer,
    RentalAgreementSerializer,
    RentalReportSerializer,
    TenantInvitationCreateSerializer,
    TenantInvitationSerializer,
    TenantProfileSerializer,
    TenantSearchSerializer,
)

User = get_user_model()


class LandlordProfileMeView(generics.RetrieveUpdateAPIView):
    serializer_class = LandlordProfileSerializer
    permission_classes = [IsAuthenticated, IsLandlord]

    def get_object(self):
        return self.request.user.landlord_profile


class TenantProfileMeView(generics.RetrieveUpdateAPIView):
    serializer_class = TenantProfileSerializer
    permission_classes = [IsAuthenticated, IsTenant]

    def get_object(self):
        return self.request.user.tenant_profile


class TenantSearchListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsLandlord]
    serializer_class = TenantSearchSerializer

    def get_queryset(self):
        qs = TenantProfile.objects.select_related("user").all()
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(user__username__icontains=q)
                | Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
            )
        return qs[:50]


class RentalAgreementViewSet(viewsets.ModelViewSet):
    serializer_class = RentalAgreementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        base = RentalAgreement.objects.select_related(
            "landlord",
            "tenant",
            "tenant__tenant_profile",
        ).select_related("tenant__tenant_profile__credit_score")
        if user.role == User.Role.ADMIN:
            return base.all()
        if user.role == User.Role.LANDLORD:
            return base.filter(landlord=user)
        if user.role == User.Role.TENANT:
            return base.filter(tenant=user)
        return RentalAgreement.objects.none()

    def perform_create(self, serializer):
        if self.request.user.role != User.Role.LANDLORD:
            raise PermissionDenied("Only landlords can create rental agreements.")
        serializer.save(landlord=self.request.user)

    def perform_update(self, serializer):
        user = self.request.user
        obj = self.get_object()
        if user.role == User.Role.TENANT:
            raise PermissionDenied("Tenants cannot update agreements.")
        if user.role == User.Role.LANDLORD and obj.landlord_id != user.id:
            raise PermissionDenied("You can only update agreements you own.")
        serializer.save()


class ConsentRecordViewSet(viewsets.mixins.CreateModelMixin, viewsets.mixins.ListModelMixin, viewsets.mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ConsentRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == User.Role.ADMIN:
            return ConsentRecord.objects.select_related("agreement", "signed_by")
        if user.role == User.Role.TENANT:
            return ConsentRecord.objects.select_related("agreement", "signed_by").filter(
                agreement__tenant=user
            )
        if user.role == User.Role.LANDLORD:
            return ConsentRecord.objects.select_related("agreement", "signed_by").filter(
                agreement__landlord=user
            )
        return ConsentRecord.objects.none()

    def perform_create(self, serializer):
        if self.request.user.role != User.Role.TENANT:
            raise PermissionDenied("Only tenants can record consent.")
        agreement = serializer.validated_data["agreement"]
        if agreement.tenant_id != self.request.user.id:
            raise PermissionDenied("You can only sign consent for your own lease agreements.")
        serializer.save(signed_by=self.request.user)


class RentalReportViewSet(viewsets.ModelViewSet):
    serializer_class = RentalReportSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        base = RentalReport.objects.select_related(
            "agreement",
            "agreement__tenant",
            "submitted_by",
        )
        if user.role == User.Role.ADMIN:
            return base
        if user.role == User.Role.LANDLORD:
            return base.filter(agreement__landlord=user)
        if user.role == User.Role.TENANT:
            return base.filter(agreement__tenant=user)
        return RentalReport.objects.none()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx

    def perform_create(self, serializer):
        if self.request.user.role != User.Role.LANDLORD:
            raise PermissionDenied("Only landlords can submit rental reports.")
        agreement = serializer.validated_data["agreement"]
        if agreement.landlord_id != self.request.user.id:
            raise PermissionDenied("You can only report on your own agreements.")
        instance = serializer.save(submitted_by=self.request.user)
        from .scoring import recalculate_tenant_credit_score

        recalculate_tenant_credit_score(instance.agreement.tenant_id)

    def destroy(self, request, *args, **kwargs):
        """Soft-delete: mark report void (keeps row for disputes/audit); recalculates tenant score."""
        instance = self.get_object()
        user = request.user
        if user.role == User.Role.TENANT:
            raise PermissionDenied("Tenants cannot retract rental reports.")
        if user.role == User.Role.LANDLORD and instance.agreement.landlord_id != user.id:
            raise PermissionDenied("You can only retract reports on your own agreements.")
        if user.role not in (User.Role.LANDLORD, User.Role.ADMIN):
            raise PermissionDenied("You cannot retract rental reports.")
        tenant_id = instance.agreement.tenant_id
        if instance.status != RentalReport.Status.VOID:
            instance.status = RentalReport.Status.VOID
            instance.save(update_fields=["status"])
        from .scoring import recalculate_tenant_credit_score

        recalculate_tenant_credit_score(tenant_id)
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CreditScoreViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CreditScoreSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        base = CreditScore.objects.select_related("tenant_profile__user")
        if user.role == User.Role.ADMIN:
            return base
        if user.role == User.Role.TENANT:
            return base.filter(tenant_profile__user=user)
        if user.role == User.Role.LANDLORD:
            tenant_ids = RentalAgreement.objects.filter(landlord=user).values_list(
                "tenant_id", flat=True
            ).distinct()
            return base.filter(tenant_profile__user_id__in=tenant_ids)
        return CreditScore.objects.none()


class DisputeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        qs = Dispute.objects.select_related(
            "filed_by",
            "agreement",
            "agreement__tenant",
            "agreement__landlord",
            "rental_report",
        ).order_by("-created_at")
        if user.role == User.Role.ADMIN:
            return qs
        if user.role == User.Role.LANDLORD:
            return qs.filter(agreement__landlord=user)
        if user.role == User.Role.TENANT:
            return qs.filter(filed_by=user)
        return Dispute.objects.none()

    def get_serializer_class(self):
        if self.action in ("partial_update", "update") and self.request.user.role == User.Role.ADMIN:
            return DisputeAdminUpdateSerializer
        if self.action == "create":
            return DisputeCreateSerializer
        return DisputeSerializer

    def perform_create(self, serializer):
        if self.request.user.role != User.Role.TENANT:
            raise PermissionDenied("Only tenants can file disputes.")
        serializer.save()

    def perform_update(self, serializer):
        inst = serializer.instance
        old_status = inst.status
        old_notes = inst.resolution_notes or ""
        super().perform_update(serializer)
        inst.refresh_from_db()
        new_status = inst.status
        new_notes = inst.resolution_notes or ""
        if self.request.user.role == User.Role.ADMIN:
            if old_status != new_status or old_notes != new_notes:
                DisputeAuditEntry.objects.create(
                    dispute=inst,
                    previous_status=old_status,
                    new_status=new_status,
                    previous_resolution_notes=old_notes,
                    new_resolution_notes=new_notes,
                    changed_by=self.request.user,
                )
            from .scoring import recalculate_tenant_credit_score

            recalculate_tenant_credit_score(inst.agreement.tenant_id)

    @action(detail=True, methods=["get"], url_path="audit-log")
    def audit_log(self, request, pk=None):
        """Chronological admin changes to status and resolution notes (visible to tenant, landlord, admin)."""
        dispute = self.get_object()
        qs = DisputeAuditEntry.objects.filter(dispute=dispute).select_related("changed_by").order_by(
            "created_at"
        )
        return Response(DisputeAuditEntrySerializer(qs, many=True).data)

    def partial_update(self, request, *args, **kwargs):
        if request.user.role == User.Role.LANDLORD:
            instance = self.get_object()
            if instance.agreement.landlord_id != request.user.id:
                raise PermissionDenied("You can only respond to disputes on your agreements.")
            extra = set(request.data.keys()) - {"landlord_response"}
            if extra:
                raise PermissionDenied("Landlords may only update the landlord_response field.")
            ser = DisputeLandlordUpdateSerializer(instance, data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            ser.save()
            instance.refresh_from_db()
            return Response(
                DisputeSerializer(instance, context=self.get_serializer_context()).data
            )
        if request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Only administrators can update dispute status and resolution notes.")
        # DRF's UpdateModelMixin.partial_update() calls self.update(). Do not override update() to call
        # partial_update() — that causes infinite recursion for admin PATCH.
        return super().partial_update(request, *args, **kwargs)


class AdminRecalculateTenantCreditView(APIView):
    """Recompute a tenant's rental credit score from current reports (admin support tool)."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        ser = AdminRecalculateTenantCreditSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        tenant_id = ser.validated_data["tenant"]
        from .scoring import recalculate_tenant_credit_score

        recalculate_tenant_credit_score(tenant_id)
        cs = (
            CreditScore.objects.select_related("tenant_profile__user")
            .filter(tenant_profile__user_id=tenant_id)
            .first()
        )
        payload = {
            "tenant": tenant_id,
            "score": cs.score if cs else None,
            "factors": cs.factors if cs else None,
        }
        if cs and getattr(cs, "updated_at", None):
            payload["updated_at"] = cs.updated_at.isoformat()
        return Response(payload)


class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == User.Role.LANDLORD:
            agr = RentalAgreement.objects.filter(landlord=user)
            need_consent = (
                agr.annotate(
                    _has=Exists(
                        ConsentRecord.objects.filter(agreement_id=OuterRef("pk"))
                    )
                )
                .filter(_has=False)
                .count()
            )
            return Response(
                {
                    "role": "landlord",
                    "agreements_total": agr.count(),
                    "agreements_pending_consent": need_consent,
                    "reports_filed": RentalReport.objects.filter(
                        agreement__landlord=user
                    ).count(),
                    "open_disputes": Dispute.objects.filter(
                        agreement__landlord=user,
                        status__in=[
                            Dispute.Status.OPEN,
                            Dispute.Status.UNDER_REVIEW,
                        ],
                    ).count(),
                    "pending_invitations": TenantInvitation.objects.filter(
                        landlord=user,
                        redeemed_at__isnull=True,
                        expires_at__gt=timezone.now(),
                    ).count(),
                }
            )
        if user.role == User.Role.TENANT:
            agr = RentalAgreement.objects.filter(tenant=user)
            need_consent = (
                agr.annotate(
                    _has=Exists(
                        ConsentRecord.objects.filter(agreement_id=OuterRef("pk"))
                    )
                )
                .filter(_has=False)
                .count()
            )
            score_row = CreditScore.objects.filter(tenant_profile__user=user).first()
            open_statuses = [Dispute.Status.OPEN, Dispute.Status.UNDER_REVIEW]
            return Response(
                {
                    "role": "tenant",
                    "agreements_total": agr.count(),
                    "agreements_pending_consent": need_consent,
                    "reports_on_me": RentalReport.objects.filter(
                        agreement__tenant=user
                    ).count(),
                    "credit_score": score_row.score if score_row else None,
                    "disputes_open": Dispute.objects.filter(
                        filed_by=user, status__in=open_statuses
                    ).count(),
                }
            )
        if user.role == User.Role.ADMIN:
            open_statuses = [Dispute.Status.OPEN, Dispute.Status.UNDER_REVIEW]
            return Response(
                {
                    "role": "admin",
                    "users_total": User.objects.count(),
                    "users_landlords": User.objects.filter(
                        role=User.Role.LANDLORD
                    ).count(),
                    "users_tenants": User.objects.filter(role=User.Role.TENANT).count(),
                    "users_admins": User.objects.filter(role=User.Role.ADMIN).count(),
                    "agreements_total": RentalAgreement.objects.count(),
                    "reports_total": RentalReport.objects.count(),
                    "disputes_open": Dispute.objects.filter(
                        status__in=open_statuses
                    ).count(),
                }
            )
        return Response({"role": getattr(user, "role", None)})


class InvitationValidateView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        raw = request.query_params.get("token")
        if not raw:
            return Response(
                {"valid": False, "detail": "Missing token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            inv = TenantInvitation.objects.select_related("landlord").get(token=raw)
        except (TenantInvitation.DoesNotExist, ValueError, DjangoValidationError):
            return Response(
                {"valid": False, "detail": "Invalid invitation."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if inv.redeemed_at is not None:
            return Response(
                {"valid": False, "detail": "This invitation was already used."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if inv.expires_at < timezone.now():
            return Response(
                {"valid": False, "detail": "This invitation has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "valid": True,
                "email": inv.email,
                "landlord_username": inv.landlord.username,
                "expires_at": inv.expires_at,
            }
        )


class TenantInvitationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsLandlord]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return TenantInvitation.objects.filter(landlord=self.request.user).select_related(
            "landlord", "redeemed_by"
        )

    def get_serializer_class(self):
        if self.action == "create":
            return TenantInvitationCreateSerializer
        return TenantInvitationSerializer

    def perform_destroy(self, instance):
        if instance.redeemed_at is not None:
            raise PermissionDenied("Cannot delete a redeemed invitation.")
        instance.delete()
