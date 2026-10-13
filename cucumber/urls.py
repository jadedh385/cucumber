"""Which page answers which web address."""

from django.contrib.auth.views import LoginView
from django.urls import path

from cucumber.core.views import health

# Shows the "Practice data" banner on staging, as every page does (U0.4a AC9).
handler500 = "cucumber.core.views.server_error"

urlpatterns = [
    path("health/", health, name="health"),
    path("accounts/login/", LoginView.as_view(), name="login"),
]
