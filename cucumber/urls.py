"""Which page answers which web address."""

from django.contrib.auth.views import LoginView
from django.urls import path

from cucumber.core.views import health

urlpatterns = [
    path("health/", health, name="health"),
    path("accounts/login/", LoginView.as_view(), name="login"),
]
