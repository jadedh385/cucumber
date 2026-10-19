"""Account pages (design §6). Thin: read the form, call a service, show the result.

Every Staff page checks for the Admin through `require_admin` (AC28);
anyone else gets 403. The two pages that show a temporary password answer
the POST directly and are never cached (§6.2): a redirect would have to
carry the password through the session or Django's messages.
"""

from dataclasses import dataclass
from datetime import datetime

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from cucumber.accounts import services
from cucumber.accounts.forms import AddAccountForm, ChangePasswordForm
from cucumber.core.refusals import Refused


@dataclass(frozen=True)
class StaffRow:
    """One account as the Staff pages show it."""

    account: User
    is_you: bool
    locked_until: datetime | None


def staff_row(request: HttpRequest, account: User) -> StaffRow:
    return StaffRow(
        account=account,
        is_you=account.pk == request.user.pk,
        locked_until=services.locked_until(account.username),
    )


def signed_in_user(request: HttpRequest) -> User:
    """The signed-in account; LoginRequired has already turned others away."""
    user = request.user
    if not isinstance(user, User):
        raise PermissionDenied
    return user


def safe_next(request: HttpRequest) -> str | None:
    """The `next` page, if it is on this site."""
    page = request.POST.get("next") or request.GET.get("next")
    if page and url_has_allowed_host_and_scheme(
        page, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return page
    return None


# ------------------------------------------------------------ everyone


@require_safe
def home(request: HttpRequest) -> HttpResponse:
    """`/`: who is signed in; a link to Staff for the Admin (AC18, AC21)."""
    is_admin = services.has_role(signed_in_user(request), services.ADMIN)
    return render(request, "accounts/home.html", {"is_admin": is_admin})


def password(request: HttpRequest) -> HttpResponse:
    """Change your own password; also the forced change (AC25, AC26)."""
    user = signed_in_user(request)
    is_forced = services.change_is_due(user)
    form = ChangePasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        # This session stays signed in; the person's others end (AC26).
        update_session_auth_hash(request, user)
        services.password_chosen(user)
        messages.success(request, _("Your new password is saved."))
        return HttpResponseRedirect(safe_next(request) or reverse("home"))
    context = {"form": form, "is_forced": is_forced, "next": safe_next(request)}
    return render(request, "accounts/password.html", context)


# --------------------------------------------------------- Admin only


@require_safe
def staff_list(request: HttpRequest) -> HttpResponse:
    services.require_admin(request.user)
    accounts = User.objects.order_by("first_name", "username")
    rows = [staff_row(request, account) for account in accounts]
    return render(request, "accounts/staff_list.html", {"rows": rows})


@never_cache
def staff_new(request: HttpRequest) -> HttpResponse:
    """Add an account; the POST answers with its temporary password (§6.2)."""
    by = signed_in_user(request)
    services.require_admin(by)
    form = AddAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            added = services.add_account(
                by, form.cleaned_data["name"], form.cleaned_data["email"]
            )
        except Refused as refusal:
            form.add_error("email", refusal.message)
        else:
            return temporary_password_page(request, added.account, added.password)
    return render(request, "accounts/staff_new.html", {"form": form})


@require_safe
def staff_detail(request: HttpRequest, account_id: int) -> HttpResponse:
    services.require_admin(request.user)
    account = get_object_or_404(User, pk=account_id)
    return render(
        request, "accounts/staff_detail.html", {"row": staff_row(request, account)}
    )


def temporary_password_page(
    request: HttpRequest, account: User, temporary: str
) -> HttpResponse:
    """Shown once, in this answer only (§6.2)."""
    context = {"account": account, "temporary": temporary}
    return render(request, "accounts/staff_password.html", context)


def account_for_button(request: HttpRequest, account_id: int) -> tuple[User, User]:
    """(the Admin, the account) for one of the Staff buttons."""
    by = signed_in_user(request)
    services.require_admin(by)
    return by, get_object_or_404(User, pk=account_id)


def name_of(account: User) -> str:
    return account.first_name or account.email


def refusal_text(refusal: Refused) -> SafeString:
    """A refusal's message for the page, its apostrophes kept as typed.

    The message is a constant from core's MESSAGES table, never input.
    """
    return mark_safe(refusal.message)  # noqa: S308 (a constant, see above)


def about(account: User, message: str) -> SafeString:
    """`message` with the account's name filled in, the name escaped."""
    return format_html(message, name=name_of(account))


@require_POST
def staff_deactivate(request: HttpRequest, account_id: int) -> HttpResponse:
    by, account = account_for_button(request, account_id)
    try:
        services.deactivate(by, account)
    except Refused as refusal:
        messages.error(request, refusal_text(refusal))
    else:
        messages.success(request, about(account, _("{name}'s account is deactivated.")))
    return redirect("staff_detail", account_id=account.pk)


@require_POST
def staff_reactivate(request: HttpRequest, account_id: int) -> HttpResponse:
    by, account = account_for_button(request, account_id)
    services.reactivate(by, account)
    messages.success(request, about(account, _("{name}'s account is active again.")))
    return redirect("staff_detail", account_id=account.pk)


@never_cache
@require_POST
def staff_new_password(request: HttpRequest, account_id: int) -> HttpResponse:
    """Answers with the new temporary password (§6.2)."""
    by, account = account_for_button(request, account_id)
    try:
        temporary = services.give_new_password(by, account)
    except Refused as refusal:
        messages.error(request, refusal_text(refusal))
        return redirect("staff_detail", account_id=account.pk)
    return temporary_password_page(request, account, temporary)


@require_POST
def staff_unlock(request: HttpRequest, account_id: int) -> HttpResponse:
    by, account = account_for_button(request, account_id)
    services.lift_lock(by, account)
    messages.success(request, about(account, _("{name} can log in again.")))
    return redirect("staff_detail", account_id=account.pk)
