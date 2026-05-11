from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminRecalculateTenantCreditView,
    ConsentRecordViewSet,
    CreditScoreViewSet,
    DashboardStatsView,
    DisputeViewSet,
    InvitationValidateView,
    LandlordProfileMeView,
    RentalAgreementViewSet,
    RentalReportViewSet,
    TenantInvitationViewSet,
    TenantProfileMeView,
    TenantSearchListView,
)

router = DefaultRouter()
router.register(r"agreements", RentalAgreementViewSet, basename="agreement")
router.register(r"consents", ConsentRecordViewSet, basename="consent")
router.register(r"reports", RentalReportViewSet, basename="report")
router.register(r"credit-scores", CreditScoreViewSet, basename="credit-score")
router.register(r"disputes", DisputeViewSet, basename="dispute")
router.register(r"invitations", TenantInvitationViewSet, basename="invitation")

urlpatterns = [
    path("dashboard/stats/", DashboardStatsView.as_view(), name="dashboard-stats"),
    path(
        "admin/recalculate-tenant-credit/",
        AdminRecalculateTenantCreditView.as_view(),
        name="admin-recalculate-tenant-credit",
    ),
    path("invitations/validate/", InvitationValidateView.as_view(), name="invitation-validate"),
    path("", include(router.urls)),
    path("profiles/landlord/me/", LandlordProfileMeView.as_view(), name="landlord-profile-me"),
    path("profiles/tenant/me/", TenantProfileMeView.as_view(), name="tenant-profile-me"),
    path("tenants/search/", TenantSearchListView.as_view(), name="tenant-search"),
]
