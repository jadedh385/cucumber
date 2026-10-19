"""Which page answers which web address."""

from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from cucumber.accounts import views as accounts
from cucumber.accounts.forms import LoginForm
from cucumber.core.views import health

# Shows the "Practice data" banner on staging, as every page does (U0.4a AC9).
handler500 = "cucumber.core.views.server_error"

urlpatterns = [
    path("", accounts.home, name="home"),
    path("health/", health, name="health"),
    path(
        "accounts/login/",
        LoginView.as_view(authentication_form=LoginForm),
        name="login",
    ),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/password/", accounts.password, name="password"),
    path("staff/", accounts.staff_list, name="staff"),
    path("staff/new/", accounts.staff_new, name="staff_new"),
    path("staff/<int:account_id>/", accounts.staff_detail, name="staff_detail"),
    path(
        "staff/<int:account_id>/deactivate/",
        accounts.staff_deactivate,
        name="staff_deactivate",
    ),
    path(
        "staff/<int:account_id>/reactivate/",
        accounts.staff_reactivate,
        name="staff_reactivate",
    ),
    path(
        "staff/<int:account_id>/new-password/",
        accounts.staff_new_password,
        name="staff_new_password",
    ),
    path("staff/<int:account_id>/role/", accounts.staff_role, name="staff_role"),
    path("staff/<int:account_id>/unlock/", accounts.staff_unlock, name="staff_unlock"),
]
