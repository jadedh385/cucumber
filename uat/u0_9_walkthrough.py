"""U0.9 G5 Owner walk-through: the reference-list services on staging.

There are no screens at U0.9, so the Admin's changes are made through the
services, from the running app's `manage.py shell` (design §9). The script is
piped in (the exact line is in the G5 note), with `SSH_USER` and
`SSH_CONNECTION` passed into the container, so every writer is called with
`via=ssh_via("manage.py shell")` and the trail says who ran it and from where.

Each step prints what the design expects and what the app did. Messages are
typed out here from design §7, not read from the app, so a wrong message shows.
The test codes (`ZTEST01`, `ZZZ`, `zz_test_tub`) cannot be deleted from a list
and the trail is append-only, so they stay; the script switches them off at the
end. Run it once: it stops if the test codes are already there.
"""

import sys
import uuid
from collections.abc import Callable
from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection

from cucumber.accounts.permissions import NotAllowed
from cucumber.core.audit import Reason, ssh_via
from cucumber.core.refusals import Refused
from cucumber.events.models import Event
from cucumber.events.services import NewBatch, NewEvent, correct, save_operation, split
from cucumber.plants.services import reclassify_genus
from cucumber.references.lists import ListName
from cucumber.references.reading import Item, active_items, item
from cucumber.references.services import add_item, edit_label, switch_off, switch_on

VIA = ssh_via("manage.py shell")
ADMIN_EMAIL = "admin@southeastcanopy.com"
TECH_EMAIL = "g5-sandbox-tech@example.com"
SWITCHED_OFF_EMAIL = "system@cucumber.invalid"
MEDIUM, GENUS, TUB = "ZTEST01", "ZZZ", "zz_test_tub"
NOTE = "U0.9 G5 walkthrough"
OFF = Reason("archive_no_longer_used", NOTE)
LONG = "x" * 101
SANDBOX_EVENTS = 13  # the events the seed scripts made: ids 1 to 13

STAGES, MEDIA, LOCATIONS = ListName.STAGES, ListName.MEDIA_CODES, ListName.LOCATIONS
GENERA, TUBS = ListName.GENERA, ListName.CONTAINER_TYPES
ACTIONS, UNITS = ListName.ACTIONS, ListName.COUNT_UNITS

# Design §7: the wording a person sees. Rules that share a message share a key.
SAYS = {
    "role_not_allowed": "Your role can't do this.",
    "account_not_active": "Your account is switched off. Nothing was saved.",
    "list_fixed": (
        "Event actions and count units can't be changed. That needs a release."
    ),
    "stages_order_fixed": (
        "Stages can't be added or moved in the order here. That needs a release."
    ),
    "locations_fixed": "Lab and Nursery are fixed. You can change their labels only.",
    "stages_active_needs_sort_order": (
        "A reserved stage can't be switched on here. That needs a release."
    ),
    "media_codes_code_format": (
        "A media code is a capital letter and 2 to 9 more capitals or digits,"
        " e.g. M001."
    ),
    "genera_code_format": "A genus code is 3 capital letters, e.g. PHL.",
    "genera_code_not_id_prefix": (
        "PLT, BAT and EVT start other IDs. Choose another genus code."
    ),
    "container_types_code_format": (
        "A container type code is small letters, digits and _, starting with a"
        " letter, e.g. magenta_box."
    ),
    "taken": "That code is already on the list.",
    "label": "Enter a label of up to 100 characters.",
    "genera_name_valid": "Enter a genus name of up to 100 characters.",
    "genera_name_unique": "Another genus already has that name.",
    "list_item_unknown": "That choice isn't on the list. Choose another.",
    "list_item_inactive": "That choice is switched off. Choose another.",
    "reason_required": "Choose a reason.",
    "reason_wrong_list": "That reason doesn't fit this change. Choose another.",
    "reason_note_too_long": "The note can be at most 500 characters.",
}

Attempt = Callable[[], object]
tally = {"match": 0, "differ": 0}


# ------------------------------------------------------------------ printing


def say(text: str) -> None:
    sys.stdout.write(text + "\n")


def step(title: str) -> None:
    say(f"\n### {title}\n")


def check(what: str, expected: object, got: object) -> None:
    """One line when the app did what the design says; both sides when not."""
    if expected == got:
        tally["match"] += 1
        say(f"- ✅ {what}: **{got}**")
        return
    tally["differ"] += 1
    say(f"- ❌ {what}: expected **{expected}**, got **{got}**")


def listed(name: ListName, code: str) -> Item:
    found = item(name, code)
    if found is None:
        raise SystemExit(f"{code} is not on the {name.value} list.")
    return found


# --------------------------------------------------------------- the audit trail


