"""Forms for logging in, adding an account and changing a password (design §7.4).

They read and check what was typed; the rules are in services.py.
"""

from typing import Any

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from cucumber.accounts.permissions import Role
from cucumber.accounts.services import (
    change_is_due,
    client_address,
    email_key,
    login_failed,
    login_lock,
    login_succeeded,
    login_turned_away,
    one_try_at_a_time,
)
from cucumber.core.audit import Reason
from cucumber.core.kit import ReasonChoiceField
from cucumber.core.refusals import message_for
from cucumber.references.models import ReasonList

# Design §2.2. A wrong password, an unknown email and a deactivated account
# all get WRONG, so nobody can tell which it was (AC2).
WRONG = _("Email or password is wrong.")
LOCKED = _("Too many tries. Wait 15 minutes or ask the Owner.")


class LoginForm(AuthenticationForm):
    """Email and password; checks the lock first (§2.2, §7.2)."""

    error_messages = {"invalid_login": WRONG, "inactive": WRONG}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        email = self.fields["username"]
        email.label = _("Email")
        email.widget = forms.EmailInput(
            attrs={"autocomplete": "username", "autofocus": True}
        )

    def clean(self) -> dict[str, Any]:
        """Lock first, so a locked try never reaches the password check.

        The check and the count happen together, one try per email at a time
        (G4 M3). The refusal is raised after that, so the count is kept.
        """
        typed = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if typed is None or password is None:
            return self.cleaned_data
        email = email_key(typed)
        address = client_address(self.request) if self.request else None
        with one_try_at_a_time(email):
            outcome = self.check_try(email, address, password)
        if isinstance(outcome, ValidationError):
            raise outcome
        self.confirm_login_allowed(outcome)
        login_succeeded(email)
        return self.cleaned_data

    def check_try(
        self, email: str, address: str | None, password: str
    ) -> User | ValidationError:
        """The account when the password is right, else the refusal (counted).

        The account is also kept in `user_cache`, as Django's form does.
        """
        if login_lock(email, address):
            login_turned_away(email, address)
            return ValidationError(LOCKED, code="locked")
        # A right password may be re-hashed (after a Django upgrade): the
        # backend writes that as System (U0.7 design §4.3).
        self.user_cache = authenticate(self.request, username=email, password=password)
        if self.user_cache is None:
            login_failed(email, address)
            return self.get_invalid_login_error()
        return self.user_cache


ROLE_LABELS = {
    Role.ADMIN: _("Admin"),
    Role.SUPERVISOR: _("Supervisor"),
    Role.TECH: _("Tech"),
    Role.READ_ONLY: _("Read Only"),
}
# One line each, from the matrix's words (U0.6 design §7).
ROLE_HELP = {
    Role.ADMIN: _("everything"),
    Role.SUPERVISOR: _("reviews others' work"),
    Role.TECH: _("logs own lab work"),
    Role.READ_ONLY: _("sees, changes none"),
}
NO_ROLE = "none"


def role_choices() -> list[tuple[str, str]]:
    """The four roles as radio choices: value = group name, label + one line."""
    return [(str(role), f"{ROLE_LABELS[role]} — {ROLE_HELP[role]}") for role in Role]


class AddAccountForm(forms.Form):
    """Name, email and role for a new account (AC22, U0.6 AC4).

    The service checks the email. There is no default role and no "no role".
    """

    name = forms.CharField(label=_("Name"), max_length=150)
    email = forms.CharField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"autocomplete": "off"}),
    )
    role = forms.ChoiceField(
        label=_("Role"), choices=role_choices, widget=forms.RadioSelect
    )


class RoleForm(forms.Form):
    """Change or remove an account's role (U0.6 AC4): the four, or `none`."""

    role = forms.ChoiceField(
        label=_("Role"),
        choices=lambda: [*role_choices(), (NO_ROLE, _("No role"))],
        widget=forms.RadioSelect,
    )


class DeactivateForm(forms.Form):
    """A reason from the `deactivate` list (U0.7 AC11, D2).

    A dropdown that passes any code on: the service checks the reason's list,
    so the page shows the same messages a script would get (U0.10a §7.3).
    There is no note: free text would be kept for good and `anonymise`
    couldn't reach it.
    """

    reason_code = ReasonChoiceField(ReasonList.DEACTIVATE, label=_("Reason"))

    def reason(self) -> Reason | None:
        """The picked reason, or None when none was picked."""
        code = self.cleaned_data.get("reason_code", "").strip()
        return Reason(code) if code else None


class ChangePasswordForm(PasswordChangeForm):
    """Django's change form; in a forced change, not the temporary one (AC25)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = _("Current password")
        self.fields["new_password1"].label = _("New password")
        self.fields["new_password2"].label = _("New password again")

    def clean(self) -> dict[str, Any]:
        """The Admin knows the temporary password, so it can't be kept (§7.4)."""
        super().clean()
        new = self.cleaned_data.get("new_password2")
        if new and change_is_due(self.user) and self.user.check_password(new):
            raise ValidationError(
                message_for("password_same_as_temporary"), code="same_as_temporary"
            )
        return self.cleaned_data
