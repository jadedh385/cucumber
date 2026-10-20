"""Rules for the accounts app. Views call these; they never hold rules themselves.

A role is a Django group (U0.2 design §2.7); the permission matrix is U0.6.
Logging in, the wrong-password lock and the Staff pages are U0.5 (design §7).

Each account change writes one plain log line (design §8): account ids only,
never a password, a session id or the email typed into a failed login.
"""

import ipaddress
import logging
import secrets
import unicodedata
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AnonymousUser, Group, User
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import connection, transaction
from django.db.models import BooleanField, Count, ExpressionWrapper, Q
from django.db.models.functions import Now
from django.http import HttpRequest

from cucumber.accounts.models import LoginFailure, PasswordChangeDue
from cucumber.accounts.permissions import Permission, Role, may, require, role_named
from cucumber.core.audit import Reason
from cucumber.core.refusals import Refused, database_refusals, refuse

logger = logging.getLogger(__name__)

ADMIN = Role.ADMIN
SUPERVISOR = Role.SUPERVISOR
TECH = Role.TECH

# Design §4, §7.2: rules, not settings, so the tests read them from here.
SESSION_MAX_AGE = timedelta(days=30)
LOCK_AFTER_FAILURES = 5
LOCK_WINDOW = timedelta(minutes=15)
ADDRESS_LIMIT = 50
# Failures older than this are deleted at each login try (§7.5, G4 M4).
FAILURES_KEPT_FOR = timedelta(days=1)
# The first number of the PostgreSQL advisory lock that lets one email's
# login tries through one at a time (G4 M3); the second is the email's hash.
LOGIN_TRY_LOCK = 505

# auth_user.username's size; the email is stored there (§2.1).
LONGEST_EMAIL = 150
# auth_user.first_name's size (AC17).
LONGEST_NAME = 150
# accounts_login_failure.email_key's size (AC19).
LONGEST_KEY = 150
# The rule the database names when the email is already taken (AC18).
EMAIL_TAKEN_RULE = "auth_user_username_key"

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


def active_workers(user_ids: Collection[int]) -> frozenset[int]:
    """Of these accounts, the active ones whose role may log work (§4.2)."""
    roles = [role for role in Role if may(role, Permission.LOG_WORK)]
    return frozenset(
        User.objects.filter(
            pk__in=user_ids, is_active=True, groups__name__in=roles
        ).values_list("pk", flat=True)
    )


def members_of(role: str) -> frozenset[int]:
    """The ids of every user in the role's group."""
    return frozenset(
        User.objects.filter(groups__name=role).values_list("id", flat=True)
    )


# ------------------------------------------------------------------ accounts


def email_key(text: str) -> str:
    """The email as stored and compared: NFKC, trimmed and lowercase (§2.1, AC19).

    The one place emails are made into keys. `lower()`, not `casefold()`, so
    it matches PostgreSQL's lower().
    """
    return unicodedata.normalize("NFKC", text).strip().lower()


def failure_key(email: str) -> str:
    """The email key as `LoginFailure` stores it: NFKC can make one too long (AC19)."""
    return email_key(email)[:LONGEST_KEY]


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


def add_account(by: User, name: str, email: str, role: Role | None) -> NewAccount:
    """Add an account with a role and a temporary password it must change.

    U0.5 AC22; the role is U0.6 AC4 (required: one of the four).
    """
    require(by, Permission.MANAGE_USERS)
    if role is None:
        raise refuse("account_role_required")
    name = name.strip()
    if len(name) > LONGEST_NAME:
        raise refuse("account_name_too_long")
    key = checked_email(email)
    if User.objects.filter(username=key).exists():
        raise refuse("account_email_taken")
    account = User(username=key, email=key, first_name=name)
    password = new_temporary_password(account)
    account.set_password(password)
    try:
        with database_refusals(), transaction.atomic():
            account.save()
            PasswordChangeDue.objects.create(user=account)
            replace_role(account, role)
    except Refused as refusal:
        if refusal.rule == EMAIL_TAKEN_RULE:
            # Someone else added the same email a moment ago.
            raise refuse("account_email_taken") from None
        raise
    logger.info("account added account=%s by=%s", account.pk, by.pk)
    log_role_change(account, None, role, str(by.pk))
    return NewAccount(account=account, password=password)


