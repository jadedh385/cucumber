"""The two small tables U0.5 adds (design §3.1, §3.2).

Accounts themselves are Django's `auth_user`; roles are its groups (U0.6).
`cucumber_app` may add and remove rows here, never edit them (§3.2).
"""

from django.contrib.auth.models import User
from django.db import models
from django.db.models.functions import Now


class LoginFailure(models.Model):
    """One wrong password, counted for the lock (AC7-AC11).

    Holds the email as typed (trimmed, lowercase), where the try came from
    and when; never the password. No link to `auth_user`, so an email with
    no account is counted the same as a real one (AC8).
    """

    email_key = models.CharField(max_length=150)
    address = models.GenericIPAddressField(null=True)
    at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "accounts_login_failure"
        indexes = [
            models.Index(fields=["email_key", "at"], name="login_failure_email_at"),
            models.Index(fields=["address", "at"], name="login_failure_address_at"),
        ]

    def __str__(self) -> str:
        # Never the email: it may be a password typed into the wrong box.
        return f"Login failure {self.pk} at {self.at}"


class PasswordChangeDue(models.Model):
    """A row means: this person must choose their own password first (AC25)."""

    user = models.OneToOneField(
        User, on_delete=models.PROTECT, primary_key=True, related_name="+"
    )
    since = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "accounts_password_change_due"

    def __str__(self) -> str:
        return f"Password change due for account {self.user_id}"
