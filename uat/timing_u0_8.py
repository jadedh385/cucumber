"""U0.8 G5 timing: the ID work at 10× data, before and after (design §4).

Run from a checkout's root with that checkout on the path, against the throwaway
`cucumber_timing` database (the same guard as `scripts.timing_10x`):

    PYTHONPATH=. python uat/timing_u0_8.py load      # 10× data, 900 SKUs
    PYTHONPATH=. python uat/timing_u0_8.py measure   # the usual timings + ID work

The same file runs on `main` (before U0.8) and on the U0.8 branch (after). Where
the branch has a new function, `main` gets the nearest thing it had: a look-up is
the plain query the old code would have made. Output is a markdown table.
"""

import importlib
import importlib.util
import os
import random
import sys
import uuid
from collections.abc import Callable
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cucumber.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import User  # noqa: E402
from django.db import connection, transaction  # noqa: E402

from cucumber.batches.models import Batch  # noqa: E402
from cucumber.core.audit import SYSTEM, audited  # noqa: E402
from cucumber.events.models import Event  # noqa: E402
from cucumber.events.services import NewBatch, NewEvent, save_operation  # noqa: E402
from cucumber.plants.models import Plant  # noqa: E402
from scripts import timing_10x as base  # noqa: E402

SKUS_LOADED = 900  # 10× today's ~90 plants with an SKU
LOOKUPS = 30

Probe = Callable[[int], object]


def first_found(*places: str) -> Any:
    """The first `module:name` that exists: the branch's, else `main`'s."""
    for place in places:
        module, name = place.split(":")
        try:
            return getattr(importlib.import_module(module), name)
        except (ImportError, AttributeError):
            continue
    raise SystemExit(f"none of {places} exists")


AFTER = importlib.util.find_spec("cucumber.ids") is not None
issue_next_sku = first_found(
    "cucumber.ids.issuing:issue_next_sku", "cucumber.plants.services:issue_next_sku"
)
lock_plants = first_found(
    "cucumber.ids.issuing:lock_plants", "cucumber.events.writing:lock_plants"
)
find_by_sku = first_found(
    "cucumber.ids.lookup:find_by_sku", "cucumber.plants.services:find_by_sku"
)


def load() -> None:
    base.check_database(connection.settings_dict["NAME"])
    scale = base.Scale()
    base.load(scale)
    with audited(SYSTEM, via=base.LOADED_BY):
        base.run_sql(
            """INSERT INTO skus (sku, plant_id, genus_code, assigned_at, assigned_by)
               SELECT 'PHL' || lpad(id::text, 3, '0'), id, 'PHL', now(), created_by
               FROM plants WHERE id <= %(n)s""",
            {"n": SKUS_LOADED},
        )
        base.run_sql(
            "UPDATE plants SET sku = 'PHL' || lpad(id::text, 3, '0') WHERE id <= %(n)s",
            {"n": SKUS_LOADED},
        )
    base.run_sql("ANALYZE")
    sys.stdout.write(
        f"loaded {scale.plants} plants, {scale.batches + 1} batches, "
        f"{SKUS_LOADED} SKUs\n"
    )


def probes_after(picks: dict[str, list[int]]) -> dict[str, Probe]:
    """The look-ups through `look_up`."""
    look_up = first_found("cucumber.ids.lookup:look_up")
    if look_up(f"PHL{picks['skus'][0]:03d} · B001") is None:
        raise SystemExit("the short name PHL001 · B001 did not read")
    return {
        "Look up by PLT- id (look_up)": lambda n: look_up(
            f"PLT-{picks['plants'][n]:04d}"
        ),
        "Look up by BAT- id": lambda n: look_up(f"BAT-{picks['batches'][n]:05d}"),
        "Look up by EVT- id": lambda n: look_up(f"EVT-{picks['events'][n]:05d}"),
        "Look up by SKU": lambda n: look_up(f"PHL{picks['skus'][n]:03d}"),
        "Look up by short name": lambda n: look_up(f"PHL{picks['skus'][n]:03d} · B001"),
    }


def probes_before(picks: dict[str, list[int]]) -> dict[str, Probe]:
    """What `main` had: the plain queries a look-up would have made."""

    def by_short(n: int) -> object:
        plant = find_by_sku(f"PHL{picks['skus'][n]:03d}")
        return Batch.objects.filter(plant_id=plant.pk, plant_seq=1).first()

    return {
        "Look up by PLT- id (plain query, no look_up yet)": lambda n: (
            Plant.objects.filter(pk=picks["plants"][n]).first()
        ),
        "Look up by BAT- id": lambda n: Batch.objects.filter(
            pk=picks["batches"][n]
        ).first(),
        "Look up by EVT- id": lambda n: Event.objects.filter(
            pk=picks["events"][n]
        ).first(),
        "Look up by SKU": lambda n: find_by_sku(f"PHL{picks['skus'][n]:03d}"),
        "Look up by short name": by_short,
    }


def lookups(rng: random.Random) -> list[tuple[str, base.Summary]]:
    picks = {
        "plants": [rng.randint(1, 3000) for _ in range(LOOKUPS)],
        "batches": [rng.randint(1, 10000) for _ in range(LOOKUPS)],
        "events": [rng.randint(1, 300000) for _ in range(LOOKUPS)],
        "skus": [rng.randint(1, SKUS_LOADED) for _ in range(LOOKUPS)],
    }
    probes = probes_after(picks) if AFTER else probes_before(picks)
    return [(label, base.timed(fn, LOOKUPS)) for label, fn in probes.items()]


def issuing(admin: User, tech: User) -> list[tuple[str, base.Summary]]:
    without_sku = base.column(
        "SELECT id FROM plants WHERE sku IS NULL ORDER BY id LIMIT 400"
    )

    def issue(n: int) -> None:
        with transaction.atomic(), audited(admin, via=base.LOADED_BY):
            issue_next_sku(without_sku[n], "PHL", admin)

    def lock_one(n: int) -> None:
        with transaction.atomic():
            lock_plants([without_sku[100 + n]])

    def lock_five(n: int) -> None:
        with transaction.atomic():
            lock_plants(without_sku[150 + n * 5 : 155 + n * 5])

    def new_batch(n: int) -> None:
        batch = NewBatch(
            plant_id=without_sku[350 + n], origin="intake", location_code="nursery"
        )
        entry = NewEvent(
            "intake", new_batch=batch, qty_in=10, stage_to="P0", media_code="M001"
        )
        save_operation(uuid.uuid4(), tech, [entry])

    runs = base.RUNS
    return [
        ("issue_next_sku", base.timed(issue, runs)),
        ("lock_plants, 1 plant", base.timed(lock_one, runs)),
        ("lock_plants, 5 plants", base.timed(lock_five, runs)),
        ("Save a new batch with its intake", base.timed(new_batch, runs)),
    ]


def measure() -> None:
    base.check_database(connection.settings_dict["NAME"])
    staff = base.make_staff()
    with base.connect_as_app() as app:
        usual = base.measure(base.Scale(), base.RUNS, app)
    picks = random.Random(8)  # noqa: S311 (fixed picks, not secrets)
    extra = lookups(picks) + issuing(staff.admin, staff.tech)
    sys.stdout.write(base.as_table(usual + extra) + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("load", "measure"):
        raise SystemExit(__doc__)
    {"load": load, "measure": measure}[sys.argv[1]]()