def deactivate(by: User, account: User, reason: Reason | None) -> None:
    """Switch an account off, with a reason from the `deactivate` list.

    Never your own, nor the last Admin (AC23, AC24); no reason is
    `reason_required` (U0.7 AC11, spec Q3). Its open sessions are removed,
    so switching it back on later doesn't sign a lost phone back in (G4 M1).
    The account and everything it saved stay.
    """
    raise NotImplementedError("U0.7 G3")


def anonymise(account: User) -> None:
    """Remove the account's personal details for good (U0.7 design §7.2).

    Run by `cucumber_anonymise` as System, with the PDPA reason. Refuses the
    last active Admin, the System account and an account already anonymised.
    """
    raise NotImplementedError("U0.7 G3")


def set_role(by: User, account: User, role: Role | None) -> None:
    """Give `account` one role, or none (U0.6 design §5.1, AC4–AC7).

    Never your own (`account_cannot_change_own_role`), and never takes the
    Admin role from the last active Admin (`account_last_admin`).
    """
    require(by, Permission.MANAGE_USERS)
    if by.pk == account.pk:
        raise refuse("account_cannot_change_own_role")
    with transaction.atomic():
        lock_for_account_change(account)
        still_manages_users(by)
        old = role_of(account)
        if old == role:
            return
        if old == Role.ADMIN and is_last_active_admin(account):
            raise refuse("account_last_admin")
        replace_role(account, role)
    log_role_change(account, old, role, str(by.pk))


def still_manages_users(by: User) -> None:
    """The Admin's own role, read again once the locks are held (G4 L1).

    The first check was made before waiting: another Admin may have taken
    `by`'s role meanwhile. `by` is among the locked Admins, so that change
    has committed by now and this read sees it.
    """
    require(by, Permission.MANAGE_USERS)


def role_of(account: User) -> Role | None:
    """The account's role now, read from the database."""
    name = (
        User.objects.filter(pk=account.pk)
        .values_list("groups__name", flat=True)
        .first()
    )
    # A group that isn't a role reads as none, as in `standing` (G4 M1).
    return role_named(name)


def replace_role(account: User, role: Role | None) -> None:
    """Give `account` this role and no other (§5.1), by a plain INSERT.

    Not `groups.add()` or `groups.set()`: on PostgreSQL those write
    `ON CONFLICT DO NOTHING`, so a second role would be skipped silently
    instead of refused by `auth_user_one_role` (§6.2).
    """
    through = User.groups.through
    through.objects.filter(user_id=account.pk).delete()
    if role is not None:
        group = Group.objects.get(name=role.value)
        through.objects.create(user_id=account.pk, group_id=group.pk)


def log_role_change(account: User, old: Role | None, new: Role | None, by: str) -> None:
    """The role-change line (§9): ids only; `by` is an id or "command"."""
    logger.info(
        "role changed account=%s from=%s to=%s by=%s",
        account.pk,
        old or "none",
        new or "none",
        by,
    )


