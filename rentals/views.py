from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    ConsentRecord,
    CreditScore,
    Dispute,
    RentalAgreement,
    RentalReport,
    TenantInvitation,
    TenantProfile,
)
from .permissions import IsLandlord, IsTenant
from .serializers import (
    ConsentRecordSerializer,
    CreditScoreSerializer,
    DisputeAdminUpdateSerializer,
    DisputeCreateSerializer,
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
        if user.role == User.Role.ADMIN:
            return RentalAgreement.objects.select_related("landlord", "tenant").all()
        if user.role == User.Role.LANDLORD:
            return RentalAgreement.objects.select_related("landlord", "tenant").filter(
                landlord=user
            )
        if user.role == User.Role.TENANT:
            return RentalAgreement.objects.select_related("landlord", "tenant").filter(
                tenant=user
            )
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
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if user.role == User.Role.ADMIN:
            return RentalReport.objects.select_related("agreement", "submitted_by")
        if user.role == User.Role.LANDLORD:
            return RentalReport.objects.select_related("agreement", "submitted_by").filter(
                agreement__landlord=user
            )
        if user.role == User.Role.TENANT:
            return RentalReport.objects.select_related("agreement", "submitted_by").filter(
                agreement__tenant=user
            )
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
            "filed_by", "agreement", "rental_report"
        ).order_by("-created_at")
        if user.role == User.Role.ADMIN:
            return qs
        if user.role == User.Role.LANDLORD:
            return qs.filter(agreement__landlord=user)
        if user.role == User.Role.TENANT:
            return qs.filter(filed_by=user)
        return Dispute.objects.none()

    def get_serializer_class(self):
        if self.action in ("partial_update", "update"):
            return DisputeAdminUpdateSerializer
        if self.action == "create":
            return DisputeCreateSerializer
        return DisputeSerializer

    def perform_create(self, serializer):
        if self.request.user.role != User.Role.TENANT:
            raise PermissionDenied("Only tenants can file disputes.")
        serializer.save()

    def partial_update(self, request, *args, **kwargs):
        if request.user.role != User.Role.ADMIN:
            raise PermissionDenied("Only administrators can update disputes.")
        return super().partial_update(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)


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
