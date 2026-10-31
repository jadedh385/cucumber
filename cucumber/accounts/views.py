"""Account pages (design §6). Thin: read the form, call a service, show the result.

Each page is labelled with its matrix row (`allowed_for`); `RoleRequired`
answers 403 for any other role (U0.6 §3.1), and the services check again.
The two pages that show a temporary password answer
the POST directly and are never cached (§6.2): a redirect would have to
carry the password through the session or Django's messages.
"""

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
from django.views.decorators.http import (
    require_http_methods,
    require_POST,
    require_safe,
)

from cucumber.accounts import pages, services
from cucumber.accounts.forms import (
    ROLE_LABELS,
    AddAccountForm,
    ChangePasswordForm,
    DeactivateForm,
    RoleForm,
)
from cucumber.accounts.pages import name_of, staff_row
from cucumber.accounts.permissions import Permission, Role, allowed_for, role_named
from cucumber.core.audit import SYSTEM_USERNAME
from cucumber.core.kit import Empty
from cucumber.core.refusals import Refused


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


@allowed_for(Permission.OWN_ACCOUNT)
@require_safe
def home(request: HttpRequest) -> HttpResponse:
    """`/`: a greeting and a tile per menu item but Home (U0.10a §10.1, AC23)."""
    no_work = Empty(_("No work to show yet. Lab work will appear here."))
    return render(request, "accounts/home.html", {"no_work": no_work})


@allowed_for(Permission.OWN_ACCOUNT)
@require_safe
def account(request: HttpRequest) -> HttpResponse:
    """`/account/`: your name and email, Change password and Log out (Q3 a)."""
    return render(request, "accounts/account.html")


@allowed_for(Permission.OWN_ACCOUNT)
@require_http_methods(["GET", "POST"])
def password(request: HttpRequest) -> HttpResponse:
    """Change your own password; also the forced change (AC25, AC26)."""
    user = signed_in_user(request)
    is_forced = services.change_is_due(user)
    if request.method != "POST":
        form = ChangePasswordForm(user)
    else:
        # Bound even when empty, so an empty POST shows its errors (U0.10a AC24).
        form = ChangePasswordForm(user, request.POST)
        if services.choose_own_password(user, form):
            # This session stays signed in; the person's others end (AC26).
            update_session_auth_hash(request, user)
            messages.success(request, _("Your new password is saved."))
            return HttpResponseRedirect(safe_next(request) or reverse("home"))
    context = {"form": form, "is_forced": is_forced, "next": safe_next(request)}
    return render(request, "accounts/password.html", context)


# ------------------------------------------------- Manage users


@allowed_for(Permission.MANAGE_USERS)
@require_safe
def staff_list(request: HttpRequest) -> HttpResponse:
    # System is no one's account to manage (U0.7 design §10).
    accounts = list(
        User.objects.exclude(username=SYSTEM_USERNAME).order_by(
            "first_name", "username"
        )
    )
    roles = dict(User.groups.through.objects.values_list("user_id", "group__name"))
    # Every lock in one query, however many people (U0.10a AC25).
    locks = services.lock_ends([account.username for account in accounts])
    rows = [
        staff_row(
            request,
            account,
            role_named(roles.get(account.pk)),
            locks.get(account.username),
        )
        for account in accounts
    ]
    context = {"table": pages.staff_table(rows)}
    return render(request, "accounts/staff_list.html", context)


@allowed_for(Permission.MANAGE_USERS)
@never_cache
def staff_new(request: HttpRequest) -> HttpResponse:
    """Add an account; the POST answers with its temporary password (§6.2)."""
    by = signed_in_user(request)
    form = AddAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            added = services.add_account(
                by,
                form.cleaned_data["name"],
                form.cleaned_data["email"],
                role_named(form.cleaned_data["role"]),
            )
        except Refused as refusal:
            # Under its field, every answer kept (§7.1); others on top.
            form.add_error(
                AddAccountForm.REFUSAL_FIELDS.get(refusal.rule), refusal.message
            )
        else:
            return temporary_password_page(request, added.account, added.password)
    return render(request, "accounts/staff_new.html", {"form": form})


@allowed_for(Permission.MANAGE_USERS)
@require_safe
def staff_detail(request: HttpRequest, account_id: int) -> HttpResponse:
    account = staff_account(account_id)
    return staff_detail_page(request, account, DeactivateForm())


