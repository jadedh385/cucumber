"""The 10× timing check (U0.4b design §13; U0.2a and U0.2b G5 timing notes).

Loads 10 times today's data (Owner, 2026-10-12: ~300 plants, 1,000 open
batches, 100 entries a day) into a throwaway database, then times the saves
and look-ups staff will make. Run it with `uat/timing_10x.sh`, which makes
the database `cucumber_timing` first; any other database is refused.

The load is plain SQL, for speed, with every rule and trigger still on. All
dates sit inside the last 7 days, the oldest an entry may have
(`event_within_7_days`). Each batch's stored count matches its events, so
`check_projections` passes on the loaded data.
"""

import os
import statistics
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from io import StringIO

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cucumber.settings")
django.setup()

import psycopg  # noqa: E402
from django.contrib.auth.models import Group, User  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402

from cucumber.accounts.permissions import Role  # noqa: E402
from cucumber.accounts.services import replace_role  # noqa: E402
from cucumber.env import env  # noqa: E402
from cucumber.events.reviews import review, review_queue, waiting_for_review  # noqa: E402
from cucumber.events.services import (  # noqa: E402
    NewBatch,
    NewEvent,
    correct,
    save_operation,
    split,
    void,
)

DATABASE = "cucumber_timing"
APP_ROLE = "cucumber_app"
RUNS = 30
GENUS = "PHL"
COUNT_EVERY = 10  # every 10th entry after the intake is a count
P95 = 95
AppConnection = psycopg.Connection[tuple[object, ...]]
SqlParams = dict[str, int | str]

LABELS = (
    "Save an entry, typical batch",
    "Save an entry, busy batch",
    "Open a batch (intake)",
    "Split",
    "Void",
    "Correction",
    "Mark one queue item reviewed",
    "Review queue, whole backlog",
    "Register a plant (plain SQL as the app)",
    "Find a plant by name (plain SQL as the app)",
    "One batch's history (plain SQL as the app)",
    "check_projections, every batch (once)",
)


@dataclass(frozen=True)
class Scale:
    """How much data to load. The defaults are 10× today."""

    plants: int = 3_000
    batches: int = 10_000
    events_per_batch: int = 36  # a year at 10×, spread over the batches
    busy_events: int = 2_000  # one batch with a long history
    backlog: int = 7_000  # a week of entries waiting for review

    @property
    def total_events(self) -> int:
        return self.batches * self.events_per_batch + self.busy_events


@dataclass(frozen=True)
class Summary:
    median: float  # milliseconds
    p95: float


@dataclass(frozen=True)
class Staff:
    admin: User
    supervisor: User
    tech: User


# ---------------------------------------------------------------- plain parts


