"""Forms for logging in, adding an account and changing a password (design §7.4).

They read and check what was typed; the rules are in services.py.
"""

from typing import Any

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from cucumber.accounts.services import (
    change_is_due,
    client_address,
    email_key,
    login_failed,
    login_lock,
    login_succeeded,
    login_turned_away,
)
from cucumber.core.refusals import message_for

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
        """Lock first, so a locked try never reaches the password check."""
        typed = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if typed is None or password is None:
            return self.cleaned_data
        email = email_key(typed)
        address = client_address(self.request) if self.request else None
        if login_lock(email, address):
            login_turned_away(email, address)
            raise ValidationError(LOCKED, code="locked")
        self.user_cache = authenticate(self.request, username=email, password=password)
        if self.user_cache is None:
            login_failed(email, address)
            raise self.get_invalid_login_error()
        self.confirm_login_allowed(self.user_cache)
        login_succeeded(email)
        return self.cleaned_data


class AddAccountForm(forms.Form):
    """Name and email for a new account (AC22). The service checks the email."""

    name = forms.CharField(label=_("Name"), max_length=150)
    email = forms.CharField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"autocomplete": "off"}),
    )


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