def staff_detail_page(
    request: HttpRequest, account: User, deactivate_form: DeactivateForm
) -> HttpResponse:
    row = staff_row(
        request,
        account,
        services.role_of(account),
        services.locked_until(account.username),
    )
    context = {
        "row": row,
        "detail": pages.staff_detail(row),
        "role_form": RoleForm(initial={"role": row.role or "none"}),
        "deactivate_form": deactivate_form,
    }
    return render(request, "accounts/staff_detail.html", context)


def temporary_password_page(
    request: HttpRequest, account: User, temporary: str
) -> HttpResponse:
    """Shown once, in this answer only (§6.2)."""
    context = {"account": account, "temporary": temporary}
    return render(request, "accounts/staff_password.html", context)


def account_for_button(request: HttpRequest, account_id: int) -> tuple[User, User]:
    """(the Admin, the account) for one of the Staff buttons."""
    return signed_in_user(request), staff_account(account_id)


def staff_account(account_id: int) -> User:
    """A staff account; System has no page, as it has no row in the list."""
    return get_object_or_404(
        User.objects.exclude(username=SYSTEM_USERNAME), pk=account_id
    )


def refusal_text(refusal: Refused) -> SafeString:
    """A refusal's message for the page, its apostrophes kept as typed.

    The message is a constant from core's MESSAGES table, never input.
    """
    return mark_safe(refusal.message)  # noqa: S308 (a constant, see above)


def about(account: User, message: str) -> SafeString:
    """`message` with the account's name filled in, the name escaped."""
    return format_html(message, name=name_of(account))


@allowed_for(Permission.MANAGE_USERS)
@require_POST
def staff_deactivate(request: HttpRequest, account_id: int) -> HttpResponse:
    """Deactivate with a reason (U0.7 AC11); a reason refusal shows under its box."""
    by, account = account_for_button(request, account_id)
    form = DeactivateForm(request.POST)
    if not form.is_valid():
        return staff_detail_page(request, account, form)
    try:
        services.deactivate(by, account, form.reason())
    except Refused as refusal:
        if refusal.rule in DeactivateForm.REFUSAL_FIELDS:
            field = DeactivateForm.REFUSAL_FIELDS[refusal.rule]
            form.add_error(field, refusal_text(refusal))
            return staff_detail_page(request, account, form)
        messages.error(request, refusal_text(refusal))
    else:
        messages.success(request, about(account, _("{name}'s account is deactivated.")))
    return redirect("staff_detail", account_id=account.pk)


@allowed_for(Permission.MANAGE_USERS)
@require_POST
def staff_reactivate(request: HttpRequest, account_id: int) -> HttpResponse:
    by, account = account_for_button(request, account_id)
    try:
        services.reactivate(by, account)
    except Refused as refusal:
        messages.error(request, about(account, refusal.message))
    else:
        messages.success(
            request, about(account, _("{name}'s account is active again."))
        )
    return redirect("staff_detail", account_id=account.pk)


@allowed_for(Permission.MANAGE_USERS)
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


@allowed_for(Permission.MANAGE_USERS)
@require_POST
def staff_role(request: HttpRequest, account_id: int) -> HttpResponse:
    """Change or remove an account's role (U0.6 AC4); back to its page."""
    by, account = account_for_button(request, account_id)
    form = RoleForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Choose a role."))
        return redirect("staff_detail", account_id=account.pk)
    role = role_named(form.cleaned_data["role"])
    try:
        services.set_role(by, account, role)
    except Refused as refusal:
        messages.error(request, refusal_text(refusal))
    else:
        messages.success(request, role_message(account, role))
    return redirect("staff_detail", account_id=account.pk)


def role_message(account: User, role: Role | None) -> SafeString:
    """ "{name}'s role is now Supervisor." or "{name} has no role now."."""
    if role is None:
        return about(account, _("{name} has no role now."))
    return format_html(
        _("{name}'s role is now {role}."), name=name_of(account), role=ROLE_LABELS[role]
    )


@allowed_for(Permission.MANAGE_USERS)
@require_POST
def staff_unlock(request: HttpRequest, account_id: int) -> HttpResponse:
    by, account = account_for_button(request, account_id)
    services.lift_lock(by, account)
    messages.success(request, about(account, _("{name} can log in again.")))
    return redirect("staff_detail", account_id=account.pk)
