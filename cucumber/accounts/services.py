"""Rules for the accounts app. Views call these; they never hold rules themselves.

A role is a Django group (U0.2 design §2.7); the permission matrix is U0.6.
Logging in, the wrong-password lock and the Staff pages are U0.5 (design §7).

Each account change writes one plain log line (design §8): account ids only,
never a password, a session id or the email typed into a failed login.
"""

import ipaddress
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models.functions import Now
from django.http import HttpRequest
from django.utils import timezone

from cucumber.accounts.models import LoginFailure, PasswordChangeDue
from cucumber.core.refusals import refuse

logger = logging.getLogger(__name__)

ADMIN = "admin"
SUPERVISOR = "supervisor"
TECH = "tech"

# Design §4, §7.2: rules, not settings, so the tests read them from here.
SESSION_MAX_AGE = timedelta(days=30)
LOCK_AFTER_FAILURES = 5
LOCK_WINDOW = timedelta(minutes=15)
ADDRESS_LIMIT = 50
# Failures older than this are deleted at each login (§7.5).
FAILURES_KEPT_FOR = timedelta(days=1)

# auth_user.username's size; the email is stored there (§2.1).
LONGEST_EMAIL = 150

# Design §7.3: letters and digits without look-alikes (no 0 o 1 l i),
# three groups of four joined by dashes, about 60 bits.
TEMPORARY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
TEMPORARY_GROUPS = 3
TEMPORARY_GROUP_LENGTH = 4
# A random one fails Django's four rules very rarely; this many in a row
# means something is wrong with the rules, not bad luck.
TEMPORARY_TRIES = 20


@dataclass(frozen=True)
class NewAccount:
    """An account just added, and its temporary password (shown once, §6.2)."""

    account: User
    password: str


def has_role(user: User | AnonymousUser, role: str) -> bool:
    """True when `user` is in the role's group."""
    return user.groups.filter(name=role).exists()


def members_of(role: str) -> frozenset[int]:
    """The ids of every user in the role's group."""
    return frozenset(
        User.objects.filter(groups__name=role).values_list("id", flat=True)
    )


# ------------------------------------------------------------------ accounts


def email_key(text: str) -> str:
    """The email as stored and compared: trimmed and lowercase (§2.1).

    `lower()`, not `casefold()`, so it matches PostgreSQL's lower().
    """
    return text.strip().lower()


def require_admin(user: User | AnonymousUser) -> None:
    """Raise `PermissionDenied` unless `user` is the Admin (AC28)."""
    if not user.is_authenticated or not has_role(user, ADMIN):
        raise PermissionDenied


def checked_email(email: str) -> str:
    """The email key, or `account_email_invalid` if it isn't a whole email."""
    key = email_key(email)
    try:
        validate_email(key)
    except ValidationError:
        raise refuse("account_email_invalid") from None
    if len(key) > LONGEST_EMAIL:
        raise refuse("account_email_invalid")
    return key


def add_account(by: User, name: str, email: str) -> NewAccount:
    """Add an account with a temporary password it must change (AC22).

    The account has no role yet (U0.6), so it sees only the home page.
    """
    require_admin(by)
    key = checked_email(email)
    if User.objects.filter(username=key).exists():
        raise refuse("account_email_taken")
    account = User(username=key, email=key, first_name=name.strip())
    password = new_temporary_password(account)
    account.set_password(password)
    try:
        with transaction.atomic():
            account.save()
            PasswordChangeDue.objects.create(user=account)
    except IntegrityError:
        # Someone else added the same email a moment ago.
        raise refuse("account_email_taken") from None
    logger.info("account added account=%s by=%s", account.pk, by.pk)
    return NewAccount(account=account, password=password)


def deactivate(by: User, account: User) -> None:
    """Switch an account off; never your own (AC23, AC24).

    Its open sessions end on their next page: Django checks `is_active` each
    time it loads the user. The account and everything it saved stay.
    """
    require_admin(by)
    if by.pk == account.pk:
        raise refuse("account_cannot_deactivate_self")
    User.objects.filter(pk=account.pk).update(is_active=False)
    logger.info("account deactivated account=%s by=%s", account.pk, by.pk)


def reactivate(by: User, account: User) -> None:
    """Switch an account back on (AC23)."""
    require_admin(by)
    User.objects.filter(pk=account.pk).update(is_active=True)
    logger.info("account reactivated account=%s by=%s", account.pk, by.pk)


