"""U0.2b Owner walk-through: the event core against the SOP (G5).

A Lab story run straight through the event services (there are no screens
yet). Each step says what the SOP expects and what the app did. Run it with
`uat/u0_2b.sh`, which gives it a fresh throwaway database, `cucumber_uat`.
"""

import os
import sys
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cucumber.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import User  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.utils import timezone  # noqa: E402

from cucumber.accounts.permissions import NotAllowed, Role  # noqa: E402
from cucumber.accounts.services import replace_role  # noqa: E402
from cucumber.batches.models import Batch  # noqa: E402
from cucumber.core.audit import SYSTEM, audited  # noqa: E402
from cucumber.core.refusals import Refused  # noqa: E402
from cucumber.core.tests.rows import give_sku, make_plant  # noqa: E402
from cucumber.events.models import Event  # noqa: E402
from cucumber.events.reviews import review, review_queue  # noqa: E402
from cucumber.events.services import (  # noqa: E402
    NewBatch,
    NewEvent,
    Saved,
    close,
    correct,
    count_difference,
    save_operation,
    split,
    void,
)
from cucumber.ids.lookup import find_by_sku  # noqa: E402
from cucumber.plants.services import reclassify_genus  # noqa: E402

UAT_VIA = "uat"  # shows in the audit trail as how these rows were made
THREE_DAYS_AGO = timedelta(days=3)
TWO_DAYS_AGO = timedelta(days=2)

tally = {"match": 0, "differ": 0}


# ------------------------------------------------------------------ printing


def say(text: str) -> None:
    sys.stdout.write(text + "\n")


def step(title: str, meaning: str) -> None:
    say(f"\n### {title}\n\n*What this shows:* {meaning}\n")


def check(what: str, expected: object, got: object) -> None:
    matches = expected == got
    tally["match" if matches else "differ"] += 1
    mark = "✅" if matches else "❌"
    say(f"- {mark} {what}: SOP expects **{expected}**, app gives **{got}**")


def check_refused(what: str, message: str, attempt: Callable[[], object]) -> None:
    try:
        attempt()
    except (Refused, NotAllowed) as refusal:
        check(what, f'refused: "{message}"', f'refused: "{refusal.message}"')
        return
    check(what, f'refused: "{message}"', "saved, not refused")


# ------------------------------------------------------------------ helpers


def staff(name: str, role: str) -> User:
    # The user name is the email (U0.5's auth_user rule).
    email = f"{name.lower().replace('_', '-')}@example.com"
    # Every audited write names a person (U0.7): set-up is made by System.
    with audited(SYSTEM, via=UAT_VIA):
        user, _ = User.objects.get_or_create(username=email, defaults={"email": email})
        replace_role(user, Role(role))
    return user


def save(by: User, *entries: NewEvent) -> Saved:
    return save_operation(uuid.uuid4(), by, entries)


def log(by: User, entry: NewEvent) -> int:
    """Save one entry on its own; returns the event's id."""
    return save(by, entry).event_ids[0]


def units(batch: int) -> int:
    return Batch.objects.get(pk=batch).live_count


def stage(batch: int) -> str | None:
    return Batch.objects.get(pk=batch).stage_id


def status(batch: int) -> str:
    return Batch.objects.get(pk=batch).status


def queued(user: User) -> set[int]:
    return {event for item in review_queue(user) for event in item.event_ids}


def voids_queued(user: User) -> bool:
    return Event.objects.filter(pk__in=queued(user), action="void").exists()


# -------------------------------------------------------------------- story