def audit_mark() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT coalesce(max(id), 0) FROM audit_log")
        row = cursor.fetchone()
    return int(row[0]) if row else 0


def audit_since(mark: int) -> list[str]:
    """The audit rows after `mark`: table, code, action, who, how, reason."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT a.table_name, a.row_pk, a.action, u.username, a.via,"
            " a.reason_code, a.note FROM audit_log a JOIN auth_user u"
            " ON u.id = a.actor_id WHERE a.id > %s ORDER BY a.id",
            [mark],
        )
        rows = cursor.fetchall()
    return [
        f"{table} {pk} {action} by {who} via '{via}'"
        + (f" reason {reason} note '{note}'" if reason else "")
        for table, pk, action, who, via, reason, note in rows
    ]


def expected_row(
    name: ListName, code: str, action: str, reason: Reason | None = None
) -> str:
    tail = f" reason {reason.code} note '{reason.note}'" if reason else ""
    return f"{name.value} {code} {action} by {ADMIN_EMAIL} via '{VIA}'{tail}"


def changes(
    what: str,
    name: ListName,
    code: str,
    action: str,
    attempt: Attempt,
    reason: Reason | None = None,
) -> None:
    """A change goes through and leaves exactly one audit row (AC19, AC20)."""
    mark = audit_mark()
    attempt()
    check(what, [expected_row(name, code, action, reason)], audit_since(mark))


def refuses(what: str, rule: str, attempt: Attempt, says: str | None = None) -> None:
    """A refusal has the design's message and writes nothing (AC21)."""
    mark, events = audit_mark(), Event.objects.count()
    try:
        attempt()
    except (Refused, NotAllowed) as refusal:
        got = f"{refusal.rule}: {refusal.message}"
    else:
        got = "saved, not refused"
    written = audit_mark() != mark or Event.objects.count() != events
    got += " [SOMETHING WRITTEN]" if written else " [nothing written]"
    check(what, f"{rule}: {SAYS[says or rule]} [nothing written]", got)


# ----------------------------------------------------------------- the writers


def add(by: User, name: ListName, code: str, label: str) -> Attempt:
    return lambda: add_item(by, name, code, label, via=VIA)


def relabel(by: User, name: ListName, code: str, label: str) -> Attempt:
    return lambda: edit_label(by, name, code, label, via=VIA)


def off(by: User, name: ListName, code: str, reason: Reason | None = OFF) -> Attempt:
    return lambda: switch_off(by, name, code, reason, via=VIA)


def on(by: User, name: ListName, code: str) -> Attempt:
    return lambda: switch_on(by, name, code, via=VIA)


def writers(admin: User) -> None:
    step("1 · Each writer, on each list that allows it")
    adds(admin)
    relabels(admin)
    switches(admin)
    mark = audit_mark()
    switch_on(admin, MEDIA, MEDIUM, via=VIA)
    check("switching on what is already on writes no row", [], audit_since(mark))


def adds(admin: User) -> None:
    for what, name, code, label in [
        ("add a media code", MEDIA, MEDIUM, "UAT test medium"),
        ("add a genus", GENERA, GENUS, "UAT test genus"),
        ("add a container type", TUBS, TUB, "UAT test tub"),
    ]:
        changes(what, name, code, "insert", add(admin, name, code, label))


def relabels(admin: User) -> None:
    """Stage and location labels are changed and put back."""
    stage_label = listed(STAGES, "P4").label
    lab_label = listed(LOCATIONS, "lab").label
    for name, code, label in [
        (STAGES, "P4", f"{stage_label} (UAT)"),
        (STAGES, "P4", stage_label),
        (LOCATIONS, "lab", f"{lab_label} (UAT)"),
        (LOCATIONS, "lab", lab_label),
        (MEDIA, MEDIUM, "UAT test medium 2"),
        (GENERA, GENUS, "UAT test genus 2"),
        (TUBS, TUB, "UAT test tub 2"),
    ]:
        what = f"label of {name.value} {code} to '{label}'"
        changes(what, name, code, "update", relabel(admin, name, code, label))


def switches(admin: User) -> None:
    """Off with an archive reason, then on, on the four lists that allow it."""
    for name, code in [(STAGES, "P4"), (MEDIA, MEDIUM), (GENERA, GENUS), (TUBS, TUB)]:
        what = f"{name.value} {code}"
        changes(f"switch off {what}", name, code, "update", off(admin, name, code), OFF)
        changes(f"switch on {what}", name, code, "update", on(admin, name, code))


# ---------------------------------------------------------------- the refusals