def give_new_password(by: User, account: User) -> str:
    """A new temporary password for someone else; returns it (AC25).

    The password and its change-due mark are saved together or not at all.
    The person's open sessions end because the password changed.
    """
    require_admin(by)
    if by.pk == account.pk:
        raise refuse("account_cannot_reset_self")
    password = new_temporary_password(account)
    with transaction.atomic():
        User.objects.filter(pk=account.pk).update(password=make_password(password))
        # The app may add and remove these rows, never edit them (§3.2).
        PasswordChangeDue.objects.filter(user_id=account.pk).delete()
        PasswordChangeDue.objects.create(user_id=account.pk)
    logger.info("password given account=%s by=%s", account.pk, by.pk)
    return password


def lift_lock(by: User, account: User) -> None:
    """Clear this account's wrong-password count (AC11)."""
    require_admin(by)
    LoginFailure.objects.filter(email_key=account.username).delete()
    logger.info("lock lifted account=%s by=%s", account.pk, by.pk)


def password_chosen(user: User) -> None:
    """The person saved their own password: no change is due any more."""
    PasswordChangeDue.objects.filter(user_id=user.pk).delete()
    logger.info("password chosen account=%s", user.pk)


def change_is_due(user: User) -> bool:
    """True while the person must choose their own password (AC25)."""
    return PasswordChangeDue.objects.filter(user_id=user.pk).exists()


def new_temporary_password(account: User) -> str:
    """Twelve letters and digits without look-alikes, in groups of four (§7.3).

    Checked against Django's four rules for this person, and made again in
    the rare case it fails one.
    """
    for _ in range(TEMPORARY_TRIES):
        password = "-".join(
            "".join(
                secrets.choice(TEMPORARY_ALPHABET)
                for _ in range(TEMPORARY_GROUP_LENGTH)
            )
            for _ in range(TEMPORARY_GROUPS)
        )
        try:
            validate_password(password, user=account)
        except ValidationError:
            continue
        return password
    raise RuntimeError(
        f"No temporary password passed the password rules in {TEMPORARY_TRIES}"
        " tries; check AUTH_PASSWORD_VALIDATORS."
    )


# ---------------------------------------------------------------------- lock


def client_address(request: HttpRequest) -> str | None:
    """Where a login came from (§7.2), or None when it can't be told.

    On the servers every request comes through the Cloudflare tunnel, so the
    phone's address is Cloudflare's `CF-Connecting-IP` header. Locally anyone
    could send that header, so it's ignored and `REMOTE_ADDR` is used.
    """
    header = "HTTP_CF_CONNECTING_IP" if settings.IS_SERVER else "REMOTE_ADDR"
    raw = request.META.get(header, "")
    try:
        return str(ipaddress.ip_address(raw.strip()))
    except ValueError:
        return None


def login_lock(email: str, address: str | None) -> bool:
    """True when this email, or this network address, has tried too often."""
    if locked_until(email) is not None:
        return True
    if address is None:
        return False
    from_address = LoginFailure.objects.filter(
        address=address, at__gt=Now() - LOCK_WINDOW
    ).count()
    return from_address >= ADDRESS_LIMIT


def locked_until(email: str) -> datetime | None:
    """When this email's lock lifts by itself, or None if it isn't locked.

    An email locks when its last 5 failures all fall within 15 minutes, and
    stays locked for 15 minutes after the 5th (AC7). Tries while locked
    aren't counted, so the 5th is always the newest failure.
    """
    newest_first = (
        LoginFailure.objects.filter(email_key=email_key(email))
        .order_by("-at")
        .values_list("at", flat=True)
    )
    times = list(newest_first[:LOCK_AFTER_FAILURES])
    if len(times) < LOCK_AFTER_FAILURES:
        return None
    fifth, first = times[0], times[-1]
    if fifth - first > LOCK_WINDOW:
        return None
    until = fifth + LOCK_WINDOW
    return until if until > timezone.now() else None


def account_label(email: str) -> str:
    """The account id for a log line, or "unknown"; never the typed email."""
    found = User.objects.filter(username=email_key(email)).values_list("pk", flat=True)
    pk = found.first()
    return "unknown" if pk is None else str(pk)


def login_failed(email: str, address: str | None) -> None:
    """Count one wrong try. Never given the password."""
    LoginFailure.objects.create(email_key=email_key(email), address=address)
    logger.info(
        "login failed account=%s address=%s",
        account_label(email),
        address or "unknown",
    )


def login_turned_away(email: str, address: str | None) -> None:
    """Log a try the lock stopped. It isn't counted (§7.2)."""
    logger.info(
        "login locked account=%s address=%s",
        account_label(email),
        address or "unknown",
    )


def login_succeeded(email: str) -> None:
    """Clear this email's count, and tidy up old rows (§7.5)."""
    LoginFailure.objects.filter(email_key=email_key(email)).delete()
    LoginFailure.objects.filter(at__lt=Now() - FAILURES_KEPT_FOR).delete()
    Session.objects.filter(expire_date__lt=Now()).delete()
