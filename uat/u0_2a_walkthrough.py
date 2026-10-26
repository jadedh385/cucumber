"""U0.2a Owner walk-through: the schema against SOP §5 (G5).

U0.2a is the database itself, so this walk-through skips the services and
writes rows with plain SQL as `cucumber_app`, the user the running app logs
in as. That is spec story S1: bad data can't get in "even through the Django
admin or raw SQL". A few steps also try as the table owner, `cucumber_owner`,
to show the triggers stop it too.

Each step names the rule that refuses the row (design §7.1) and the message
staff would see. Run it with `uat/u0_2a.sh`, which gives it a fresh throwaway
database, `cucumber_uat`.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cucumber.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from u0_2a_rows import NOT_ALLOWED, SAVED, App, Story, as_owner, refused  # noqa: E402

from cucumber.plants.services import zoho_link_missing  # noqa: E402

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
    say(f"- {mark} {what}: expected **{expected}**, database gives **{got}**")


# -------------------------------------------------------------------- steps


def names(s: Story) -> None:
    step(
        "Rules 12 and 13 · Plant names",
        "a plant needs a readable name, and no two plants in a genus share one,"
        " even when typed with other capitals or spaces. Retired plants keep"
        " their name; voided ones free it.",
    )
    check(
        "Register Philodendron 'Pink Princess' (gift)",
        SAVED,
        s.add_plant("Pink Princess"),
    )
    check(
        "'pink princess' in the same genus",
        refused("plant_name_unique_in_genus"),
        s.add_plant("pink princess"),
    )
    check(
        "'Pink  Princess' (two spaces)",
        refused("plant_name_unique_in_genus"),
        s.add_plant("Pink  Princess"),
    )
    check(
        "'Pink Princess' as a Hoya (another genus)",
        SAVED,
        s.add_plant("Pink Princess", genus_code="HYA"),
    )
    check(
        "A plant named 'Philodendron ???'",
        refused("plant_name_valid"),
        s.add_plant("Philodendron ???"),
    )
    check("A blank name", refused("plant_name_valid"), s.add_plant("  "))
    s.add_plant("Birkin")
    s.app.update("plants", s.plant("Birkin"), {"status": "retired"})
    check(
        "A new 'Birkin' while the old one is Retired",
        refused("plant_name_unique_in_genus"),
        s.add_plant("Birkin"),
    )
    s.add_plant("Micans")
    s.app.update("plants", s.plant("Micans"), {"status": "voided"}, reason="void_other")
    check("A new 'Micans' after the old one was Voided", SAVED, s.add_plant("Micans"))


def zoho_link(s: Story) -> None:
    step(
        "Rule 4 · Purchased plants and the Zoho link",
        "a purchase can be registered before Zoho has it, and is listed until"
        " the vendor and Zoho reference are added; it can't be sold (Portfolio)"
        " without them. Gifts and propagated plants have neither.",
    )
    check(
        "Register a purchase with no vendor or Zoho ref",
        SAVED,
        s.add_plant("Gloriosum", source="purchase"),
    )
    plant = s.plant("Gloriosum")
    listed = any(p.pk == plant for p in zoho_link_missing())
    check("It is on the 'Zoho link missing' list", True, listed)
    s.give_sku(plant, "PHL010")
    check(
        "Moving it to Portfolio without the link",
        refused("plant_portfolio_needs_zoho_link"),
        s.app.update("plants", plant, {"status": "portfolio"}),
    )
    s.app.insert(
        "vendors",
        {
            "zoho_contact_id": "ZC-1",
            "name": "Green Leaf Co.",
            "active": True,
            "synced_at": s.now(),
        },
    )
    s.app.update("plants", plant, {"vendor_id": "ZC-1", "zoho_ref": "EXP-0001"})
    check(
        "…with vendor and Zoho ref added, to Portfolio",
        SAVED,
        s.app.update("plants", plant, {"status": "portfolio"}),
    )
    check(
        "A gift with a Zoho ref",
        refused("plant_vendor_only_if_purchased"),
        s.add_plant("Melanochrysum", zoho_ref="EXP-0002"),
    )


def skus(s: Story) -> None:
    step(
        "Rule 1 · SKUs",
        "a Portfolio plant has an SKU; an SKU is issued once, to one plant, starts"
        " with the plant's genus, and never changes unless the genus does.",
    )
    plant = s.plant("Pink Princess")
    check(
        "Pink Princess to Portfolio with no SKU",
        refused("plant_portfolio_needs_sku"),
        s.app.update("plants", plant, {"status": "portfolio"}),
    )
    check("Give it PHL001", SAVED, s.give_sku(plant, "PHL001"))
    check(
        "…then to Portfolio",
        SAVED,
        s.app.update("plants", plant, {"status": "portfolio"}),
    )
    other = s.plant("Gloriosum")
    check(
        "Issue PHL001 again, to another plant",
        refused("skus_pkey"),
        s.issue_sku(other, "PHL001"),
    )
    check(
        "Point another plant at PHL001",
        refused("plant_sku_unique"),
        s.app.update("plants", s.plant("Micans"), {"sku": "PHL001"}),
    )
    check(
        "An SKU 'PHL01'",
        refused("plant_sku_format"),
        s.app.update("plants", s.plant("Micans"), {"sku": "PHL01"}),
    )
    s.issue_sku(s.plant("Micans"), "HYA001", genus="HYA")
    check(
        "SKU HYA001 on a Philodendron",
        refused("plant_sku_matches_genus"),
        s.app.update("plants", s.plant("Micans"), {"sku": "HYA001"}),
    )
    check(
        "Clearing Pink Princess's SKU",
        refused("plant_sku_static"),
        s.app.update("plants", plant, {"sku": None}),
    )
    s.issue_sku(plant, "PHL002")
    check(
        "Changing it to PHL002, same genus",
        refused("plant_sku_static"),
        s.app.update("plants", plant, {"sku": "PHL002"}),
    )


def batches(s: Story) -> None:
    step(
        "Rules 5, 6, 7, 11 · Batches",
        "a batch made from another batch points at its parent, of the same"
        " plant; every Lab batch has a stage; a count never goes below zero;"
        " only a quarantine batch can be quarantined.",
    )
    plant, other = s.plant("Pink Princess"), s.plant("Gloriosum")
    check(
        "Lab batch at P0 (intake)",
        SAVED,
        s.add_batch(plant, location_code="lab", stage_code="P0"),
    )
    parent = s.last_batch()
    check(
        "Lab batch with no stage",
        refused("batch_lab_needs_stage"),
        s.add_batch(plant, location_code="lab"),
    )
    check("Nursery batch with no stage", SAVED, s.add_batch(plant))
    check(
        "Subculture batch with no parent",
        refused("batch_needs_parent"),
        s.add_batch(plant, origin="subculture", location_code="lab", stage_code="P1"),
    )
    check(
        "Subculture batch of Gloriosum under a Pink Princess parent",
        refused("batch_parent_same_plant"),
        s.add_batch(
            other,
            origin="subculture",
            parent_batch_id=parent,
            location_code="lab",
            stage_code="P1",
        ),
    )
    check(
        "A batch as its own parent",
        refused("batch_not_own_parent"),
        s.app.update("batches", parent, {"parent_batch_id": parent}),
    )
    s.app.update("batches", parent, {"live_count": 3})
    check(
        "Batch count set to −1",
        refused("batch_count_not_negative"),
        s.app.update("batches", parent, {"live_count": -1}),
    )
    check(
        "An intake batch marked quarantined",
        refused("batch_quarantine_origin"),
        s.add_batch(plant, quarantined=True),
    )
    check(
        "A second open Nursery batch of the same plant (Q7)", SAVED, s.add_batch(plant)
    )


def events(s: Story) -> None:
    step(
        "Rules 7 and 8 · Entries (events)",
        "quantities are never negative; a loss, Void or Correction needs a"
        " reason; an entry is voided once; dates are at most 7 Bangkok days"
        " back and never in the future, except a Correction restating an old date.",
    )
    batch = s.plant_batch("Pink Princess")
    check("Count of 5", SAVED, s.add_event(batch, "count", counted_qty=5))
    original = s.last_event()
    check(
        "A loss of −2 (plain SQL: the loss's shape rule answers first)",
        refused("event_loss_shape"),
        s.add_event(batch, "loss", qty_out=-2, reason_code=s.reason("loss")),
    )
    check(
        "…the same loss saved through the app (found at this G5, fixed)",
        refused("event_qty_not_negative"),
        s.save_loss(batch, -2),
    )
    check(
        "A Correction to −1",
        refused("event_qty_not_negative"),
        s.add_event(
            batch,
            "correction",
            corrects_event_id=original,
            counted_qty=5,
            qty_out=-1,
            reason_code=s.reason("correction"),
        ),
    )
    check(
        "A count of −1",
        refused("event_counted_not_negative"),
        s.add_event(batch, "count", counted_qty=-1),
    )
    check(
        "A loss with no reason",
        refused("event_reason_required"),
        s.add_event(batch, "loss", qty_out=1),
    )
    check(
        "A Void with no reason",
        refused("event_reason_required"),
        s.add_event(batch, "void", voids_event_id=original),
    )
    check(
        "A Void with a reason",
        SAVED,
        s.add_event(
            batch, "void", voids_event_id=original, reason_code=s.reason("void")
        ),
    )
    check(
        "Voiding the same entry again",
        refused("event_void_once"),
        s.add_event(
            batch, "void", voids_event_id=original, reason_code=s.reason("void")
        ),
    )
    check(
        "A count dated 8 days ago",
        refused("event_within_7_days"),
        s.add_event(batch, "count", counted_qty=5, occurred_at=s.days_ago(8)),
    )
    check(
        "A count dated 7 days ago",
        SAVED,
        s.add_event(batch, "count", counted_qty=5, occurred_at=s.days_ago(7)),
    )
    check(
        "A count dated 1 hour ahead",
        refused("event_not_in_future"),
        s.add_event(batch, "count", counted_qty=5, occurred_at=s.hours_ahead(1)),
    )
    check(
        "A Correction restating a date 3 weeks back (Q5)",
        SAVED,
        s.add_event(
            batch,
            "correction",
            corrects_event_id=s.last_event(),
            counted_qty=5,
            reason_code=s.reason("correction"),
            occurred_at=s.days_ago(21),
        ),
    )
    check(
        "Saving the same form (operation) twice",
        refused("operations_pkey"),
        s.app.run(
            "INSERT INTO operations (id, recorded_by) SELECT id, recorded_by"
            " FROM operations LIMIT 1"
        ),
    )


def no_edits(s: Story) -> None:
    step(
        "Rules 2, 8, 9, 10 · Nothing is edited or deleted",
        "entries, reviews and status history can't be changed or deleted;"
        " plants and batches can't be deleted. The app isn't even allowed to"
        " try; the table owner tries and the database's triggers stop it.",
    )
    event = s.last_event()
    check("Review an entry", SAVED, s.review(event))
    check("Review it a second time", refused("event_review_once"), s.review(event))
    check(
        "App: change an entry",
        NOT_ALLOWED,
        s.app.run("UPDATE events SET note = 'x' WHERE id = %s", [event]),
    )
    check(
        "App: delete an entry",
        NOT_ALLOWED,
        s.app.run("DELETE FROM events WHERE id = %s", [event]),
    )
    check("App: delete a plant", NOT_ALLOWED, s.app.run("DELETE FROM plants"))
    check("App: delete a batch", NOT_ALLOWED, s.app.run("DELETE FROM batches"))
    check("App: empty the entries table", NOT_ALLOWED, s.app.run("TRUNCATE events"))
    check(
        "Owner: change an entry",
        refused("events_append_only"),
        as_owner("UPDATE events SET note = 'x' WHERE id = %s", [event]),
    )
    check(
        "Owner: delete a review",
        refused("event_reviews_append_only"),
        as_owner("DELETE FROM event_reviews"),
    )
    check(
        "Owner: delete a plant",
        refused("plants_no_delete"),
        as_owner("DELETE FROM plants"),
    )
    check(
        "Owner: delete a batch",
        refused("batches_no_delete"),
        as_owner("DELETE FROM batches"),
    )


def closing(s: Story) -> None:
    step(
        "Rule 9 · Closing and voiding batches",
        "a batch is closed or voided only at 0 units, and its closed / voided"
        " date goes with the status.",
    )
    batch = s.plant_batch("Pink Princess")
    check(
        "Close a batch holding 3",
        refused("batch_closed_needs_zero"),
        s.app.update("batches", batch, {"status": "closed", "closed_at": s.now()}),
    )
    s.app.update("batches", batch, {"live_count": 0})
    check(
        "Close it at 0",
        SAVED,
        s.app.update("batches", batch, {"status": "closed", "closed_at": s.now()}),
    )
    check(
        "Reopen it but keep the closed date",
        refused("batch_closed_at_matches"),
        s.app.update("batches", batch, {"status": "open"}),
    )


def lists(s: Story) -> None:
    step(
        "Reference lists (AC20, AC21)",
        "stages run S0, P0, P1, P2, A1, P4 (S0 from U0.9); a stage in use"
        " can't be renamed or deleted, only switched off.",
    )
    order = s.app.one(
        "SELECT string_agg(code, ' ' ORDER BY sort_order) FROM stages WHERE active"
    )
    check("Stage order", "S0 P0 P1 P2 A1 P4", order)
    check(
        "Rename stage P0 (in use)",
        refused("stages_code_rename"),
        s.app.run("UPDATE stages SET code = 'PX' WHERE code = 'P0'"),
    )
    check(
        "App: delete stage P0",
        NOT_ALLOWED,
        s.app.run("DELETE FROM stages WHERE code = 'P0'"),
    )
    check(
        "Owner: delete stage P0",
        refused("stages_no_delete"),
        as_owner("DELETE FROM stages WHERE code = 'P0'"),
    )
    check(
        "Switch stage P4 off",
        SAVED,
        s.app.run(
            "UPDATE stages SET active = false WHERE code = 'P4'",
            reason="archive_no_longer_used",
        ),
    )
    s.app.run("UPDATE stages SET active = true WHERE code = 'P4'")


def undo_guard() -> None:
    step(
        "Undoing the schema (G4 review H1)",
        "with real data in the database, a developer can't undo the migrations"
        " and drop the tables by mistake.",
    )
    # Going back to 0003 undoes core 0006 (the audit trail, U0.7) first, and
    # that migration refuses before the schema one (0004) is reached.
    try:
        call_command("migrate", "core", "0003", verbosity=0)
    except RuntimeError as error:
        got = "refused: " + str(error).split(":")[0]
    else:
        got = "undone"
    check(
        "Undo the last schema migration",
        "refused: Refusing to undo the audit trail",
        got,
    )


SERVICE_ONLY = """
### Rules the database can't hold alone

These have a written reason in design §5 and are checked by services
(U0.2b, U0.6, U1.x), not by the database:

- **Rule 2** who may promote, demote or retire (roles live in the app; U0.6).
- **Rule 3** a Candidate has no batches (needs the plant's status while
  saving a batch: a check across tables; U1.3).
- **Rule 8** Undo within 10 minutes of your own entry (needs the current user;
  U0.6 / U1.8). Voiding a whole operation at once: U0.2b, walked through there.
- **Rule 10** nobody reviews their own entry, except the Admin (roles; U0.2b
  walk-through).
- **Rule 11** quarantined stock left out of availability (a calculation; U5.2).
- The batch count following its entries (the projection; U0.2b), checked
  nightly by `check_projections`.
"""


def main() -> None:
    say("# U0.2a schema walk-through (G5)\n")
    say("Plain SQL as the app user `cucumber_app`; a few steps as the table owner.")
    story = Story(App())
    for walk in (names, zoho_link, skus, batches, events, no_edits, closing, lists):
        walk(story)
    undo_guard()
    say(SERVICE_ONLY)
    say(f"**Result: {tally['match']} checks as expected, {tally['differ']} not.**")
    sys.exit(1 if tally["differ"] else 0)


if __name__ == "__main__":
    main()
