"""Rental credit score from aggregated reports (MVP rules)."""

from django.contrib.auth import get_user_model

from .models import CreditScore, RentalReport, TenantProfile

User = get_user_model()

PENALTIES = {
    RentalReport.ReportType.LATE_PAYMENT: 5,
    RentalReport.ReportType.DEFAULT: 25,
    RentalReport.ReportType.LEASE_VIOLATION: 12,
}


def recalculate_tenant_credit_score(tenant_user_id: int) -> None:
    """Recompute score for a tenant user from all reports on their agreements."""
    try:
        user = User.objects.get(pk=tenant_user_id)
    except User.DoesNotExist:
        return
    if user.role != User.Role.TENANT:
        return
    try:
        profile = TenantProfile.objects.get(user_id=tenant_user_id)
    except TenantProfile.DoesNotExist:
        return

    active_reports = RentalReport.objects.filter(
        agreement__tenant_id=tenant_user_id,
        status=RentalReport.Status.ACTIVE,
    )
    void_count = RentalReport.objects.filter(
        agreement__tenant_id=tenant_user_id,
        status=RentalReport.Status.VOID,
    ).count()
    score = 100
    factors = {
        "late_payment_count": 0,
        "default_count": 0,
        "lease_violation_count": 0,
        "total_reports": 0,
        "void_reports_archived": void_count,
    }
    for r in active_reports:
        factors["total_reports"] += 1
        if r.report_type == RentalReport.ReportType.LATE_PAYMENT:
            score -= PENALTIES[RentalReport.ReportType.LATE_PAYMENT]
            factors["late_payment_count"] += 1
        elif r.report_type == RentalReport.ReportType.DEFAULT:
            score -= PENALTIES[RentalReport.ReportType.DEFAULT]
            factors["default_count"] += 1
        elif r.report_type == RentalReport.ReportType.LEASE_VIOLATION:
            score -= PENALTIES[RentalReport.ReportType.LEASE_VIOLATION]
            factors["lease_violation_count"] += 1

    score = max(0, min(100, score))
    factors["computed_score"] = score

    cs, _ = CreditScore.objects.get_or_create(
        tenant_profile=profile,
        defaults={"score": score, "factors": factors},
    )
    cs.score = score
    cs.factors = factors
    cs.save(update_fields=["score", "factors", "updated_at"])