class Story:
    """The people, the plant and the batches the steps share."""

    def __init__(self) -> None:
        self.tech = staff("tech_a", "tech")
        self.supervisor = staff("supervisor", "supervisor")
        self.admin = staff("admin", "admin")
        self.plant = make_plant(self.admin.pk, full_name="Pink Princess")
        self.parent = self.child_1 = self.child_2 = self.split_off = 0
        self.count_event = self.late_loss = self.split_event = 0
        self.first_subculture = 0

    def child_of(self, parent: int) -> NewEvent:
        """An intake making one child batch of 8 at P2, from a subculture."""
        new = NewBatch(
            plant_id=self.plant,
            origin="subculture",
            location_code="lab",
            parent_batch_id=parent,
        )
        return NewEvent(
            "intake", new_batch=new, qty_in=8, stage_to="P2", media_code="M002"
        )

    def lab_batch(self) -> None:
        step(
            "SOP-3 · Start a lab batch, 3 days ago (Tech)",
            "a new Lab batch starts with its explant count and its stage.",
        )
        new = NewBatch(plant_id=self.plant, origin="intake", location_code="lab")
        entry = NewEvent(
            "intake",
            new_batch=new,
            qty_in=20,
            stage_to="P0",
            media_code="M001",
            occurred_at=timezone.now() - THREE_DAYS_AGO,
        )
        self.parent = save(self.tech, entry).batch_ids[0]
        check("Units in the new Lab batch", 20, units(self.parent))
        check("Its stage", "P0", stage(self.parent))

        step("SOP-5 · Stage change P0 → P1 (Tech)", "the batch's stage follows.")
        log(self.tech, NewEvent("stage_change", batch_id=self.parent, stage_to="P1"))
        check("Stage after the change", "P1", stage(self.parent))

    def subculture(self) -> None:
        step(
            "SOP-4 · Subculture: 6 jars used, 2 child batches of 8 at P2 (Tech)",
            "one save takes units from the parent and makes the children.",
        )
        used = NewEvent(
            "subculture", batch_id=self.parent, qty_out=6, media_code="M002"
        )
        made = self.child_of(self.parent)
        saved = save(self.tech, used, made, made)
        self.first_subculture = saved.event_ids[0]
        self.child_1, self.child_2 = saved.batch_ids
        check("Parent after using 6 jars", 14, units(self.parent))
        check("Each child batch", [8, 8], [units(self.child_1), units(self.child_2)])
        parents = {
            Batch.objects.get(pk=batch).parent_batch_id
            for batch in (self.child_1, self.child_2)
        }
        check("Children point at their parent", {self.parent}, parents)

        step(
            "SOP-4 · Contamination thrown away: 2 jars (Tech)",
            "contaminated units leave the batch.",
        )
        log(self.tech, NewEvent("contamination", batch_id=self.parent, qty_out=2))
        check("Parent after contamination", 12, units(self.parent))

    def loss(
        self, qty: int, reason: str | None, occurred_at: datetime | None = None
    ) -> int:
        """Log a loss on the parent batch as the Tech."""
        entry = NewEvent(
            "loss",
            batch_id=self.parent,
            qty_out=qty,
            reason_code=reason,
            occurred_at=occurred_at,
        )
        return log(self.tech, entry)

    def loss_and_count(self) -> None:
        step(
            "SOP-11 · Record a loss (Tech)",
            "a loss needs a reason, and nothing can go below zero.",
        )
        check_refused(
            "A loss with no reason", "Choose a reason.", lambda: self.loss(1, None)
        )
        self.loss(1, "loss_pest")
        check("Parent after a loss of 1 (pests)", 11, units(self.parent))
        check_refused(
            "Taking 50 from a batch of 11",
            "This would take the batch below zero. Check the numbers.",
            lambda: self.loss(50, "loss_rot"),
        )

        step(
            "SOP-6 · Count: the count wins (Tech)",
            "a count sets the total; the gap is kept as the count's difference, "
            "and an entry found later explains it instead of changing the total.",
        )
        count = NewEvent("count", batch_id=self.parent, counted_qty=10)
        self.count_event = log(self.tech, count)
        check("Total after counting 10 (1 jar unexplained)", 10, units(self.parent))
        check("The count's difference", -1, count_difference(self.count_event))
        self.late_loss = self.loss(
            1, "loss_rot", occurred_at=timezone.now() - TWO_DAYS_AGO
        )
        check("A loss dated 2 days back: total stays", 10, units(self.parent))
        difference = count_difference(self.count_event)
        check("…and the difference is now explained", 0, difference)

    def split_and_close(self) -> None:
        step(
            "SOP-12 · Split (Tech)",
            "units move to a new batch at the same place and stage, with a why.",
        )
        check_refused(
            "A split with no note",
            "Say why these units are split off.",
            lambda: split(uuid.uuid4(), self.tech, self.child_2, 3, ""),
        )
        saved = split(uuid.uuid4(), self.tech, self.child_2, 3, "pre-order")
        self.split_off = saved.batch_ids[0]
        self.split_event = saved.event_ids[0]
        new = Batch.objects.get(pk=self.split_off)
        check("Original after splitting off 3", 5, units(self.child_2))
        check(
            "New batch: place, stage, units",
            ("lab", "P2", 3),
            (new.location_id, new.stage_id, new.live_count),
        )

        step(
            "SOP-13 · Close a batch (Tech)",
            "only an empty batch closes, and a closed batch takes nothing new.",
        )
        batch = split(uuid.uuid4(), self.tech, self.child_1, 2, "new media").batch_ids[
            0
        ]
        check_refused(
            "Closing a batch that still has 2",
            "A batch can only be closed or voided when it has 0 units.",
            lambda: close(uuid.uuid4(), self.tech, batch),
        )
        empty = NewEvent("loss", batch_id=batch, qty_out=2, reason_code="loss_damage")
        log(self.tech, empty)
        closed = close(uuid.uuid4(), self.tech, batch).event_ids[0]
        check("Status after Close at 0", "closed", status(batch))
        check_refused(
            "Adding stock to the closed batch",
            "This batch is closed. Only voiding its Close can be logged on it.",
            lambda: log(self.tech, NewEvent("intake", batch_id=batch, qty_in=1)),
        )
        void(self.supervisor, closed, "void_other", note="closed too early")
        check("Voiding the Close reopens it (SOP-10)", "open", status(batch))

    def fixes(self) -> None:
        step(
            "SOP-10 · Fix mistakes",
            "a Void undoes a whole action; a Correction restates numbers, on "
            "both batches for a split; neither can change what an entry is.",
        )
        used = NewEvent(
            "subculture", batch_id=self.parent, qty_out=2, media_code="M002"
        )
        duplicate = save(self.tech, used, self.child_of(self.parent))
        check("A second subculture by mistake: parent", 8, units(self.parent))
        void(self.tech, duplicate.event_ids[1], "void_duplicate_entry")
        check("Voiding one of its entries: parent back to", 10, units(self.parent))
        check("…and the child it made", "voided", status(duplicate.batch_ids[0]))
        try:
            void(self.tech, self.first_subculture, "void_wrong_batch")
            got = "saved, not refused"
        except Refused as refusal:
            got = f"refused, {len(refusal.event_ids)} later entries listed"
        check(
            "Voiding the first subculture, whose children have later entries",
            "refused, 2 later entries listed",
            got,
        )
        correct(
            self.supervisor, self.split_event, "correction_wrong_quantity", qty_out=2
        )
        check(
            "Correcting the split 3 → 2: both batches",
            (6, 2),
            (units(self.child_2), units(self.split_off)),
        )
        pest = Event.objects.get(batch_id=self.parent, reason_id="loss_pest").pk
        check_refused(
            "A correction that turns a loss into a gain",
            "A correction can't change what kind of entry this is."
            " Void it and log the right entry instead.",
            lambda: correct(
                self.supervisor,
                pest,
                "correction_wrong_quantity",
                qty_in=50,
                qty_out=0,
            ),
        )

    def reviews(self) -> None:
        step(
            "Entering work for someone else (Supervisor saves the Tech's loss)",
            "both people are kept, and neither of them may review it.",
        )
        entry = NewEvent(
            "loss",
            batch_id=self.child_1,
            qty_out=1,
            reason_code="loss_rot",
            staff_id=self.tech.pk,
        )
        for_tech = log(self.supervisor, entry)
        event = Event.objects.get(pk=for_tech)
        check(
            "Did it / saved it",
            ("tech-a@example.com", "supervisor@example.com"),
            (event.staff.username, event.recorded_by.username),
        )
        check("In the Supervisor's queue", False, for_tech in queued(self.supervisor))
        check("In the Admin's queue", True, for_tech in queued(self.admin))

        step(
            "SOP-7 · Review",
            "who reviews what, the 'entered late' flag, and that a review "
            "can't be done twice.",
        )
        late = any(
            "entered_late" in item.flags
            for item in review_queue(self.supervisor)
            if self.late_loss in item.event_ids
        )
        check("The loss logged 2 days late is flagged", True, late)
        check(
            "The split, which the Supervisor corrected, still waiting",
            False,
            self.split_event in queued(self.supervisor),
        )
        check("Voids in the Supervisor's queue", False, voids_queued(self.supervisor))
        check("Voids in the Admin's queue", True, voids_queued(self.admin))
        first = review_queue(self.supervisor)[0].operation_id
        review(self.supervisor, first, note="checked on the bench")
        waiting = {item.operation_id for item in review_queue(self.supervisor)}
        check("Reviewed item still in the queue", False, first in waiting)
        check_refused(
            "Reviewing it again",
            "This entry has already been reviewed.",
            lambda: review(self.supervisor, first),
        )
        check_refused(
            "A Tech trying to review",
            "Your role can't do this.",
            lambda: review(self.tech, review_queue(self.admin)[0].operation_id),
        )
        own = NewEvent("loss", batch_id=self.child_1, qty_out=1, reason_code="loss_rot")
        own_id = log(self.admin, own)
        check("The Admin's own entry waiting", False, own_id in queued(self.admin))

    def reclassify(self) -> None:
        step(
            "Genus reclassification (Admin)",
            "only the Admin moves a plant to another genus; it gets a new SKU "
            "and the old one still finds it.",
        )
        give_sku(self.plant, "PHL001", self.admin.pk)
        check_refused(
            "By the Supervisor",
            "Your role can't do this.",
            lambda: reclassify_genus(self.supervisor, self.plant, "ALC"),
        )
        moved = reclassify_genus(self.admin, self.plant, "ALC")
        check("New genus and SKU", ("ALC", "ALC001"), (moved.genus_id, moved.sku_id))
        found = find_by_sku("PHL001")
        check("Search for PHL001 finds it", self.plant, found.pk if found else None)

    def nightly_check(self) -> None:
        step(
            "Nightly check (check_projections)",
            "every batch's stored numbers agree with its entries.",
        )
        output = StringIO()
        call_command("check_projections", stdout=output)
        check("Every batch matches", True, "match their events" in output.getvalue())


def main() -> None:
    say("# U0.2b walk-through: the event core against the SOP\n")
    say("People: **Tech**, **Supervisor**, **Admin**. Plant: PHL Pink Princess.")
    story = Story()
    story.lab_batch()
    story.subculture()
    story.loss_and_count()
    story.split_and_close()
    story.fixes()
    story.reviews()
    story.reclassify()
    story.nightly_check()
    matched, differ = tally["match"], tally["differ"]
    say(f"\n**Result: {matched} checks match the SOP, {differ} don't.**")
    sys.exit(1 if tally["differ"] else 0)


if __name__ == "__main__":
    main()