def refusals(admin: User, tech: User, switched_off: User) -> None:
    step("2 · Each refusal of design §7, with its message")
    refuses(
        "a Tech adds a media code", "role_not_allowed", add(tech, MEDIA, "ZTEST02", "x")
    )
    refuses(
        "a Tech edits a label", "role_not_allowed", relabel(tech, MEDIA, MEDIUM, "x")
    )
    refuses("a Tech switches off", "role_not_allowed", off(tech, MEDIA, MEDIUM))
    refuses("a Tech switches on", "role_not_allowed", on(tech, MEDIA, MEDIUM))
    refuses(
        "an account that is switched off",
        "account_not_active",
        add(switched_off, MEDIA, "ZTEST02", "x"),
    )
    refuses("add to event actions", "list_fixed", add(admin, ACTIONS, "ABC", "x"))
    refuses("relabel a count unit", "list_fixed", relabel(admin, UNITS, "mg", "x"))
    refuses("switch off an action", "list_fixed", off(admin, ACTIONS, "intake"))
    refuses("add a stage", "stages_order_fixed", add(admin, STAGES, "S9", "x"))
    refuses("add a location", "locations_fixed", add(admin, LOCATIONS, "farm", "x"))
    refuses("switch off Lab", "locations_fixed", off(admin, LOCATIONS, "lab"))
    refuses("switch on Nursery", "locations_fixed", on(admin, LOCATIONS, "nursery"))
    bad_codes(admin)
    taken_codes(admin)
    bad_labels(admin)
    bad_reasons(admin)
    other_rules(admin)


def bad_codes(admin: User) -> None:
    refuses(
        "media code in small letters",
        "media_codes_code_format",
        add(admin, MEDIA, "m001", "x"),
    )
    refuses(
        "media code too short", "media_codes_code_format", add(admin, MEDIA, "M", "x")
    )
    refuses(
        "genus code in small letters",
        "genera_code_format",
        add(admin, GENERA, "phl", "x"),
    )
    refuses(
        "genus code of two letters", "genera_code_format", add(admin, GENERA, "PH", "x")
    )
    refuses(
        "genus code that starts IDs",
        "genera_code_not_id_prefix",
        add(admin, GENERA, "PLT", "x"),
    )
    refuses(
        "container code with a space",
        "container_types_code_format",
        add(admin, TUBS, "Magenta Box", "x"),
    )
    refuses(
        "container code starting with a digit",
        "container_types_code_format",
        add(admin, TUBS, "4jar", "x"),
    )


def taken_codes(admin: User) -> None:
    refuses(
        "media code taken (M001)",
        "media_codes_pkey",
        add(admin, MEDIA, "M001", "x"),
        "taken",
    )
    refuses(
        "genus code taken (PHL)", "genera_pkey", add(admin, GENERA, "PHL", "x"), "taken"
    )
    refuses(
        "container code taken (jar)",
        "container_types_pkey",
        add(admin, TUBS, "jar", "x"),
        "taken",
    )


def bad_labels(admin: User) -> None:
    refuses(
        "blank media label",
        "media_codes_label_valid",
        relabel(admin, MEDIA, MEDIUM, "   "),
        "label",
    )
    refuses(
        "101-character stage label",
        "stages_label_valid",
        relabel(admin, STAGES, "P4", LONG),
        "label",
    )
    refuses(
        "blank location label",
        "locations_label_valid",
        relabel(admin, LOCATIONS, "lab", ""),
        "label",
    )
    refuses("blank genus name", "genera_name_valid", relabel(admin, GENERA, GENUS, " "))
    refuses(
        "101-character container label",
        "container_types_label_valid",
        relabel(admin, TUBS, TUB, LONG),
        "label",
    )
    refuses(
        "add with a blank label",
        "container_types_label_valid",
        add(admin, TUBS, "zz_blank", ""),
        "label",
    )


def bad_reasons(admin: User) -> None:
    refuses(
        "switch off with no reason", "reason_required", off(admin, MEDIA, MEDIUM, None)
    )
    refuses(
        "switch off, reason from another list",
        "reason_wrong_list",
        off(admin, MEDIA, MEDIUM, Reason("void_other")),
    )
    refuses(
        "switch off, 501-character note",
        "reason_note_too_long",
        off(admin, MEDIA, MEDIUM, Reason("archive_other", "x" * 501)),
    )


def other_rules(admin: User) -> None:
    refuses(
        "relabel a code that is not on the list",
        "list_item_unknown",
        relabel(admin, MEDIA, "ZNOPE9", "x"),
    )
    refuses(
        "switch on a reserved stage (P3)",
        "stages_active_needs_sort_order",
        on(admin, STAGES, "P3"),
    )
    refuses(
        "rename a genus to another's name",
        "genera_name_unique",
        relabel(admin, GENERA, GENUS, "Philodendron"),
    )
    refuses(
        "add a genus with another's name",
        "genera_name_unique",
        add(admin, GENERA, "ZZY", "Hoya"),
    )


