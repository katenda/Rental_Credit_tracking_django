from django.contrib import admin
from django.urls import include, path

from .health import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("rentals.urls")),
]