def summarize(samples_ms: Sequence[float]) -> Summary:
    """Median and 95th percentile (nearest rank) of the timings."""
    ordered = sorted(samples_ms)
    rank = max(1, -(-P95 * len(ordered) // 100))  # ceiling, at least the first
    return Summary(median=statistics.median(ordered), p95=ordered[rank - 1])


def outs_among(entries: int) -> int:
    """How many of entries 1…`entries` are outs (the rest are counts)."""
    return entries - entries // COUNT_EVERY


def start_qty(events: int) -> int:
    """The intake's quantity: enough that the outs never empty the batch."""
    return 2 * events


def final_count(events: int) -> int:
    """A batch's live count after its `events` (intake, then outs and counts)."""
    return start_qty(events) - outs_among(events - 1)


def shown(ms: float) -> str:
    return f"{ms / 1000:.2f} s" if ms >= 1000 else f"{ms:.1f} ms"


def as_table(rows: Sequence[tuple[str, Summary]]) -> str:
    lines = ["| Action | Median | p95 |", "|---|--:|--:|"]
    lines += [f"| {label} | {shown(s.median)} | {shown(s.p95)} |" for label, s in rows]
    return "\n".join(lines)


def check_database(name: str) -> None:
    """Refuse to load into anything but the throwaway database."""
    if name != DATABASE:
        raise SystemExit(
            f"Refused: this loads 362,000 made-up entries. It only runs on "
            f"{DATABASE!r}, not {name!r}. Use uat/timing_10x.sh."
        )


# ------------------------------------------------------------------- the load


def run_sql(query: str, params: SqlParams | None = None) -> None:
    with connection.cursor() as cursor:
        cursor.execute(query, params)


def make_staff() -> Staff:
    def member(name: str, role: str) -> User:
        # The user name is the email (U0.5's auth_user rule).
        email = f"timing-{name}@example.com"
        user, _ = User.objects.get_or_create(username=email, defaults={"email": email})
        Group.objects.get_or_create(name=role)  # a flushed test database has none
        replace_role(user, Role(role))
        return user

    return Staff(
        member("admin", "admin"), member("sup", "supervisor"), member("tech", "tech")
    )


def seed_reference_rows() -> None:
    """The codes the load and timings use, if missing (a flushed test database)."""
    run_sql(
        """
        INSERT INTO genera (code, name, active) VALUES (%(genus)s, 'Philodendron', true)
            ON CONFLICT DO NOTHING;
        INSERT INTO locations (code, label, active) VALUES ('nursery', 'Nursery', true)
            ON CONFLICT DO NOTHING;
        INSERT INTO reasons (code, label, applies_to, active) VALUES
            ('void_test_entry', 'Test entry', 'void', true),
            ('correction_wrong_quantity', 'Wrong quantity', 'correction', true)
            ON CONFLICT DO NOTHING;
        """,
        {"genus": GENUS},
    )


def load_plants(scale: Scale, tech: User) -> None:
    run_sql(
        """INSERT INTO plants (genus_code, full_name, status, created_by)
           SELECT %(genus)s, 'Timing plant ' || n, 'candidate', %(tech)s
           FROM generate_series(1, %(plants)s) AS n""",
        {"genus": GENUS, "plants": scale.plants, "tech": tech.pk},
    )


def load_batches(first: int, last: int, events: int, scale: Scale, tech: User) -> None:
    """Batches `first`…`last`, each an intake then `events - 1` outs and counts.

    One operation per entry; ids are md5 uuids of the batch and entry number,
    so each step can find the last one's rows. Dates run oldest first from 6
    days ago.
    """
    params: SqlParams = {
        "first": first,
        "last": last,
        "last_k": events - 1,
        "plants": scale.plants,
        "start": start_qty(events),
        "live": final_count(events),
        "every": COUNT_EVERY,
        "step": f"{5 * 24 * 3600 / events} seconds",
        "tech": tech.pk,
    }
    entries = """FROM generate_series(%(first)s, %(last)s) AS n
                 CROSS JOIN generate_series(0, %(last_k)s) AS k"""
    operation = """(CASE WHEN k = 0 THEN md5('b' || n)
                         ELSE md5('e' || n || '-' || k) END)::uuid"""
    run_sql(
        f"""INSERT INTO operations (id, recorded_by)
            SELECT {operation}, %(tech)s {entries}""",
        params,
    )
    run_sql(
        """INSERT INTO batches (plant_seq, origin, created_operation_id, live_count,
                                created_by, location_code, plant_id)
           SELECT (n - 1) / %(plants)s + 1, 'intake', md5('b' || n)::uuid, %(live)s,
                  %(tech)s, 'nursery', p.id
           FROM generate_series(%(first)s, %(last)s) AS n
           JOIN (SELECT id, row_number() OVER (ORDER BY id) AS rank FROM plants) AS p
             ON p.rank = (n - 1) %% %(plants)s + 1""",
        params,
    )
    # Before entry k: (k - 1) entries, of which (k - 1) / every are counts.
    run_sql(
        f"""INSERT INTO events (action, qty_in, qty_out, counted_qty, occurred_at,
                                batch_id, recorded_by, staff_id, operation_id)
            SELECT CASE WHEN k = 0 THEN 'intake'
                        WHEN k %% %(every)s = 0 THEN 'count' ELSE 'out' END,
                   CASE WHEN k = 0 THEN %(start)s ELSE 0 END,
                   CASE WHEN k > 0 AND k %% %(every)s <> 0 THEN 1 ELSE 0 END,
                   CASE WHEN k > 0 AND k %% %(every)s = 0
                        THEN %(start)s - ((k - 1) - (k - 1) / %(every)s) END,
                   now() - interval '6 days' + k * %(step)s::interval,
                   b.id, %(tech)s, %(tech)s, {operation}
            {entries}
            JOIN batches AS b ON b.created_operation_id = md5('b' || n)::uuid""",
        params,
    )


def mark_reviewed_but_backlog(scale: Scale, supervisor: User) -> None:
    """Every entry reviewed except the newest `backlog`."""
    run_sql(
        """INSERT INTO event_reviews (event_id, reviewer_id)
           SELECT id, %(sup)s FROM events ORDER BY id DESC OFFSET %(backlog)s""",
        {"sup": supervisor.pk, "backlog": scale.backlog},
    )


def load(scale: Scale) -> Staff:
    staff = make_staff()
    seed_reference_rows()
    load_plants(scale, staff.tech)
    load_batches(1, scale.batches, scale.events_per_batch, scale, staff.tech)
    busy = scale.batches + 1
    load_batches(busy, busy, scale.busy_events, scale, staff.tech)
    mark_reviewed_but_backlog(scale, staff.supervisor)
    run_sql("ANALYZE")
    return staff


# ---------------------------------------------------------------- the timings


def timed(action: Callable[[int], object], runs: int) -> Summary:
    """Run `action(run_number)` `runs` times; each run's wall time in ms."""
    samples = []
    for number in range(runs):
        started = time.perf_counter()
        action(number)
        samples.append((time.perf_counter() - started) * 1000)
    return summarize(samples)


def column(query: str, params: Sequence[int] = ()) -> list[int]:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return [row[0] for row in cursor.fetchall()]


def entry(by: User, batch_id: int) -> object:
    return save_operation(
        uuid.uuid4(), by, [NewEvent("out", batch_id=batch_id, qty_out=1)]
    )


def service_timings(staff: Staff, runs: int) -> list[Summary]:
    """The writes through the event services, as staff save them."""
    tech, sup, admin = staff.tech, staff.supervisor, staff.admin
    typical = column("SELECT id FROM batches ORDER BY id LIMIT %s", [runs * 3])
    busy = column("SELECT id FROM batches ORDER BY id DESC LIMIT 1")[0]
    plant = column("SELECT id FROM plants ORDER BY id LIMIT 1")[0]
    # Reviewed outs, one per batch, from batches nothing else here touches.
    outs = column(
        """SELECT max(e.id) FROM events AS e
           JOIN event_reviews AS r ON r.event_id = e.id
           WHERE e.action = 'out' GROUP BY e.batch_id ORDER BY e.batch_id DESC
           LIMIT %s OFFSET 1""",
        [runs * 2],
    )
    waiting = [event.operation_id for event in waiting_for_review()][:runs]
    new_batch = NewBatch(plant_id=plant, origin="intake", location_code="nursery")
    return [
        timed(lambda n: entry(tech, typical[n]), runs),
        timed(lambda n: entry(tech, busy), runs),
        timed(
            lambda n: save_operation(
                uuid.uuid4(), tech, [NewEvent("intake", new_batch=new_batch, qty_in=10)]
            ),
            runs,
        ),
        timed(
            lambda n: split(uuid.uuid4(), tech, typical[runs + n], 1, "timing"), runs
        ),
        timed(lambda n: void(admin, outs[n], "void_test_entry"), runs),
        timed(
            lambda n: correct(
                sup, outs[runs + n], "correction_wrong_quantity", qty_out=2
            ),
            runs,
        ),
        timed(lambda n: review(sup, waiting[n]), runs),
        timed(lambda n: review_queue(sup), runs),
    ]


def app_timings(app: AppConnection, tech: User, runs: int) -> list[Summary]:
    """Single statements as `cucumber_app`, each its own transaction."""
    batch = column("SELECT id FROM batches ORDER BY id LIMIT 1")[0]
    tag = uuid.uuid4().hex[:8]  # new names each time the script runs
    return [
        timed(
            lambda n: app.execute(
                """INSERT INTO plants (genus_code, full_name, status, created_by)
               VALUES (%s, %s, 'candidate', %s)""",
                [GENUS, f"Timed plant {tag} {n}", tech.pk],
            ),
            runs,
        ),
        timed(
            lambda n: app.execute(
                "SELECT id FROM plants WHERE name_key LIKE %s", [f"%plant {n * 97}%"]
            ).fetchall(),
            runs,
        ),
        timed(
            lambda n: app.execute(
                "SELECT * FROM events WHERE batch_id = %s ORDER BY occurred_at, id",
                [batch],
            ).fetchall(),
            runs,
        ),
    ]


def measure(scale: Scale, runs: int, app: AppConnection) -> list[tuple[str, Summary]]:
    """Every timing in `LABELS` order, on data `load(scale)` made."""
    staff = make_staff()
    summaries = service_timings(staff, runs) + app_timings(app, staff.tech, runs)
    summaries.append(
        timed(lambda n: call_command("check_projections", stdout=StringIO()), 1)
    )
    return list(zip(LABELS, summaries, strict=True))


def connect_as_app() -> AppConnection:
    settings = connection.settings_dict
    app = psycopg.connect(
        dbname=settings["NAME"],
        user=APP_ROLE,
        password=env("DB_APP_PASSWORD"),
        host=settings["HOST"],
        port=settings["PORT"],
        autocommit=True,
    )
    if app.execute("SELECT current_user").fetchone() != (APP_ROLE,):
        raise SystemExit(f"expected to connect as {APP_ROLE}")
    return app


def main() -> None:
    check_database(connection.settings_dict["NAME"])
    scale = Scale()
    print(
        f"Loading {scale.plants:,} plants, {scale.batches + 1:,} batches, "
        f"{scale.total_events:,} entries…",
        file=sys.stderr,
    )
    started = time.perf_counter()
    load(scale)
    print(
        f"Loaded in {time.perf_counter() - started:.1f} s. Timing {RUNS} runs each…",
        file=sys.stderr,
    )
    with connect_as_app() as app:
        print(as_table(measure(scale, RUNS, app)))


if __name__ == "__main__":
    main()