# --------------------------------------------------------------------- M004


def old_events() -> list[tuple[object, ...]]:
    """The sandbox events as stored: they are never rewritten."""
    return list(
        Event.objects.filter(pk__lte=SANDBOX_EVENTS)
        .order_by("pk")
        .values_list(
            "id", "batch_id", "action", "qty_in", "qty_out", "media_code", "stage_to"
        )
    )


def new_intake(tech: User, plant_id: int) -> Attempt:
    batch = NewBatch(plant_id=plant_id, origin="intake", location_code="lab")
    entry = NewEvent(
        "intake", new_batch=batch, qty_in=1, stage_to="P1", media_code="M004"
    )
    return lambda: save_operation(uuid.uuid4(), tech, [entry])


def projections_ok() -> str:
    try:
        call_command("check_projections", stdout=StringIO())
    except Exception as failure:  # the command raises when a batch's count differs
        return f"FAILED: {failure}"
    return "ok"


def media_m004(admin: User, tech: User) -> None:
    step("3 · Switch M004 off: new saves refused, old records and fixes go on")
    before = old_events()
    changes(
        "switch off M004 with an archive reason",
        MEDIA,
        "M004",
        "update",
        off(admin, MEDIA, "M004"),
        OFF,
    )
    check(
        "M004 is not in the dropdown",
        False,
        "M004" in [i.code for i in active_items(MEDIA)],
    )
    found = listed(MEDIA, "M004")
    check("M004 still reads, switched off", ("M004", False), (found.code, found.active))
    refuses("a new save picking M004", "list_item_inactive", new_intake(tech, 1))
    split(uuid.uuid4(), tech, 5, 1, f"{NOTE}: split of a batch on M004")
    later = Event.objects.filter(pk__gt=SANDBOX_EVENTS, action__in=["split", "intake"])
    check("a split of the batch on M004 (batch 5) works", 2, later.count())
    original = Event.objects.get(pk=9)
    correct(
        admin,
        9,
        "correction_wrong_media_code",
        media_code="M004",
        occurred_at=original.occurred_at - timedelta(minutes=1),
        note=NOTE,
    )
    check(
        "a Correction that restates M004 works",
        1,
        Event.objects.filter(corrects_event_id=9).count(),
    )
    check("the old events read the same", True, old_events() == before)
    check("every batch's count still matches its events", "ok", projections_ok())
    changes("switch M004 back on", MEDIA, "M004", "update", on(admin, MEDIA, "M004"))
    new_intake(tech, 1)()
    picked = Event.objects.filter(media_code="M004", pk__gt=SANDBOX_EVENTS)
    check("a new save picking M004 works again", True, picked.exists())


def genus_off(admin: User) -> None:
    step("4 · Reclassify a plant to a switched-off genus")
    changes(
        "switch off the test genus",
        GENERA,
        GENUS,
        "update",
        off(admin, GENERA, GENUS),
        OFF,
    )
    refuses(
        "reclassify plant 1 to it",
        "list_item_inactive",
        lambda: reclassify_genus(admin, 1, GENUS),
    )


def tidy(admin: User) -> None:
    step("5 · Switch the test codes off, so no dropdown offers them")
    changes(
        "switch off the test medium",
        MEDIA,
        MEDIUM,
        "update",
        off(admin, MEDIA, MEDIUM),
        OFF,
    )
    changes(
        "switch off the test container type",
        TUBS,
        TUB,
        "update",
        off(admin, TUBS, TUB),
        OFF,
    )


def leftovers(start: int) -> None:
    step("What this left on staging")
    for line in audit_since(start):
        say(f"- audit: {line}")
    later = Event.objects.filter(pk__gt=SANDBOX_EVENTS).count()
    say(f"- events after the sandbox: {later}")
    say(f"\n**{tally['match']} matched, {tally['differ']} differed.**")


def main() -> None:
    admin = User.objects.get(username=ADMIN_EMAIL)
    tech = User.objects.get(username=TECH_EMAIL)
    switched_off = User.objects.get(username=SWITCHED_OFF_EMAIL)
    if item(MEDIA, MEDIUM) is not None:
        raise SystemExit(f"{MEDIUM} is already on the list: this was run before.")
    say(f"Run by {VIA}\nDatabase user: {connection.settings_dict['USER']}")
    start = audit_mark()
    writers(admin)
    refusals(admin, tech, switched_off)
    media_m004(admin, tech)
    genus_off(admin)
    tidy(admin)
    leftovers(start)


main()
