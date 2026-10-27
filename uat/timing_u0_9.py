"""U0.9 G5 timing: the reference lists at 10× data, before and after (design §3.2, Q3).

Run from a checkout's root with that checkout on the path, against the throwaway
`cucumber_timing` database (the same guard as `scripts.timing_10x`):

    PYTHONPATH=. python uat/timing_u0_9.py load      # 10× data
    PYTHONPATH=. python uat/timing_u0_9.py measure   # the usual timings, plus the lists

The same file runs on `2026.10.5` (before U0.9: the usual table only) and on the
U0.9 branch (after: the usual table, the list reads, the writers, and the
inactive check on a save). The check's cost is the same save made with
`picked=False` (no check, as before U0.9) and with the default (checked), taken
one after the other, plus the number of queries the check makes.
Output is a markdown table.
"""

import importlib
import importlib.util
import os
import sys
import time
import uuid
from collections.abc import Callable

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cucumber.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import User  # noqa: E402
from django.db import connection  # noqa: E402

from cucumber.core.audit import Reason  # noqa: E402
from cucumber.events.services import NewBatch, NewEvent, save_operation  # noqa: E402
from scripts import timing_10x as base  # noqa: E402

AFTER = importlib.util.find_spec("cucumber.references.reading") is not None
RUNS = base.RUNS
WARM_UP = 5
VIA = "timing load"
Rows = list[tuple[str, base.Summary]]


def load() -> None:
    base.check_database(connection.settings_dict["NAME"])
    scale = base.Scale()
    base.load(scale)
    base.run_sql("ANALYZE")
    sys.stdout.write(f"loaded {scale.plants} plants, {scale.batches + 1} batches\n")


def dropdown(name: object) -> Callable[[int], object]:
    reading = importlib.import_module("cucumber.references.reading")
    return lambda n: reading.active_items(name)


def list_reads() -> Rows:
    """Every dropdown, one item and the inactive check, on the five stored lists."""
    reading = importlib.import_module("cucumber.references.reading")
    names = importlib.import_module("cucumber.references.lists").ListName
    stored = [names.STAGES, names.MEDIA_CODES, names.LOCATIONS, names.GENERA]
    stored.append(names.CONTAINER_TYPES)
    rows = [
        (f"Read the {name.value} dropdown", base.timed(dropdown(name), RUNS))
        for name in stored
    ]
    media = names.MEDIA_CODES

    def one(n: int) -> object:
        return reading.item(media, "M001")

    def check_one(n: int) -> object:
        return reading.check_active(media, "M001")

    def check_three(n: int) -> object:
        return reading.check_active(media, "M001", "M002", "M003")

    return rows + [
        ("`item`, one media code", base.timed(one, RUNS)),
        ("`check_active`, one media code", base.timed(check_one, RUNS)),
        ("`check_active`, three media codes", base.timed(check_three, RUNS)),
    ]


def intake(plant_id: int) -> list[NewEvent]:
    """A save that picks a medium, a stage and a location: the most checks."""
    batch = NewBatch(plant_id=plant_id, origin="intake", location_code="nursery")
    entry = NewEvent(
        "intake", new_batch=batch, qty_in=1, stage_to="P0", media_code="M001"
    )
    return [entry]


def check_cost(tech: User) -> tuple[Rows, int]:
    """The same intake saved without and with the check, alternating, and the
    number of queries the check makes."""
    plant = base.column("SELECT id FROM plants ORDER BY id LIMIT 1")[0]
    for _ in range(WARM_UP):
        save_operation(uuid.uuid4(), tech, intake(plant))
    samples: dict[bool, list[float]] = {False: [], True: []}
    for _ in range(RUNS):
        for picked in (False, True):
            started = time.perf_counter()
            save_operation(uuid.uuid4(), tech, intake(plant), picked=picked)
            samples[picked].append((time.perf_counter() - started) * 1000)
    services = importlib.import_module("cucumber.events.services")
    queries: list[str] = []

    def count(execute: Callable[..., object], sql: str, *rest: object) -> object:
        queries.append(sql)
        return execute(sql, *rest)

    with connection.execute_wrapper(count):
        services.check_picked(intake(plant))
    rows = [
        (
            "Open a batch with a medium, stage and location, no check (as before)",
            base.summarize(samples[False]),
        ),
        ("The same, with the inactive check", base.summarize(samples[True])),
    ]
    return rows, len(queries)


def writer_timings(admin: User) -> Rows:
    """An Admin's changes, on a test code made here (a list has no delete)."""
    services = importlib.import_module("cucumber.references.services")
    media = importlib.import_module("cucumber.references.lists").ListName.MEDIA_CODES
    code = f"ZT{uuid.uuid4().hex[:6].upper()}"
    started = time.perf_counter()
    services.add_item(admin, media, code, "Timed", via=VIA)
    added = base.summarize([(time.perf_counter() - started) * 1000])
    reason = Reason("archive_other", "timing")

    def relabel(n: int) -> object:
        return services.edit_label(admin, media, code, f"Timed {n}", via=VIA)

    def flip(n: int) -> object:
        if n % 2 == 0:
            return services.switch_off(admin, media, code, reason, via=VIA)
        return services.switch_on(admin, media, code, via=VIA)

    return [
        ("Add a media code (one run)", added),
        ("Change a label", base.timed(relabel, RUNS)),
        ("Switch an item off or on", base.timed(flip, RUNS)),
    ]


def measure() -> None:
    base.check_database(connection.settings_dict["NAME"])
    staff = base.make_staff()
    with base.connect_as_app() as app:
        rows: Rows = base.measure(base.Scale(), RUNS, app)
    queries = None
    if AFTER:
        saves, queries = check_cost(staff.tech)
        rows += list_reads() + saves + writer_timings(staff.admin)
    sys.stdout.write(base.as_table(rows) + "\n")
    if queries is not None:
        sys.stdout.write(
            f"\nQueries the inactive check makes on that save: {queries}\n"
        )


COMMANDS: dict[str, Callable[[], None]] = {"load": load, "measure": measure}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit(__doc__)
    COMMANDS[sys.argv[1]]()
