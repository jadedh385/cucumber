"""Forms for logging in, adding an account and changing a password (design §7.4).

They read and check what was typed; the rules are in services.py.
"""

from typing import Any

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from cucumber.accounts.services import NOT_BUILT


class LoginForm(AuthenticationForm):
    """Email and password; checks the lock first (§2.2, §7.2)."""

    def clean(self) -> dict[str, Any]:
        raise NotImplementedError(NOT_BUILT)


class AddAccountForm(forms.Form):
    """Name and email for a new account (AC22)."""

    def clean(self) -> dict[str, Any]:
        raise NotImplementedError(NOT_BUILT)


class ChangePasswordForm(PasswordChangeForm):
    """Django's change form; in a forced change, not the temporary one (AC25)."""

    def clean(self) -> dict[str, Any]:
        raise NotImplementedError(NOT_BUILT)