def lock_for_account_change(account: User) -> None:
    """Lock `account` and the active Admins, in id order (§5.1).

    Only takes the locks: under READ COMMITTED the list may be stale after
    a wait, so decisions are made with new queries afterwards. `no_key`, so
    event inserts by these people aren't blocked.
    """
    list(
        User.objects.select_for_update(no_key=True, of=("self",))
        .filter(Q(pk=account.pk) | Q(groups__name=ADMIN, is_active=True))
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def is_last_active_admin(account: User) -> bool:
    """True when `account` is the only active Admin (G4 M2).

    Call after `lock_for_account_change`, in the same transaction, so two
    Admins changing each other at the same moment are taken one at a time:
    the second sees the first's change and is refused.
    """
    active_admins = list(
        User.objects.filter(groups__name=ADMIN, is_active=True).values_list(
            "pk", flat=True
        )
    )
    return active_admins == [account.pk]


def end_sessions_of(account: User) -> None:
    """Remove every open session that belongs to `account`.

    A session's owner is inside its encoded data, so each open one is read;
    there are only as many as the staff's phones.
    """
    owner = str(account.pk)
    theirs = [
        session.session_key
        for session in Session.objects.filter(expire_date__gt=Now())
        if session.get_decoded().get(SESSION_KEY) == owner
    ]
    Session.objects.filter(session_key__in=theirs).delete()


def reactivate(by: User, account: User) -> None:
    """Switch an account back on (AC23)."""
    require(by, Permission.MANAGE_USERS)
    User.objects.filter(pk=account.pk).update(is_active=True)
    logger.info("account reactivated account=%s by=%s", account.pk, by.pk)


def give_new_password(by: User, account: User) -> str:
    """A new temporary password for someone else; returns it (AC25).

    The password and its change-due mark are saved together or not at all.
    The person's open sessions end because the password changed.
    """
    require(by, Permission.MANAGE_USERS)
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
    """Clear this account's wrong-password count, and any locked network (AC11, AC16).

    The person's own tries while the network was locked weren't counted, so
    their email may have no failures to point at the address. So every
    address at or over the 50-try limit is lifted too; each is logged with
    its count first, because deleting the rows removes the evidence.
    """
    require(by, Permission.MANAGE_USERS)
    with transaction.atomic():
        recent = LoginFailure.objects.filter(at__gt=Now() - LOCK_WINDOW)
        locked = {
            row["address"]: row["tries"]
            for row in recent.exclude(address=None)
            .values("address")
            .annotate(tries=Count("pk"))
            .filter(tries__gte=ADDRESS_LIMIT)
        }
        for address, tries in locked.items():
            logger.info("network lock lifted address=%s failures=%s", address, tries)
        LoginFailure.objects.filter(email_key=account.username).delete()
        recent.filter(address__in=list(locked)).delete()
    logger.info(
        "lock lifted account=%s by=%s addresses=%s", account.pk, by.pk, len(locked)
    )


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


def emails_that_may_be_locked() -> frozenset[str]:
    """The email keys with enough recent failures to be locked, in one query.

    A lock needs 5 failures within 15 minutes and the newest within the last
    15, so all 5 fall within twice the window. `locked_until` then decides
    for these few only (the Staff list, G4 L5).
    """
    return frozenset(
        LoginFailure.objects.filter(at__gt=Now() - 2 * LOCK_WINDOW)
        .values("email_key")
        .annotate(tries=Count("pk"))
        .filter(tries__gte=LOCK_AFTER_FAILURES)
        .values_list("email_key", flat=True)
    )


def locked_until(email: str) -> datetime | None:
    """When this email's lock lifts by itself, or None if it isn't locked.

    An email locks when its last 5 failures all fall within 15 minutes, and
    stays locked for 15 minutes after the 5th (AC7). Tries while locked
    aren't counted, so the 5th is always the newest failure. "Now" is the
    database's clock, the same one that stamped the failures (G4 M7).
    """
    is_recent = ExpressionWrapper(
        Q(at__gt=Now() - LOCK_WINDOW), output_field=BooleanField()
    )
    newest_first = (
        LoginFailure.objects.filter(email_key=failure_key(email))
        .annotate(is_recent=is_recent)
        .order_by("-at")
        .values_list("at", "is_recent")
    )
    rows = list(newest_first[:LOCK_AFTER_FAILURES])
    if len(rows) < LOCK_AFTER_FAILURES:
        return None
    (fifth, fifth_is_recent), (first, _) = rows[0], rows[-1]
    if fifth - first > LOCK_WINDOW or not fifth_is_recent:
        return None
    return fifth + LOCK_WINDOW


def account_label(email: str) -> str:
    """The account id for a log line, or "unknown"; never the typed email."""
    found = User.objects.filter(username=email_key(email)).values_list("pk", flat=True)
    pk = found.first()
    return "unknown" if pk is None else str(pk)


@contextmanager
def one_try_at_a_time(email: str) -> Iterator[None]:
    """Let this email's login tries through one at a time (G4 M3).

    Without it, tries sent at the same moment could all pass the lock check
    before any of them was counted. The lock is PostgreSQL's, so it holds
    across gunicorn workers, and ends with the transaction.
    """
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s, hashtext(%s))",
            [LOGIN_TRY_LOCK, email_key(email)],
        )
        yield


def login_failed(email: str, address: str | None) -> None:
    """Count one wrong try. Never given the password."""
    LoginFailure.objects.create(email_key=failure_key(email), address=address)
    forget_old_failures()
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
    LoginFailure.objects.filter(email_key=failure_key(email)).delete()
    forget_old_failures()
    Session.objects.filter(expire_date__lt=Now()).delete()


def forget_old_failures() -> None:
    """Delete failures older than a day, at every login try (G4 M4).

    Also after wrong ones: with no good login, the table would only grow.
    """
    LoginFailure.objects.filter(at__lt=Now() - FAILURES_KEPT_FOR).delete()
