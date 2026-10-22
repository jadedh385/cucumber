"""Rows for the U0.2a walk-through, written with plain SQL as `cucumber_app`.

Kept apart from `u0_2a_walkthrough.py` so the story there reads step by step.
Needs `django.setup()` to have run first.
"""

import uuid
from collections.abc import Mapping

import psycopg
from django.contrib.auth.models import User
from django.db import DatabaseError, connection
from psycopg import sql

from cucumber.accounts.permissions import Role
from cucumber.accounts.services import replace_role
from cucumber.core.audit import SYSTEM, WRITE_SETTINGS, audited, system_account
from cucumber.core.refusals import Refused, message_for, rule_of
from cucumber.env import env
from cucumber.events.services import NewEvent, save_operation

APP_ROLE = "cucumber_app"
UAT_VIA = "uat"  # shows in the audit trail as how these rows were made
SAVED = "saved"
NOT_ALLOWED = "not allowed: the app has no permission"

Values = Mapping[str, object]
Params = list[object] | None


def refused(rule: str) -> str:
    """How a refusal reads: the rule's name and the message staff see."""
    return f'refused by `{rule}`: "{message_for(rule)}"'


def as_owner(query: str, params: list[int] | None = None) -> str:
    """Run `query` as the table owner, `cucumber_owner` (Django's connection)."""
    try:
        with audited(SYSTEM, via=UAT_VIA), connection.cursor() as cursor:
            cursor.execute(query, params)
    except DatabaseError as error:
        return refused(rule_of(error))
    return SAVED


class App:
    """Plain SQL as `cucumber_app`; each statement is its own transaction."""

    def __init__(self) -> None:
        settings = connection.settings_dict
        self.db = psycopg.connect(
            dbname=settings["NAME"],
            user=APP_ROLE,
            password=env("DB_APP_PASSWORD"),
            host=settings["HOST"],
            port=settings["PORT"],
            autocommit=True,
        )
        current = self.db.execute("SELECT current_user").fetchone()
        if current != (APP_ROLE,):
            raise RuntimeError(f"expected to connect as {APP_ROLE}, got {current}")
        self.actor = str(system_account().pk)

    def one(self, query: str, params: Params = None) -> object:
        """The first column of the one row `query` returns."""
        row = self.db.execute(query.encode(), params).fetchone()
        if row is None:
            raise RuntimeError(f"no row from: {query}")
        return row[0]

    def attempt(
        self,
        statement: sql.Composed | bytes,
        params: Params = None,
        reason: str = "",
    ) -> str:
        """Run one statement; say whether it was saved or what refused it.

        `reason` is the code a switch-off, void or retire must give (U0.7).
        """
        try:
            with self.db.transaction():
                # Every audited write names a person (U0.7): System, here.
                self.db.execute(WRITE_SETTINGS, [self.actor, UAT_VIA, reason, ""])
                self.db.execute(statement, params)
        except psycopg.errors.InsufficientPrivilege:
            return NOT_ALLOWED
        except psycopg.Error as error:
            return refused(error.diag.constraint_name or "unnamed")
        return SAVED

    def run(self, query: str, params: Params = None, reason: str = "") -> str:
        return self.attempt(query.encode(), params, reason)

    def insert(self, table: str, values: Values) -> str:
        statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(", ").join(map(sql.Identifier, values)),
            sql.SQL(", ").join(sql.Placeholder() * len(values)),
        )
        return self.attempt(statement, list(values.values()))

    def update(self, table: str, key: object, values: Values, reason: str = "") -> str:
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(column)) for column in values
        )
        statement = sql.SQL("UPDATE {} SET {} WHERE id = %s").format(
            sql.Identifier(table), assignments
        )
        return self.attempt(statement, [*values.values(), key], reason)


class Story:
    """The people and rows the walk-through's steps share."""

    def __init__(self, app: App) -> None:
        self.app = app
        # User names are emails (U0.5's auth_user rule).
        self.admin = self.person("admin@example.com", Role.ADMIN)
        self.tech = self.person("tech-a@example.com", Role.TECH)

    @staticmethod
    def person(email: str, role: Role) -> int:
        with audited(SYSTEM, via=UAT_VIA):
            user = User.objects.create_user(username=email, email=email)
            replace_role(user, role)  # services refuse an account with no role (U0.6)
        return user.pk

    # Times, from the database clock

    def now(self) -> object:
        return self.app.one("SELECT now()")

    def days_ago(self, days: int) -> object:
        return self.app.one("SELECT now() - make_interval(days => %s)", [days])

    def hours_ahead(self, hours: int) -> object:
        return self.app.one("SELECT now() + make_interval(hours => %s)", [hours])

    # Plants and SKUs

    def add_plant(self, name: str, **overrides: object) -> str:
        values = {
            "genus_code": "PHL",
            "full_name": name,
            "status": "collection",
            "source": "gift",
            "notes": "",
            "created_at": self.now(),
            "created_by": self.admin,
            **overrides,
        }
        return self.app.insert("plants", values)

    def plant(self, name: str) -> object:
        """The id of the Philodendron called `name` that isn't voided."""
        return self.app.one(
            "SELECT id FROM plants WHERE full_name = %s AND genus_code = 'PHL'"
            " AND status <> 'voided'",
            [name],
        )

    def issue_sku(self, plant: object, sku: str, genus: str = "") -> str:
        values = {
            "sku": sku,
            "plant_id": plant,
            "genus_code": genus or sku[:3],
            "assigned_at": self.now(),
            "assigned_by": self.admin,
        }
        return self.app.insert("skus", values)

    def give_sku(self, plant: object, sku: str) -> str:
        """Issue `sku` to the plant and point the plant at it."""
        issued = self.issue_sku(plant, sku)
        if issued != SAVED:
            return issued
        return self.app.update("plants", plant, {"sku": sku})

    # Batches

    def operation(self) -> object:
        return self.app.one(
            "INSERT INTO operations (id, recorded_by)"
            " VALUES (gen_random_uuid(), %s) RETURNING id",
            [self.tech],
        )

    def add_batch(self, plant: object, **overrides: object) -> str:
        seq = self.app.one(
            "SELECT coalesce(max(plant_seq), 0) + 1 FROM batches WHERE plant_id = %s",
            [plant],
        )
        values = {
            "plant_id": plant,
            "plant_seq": seq,
            "origin": "intake",
            "created_operation_id": self.operation(),
            "location_code": "nursery",
            "quarantined": False,
            "status": "open",
            "live_count": 0,
            "created_at": self.now(),
            "created_by": self.tech,
            **overrides,
        }
        return self.app.insert("batches", values)

    def last_batch(self) -> object:
        return self.app.one("SELECT max(id) FROM batches")

    def plant_batch(self, name: str) -> object:
        """The plant's first batch."""
        return self.app.one(
            "SELECT min(id) FROM batches WHERE plant_id = %s", [self.plant(name)]
        )

    # Events and reviews

    def add_event(self, batch: object, action: str, **overrides: object) -> str:
        values = {
            "operation_id": self.operation(),
            "batch_id": batch,
            "action": action,
            "staff_id": self.tech,
            "recorded_by": self.tech,
            "occurred_at": self.now(),
            **overrides,
        }
        return self.app.insert("events", values)

    def last_event(self) -> int:
        event = self.app.one("SELECT max(id) FROM events")
        if not isinstance(event, int):
            raise RuntimeError("no events yet")
        return event

    def reason(self, applies_to: str) -> object:
        return self.app.one(
            "SELECT code FROM reasons WHERE applies_to = %s ORDER BY code LIMIT 1",
            [applies_to],
        )

    def save_loss(self, batch: object, qty: int) -> str:
        """A loss saved through the event service, as a screen will save it."""
        entry = NewEvent(
            "loss",
            batch_id=int(str(batch)),
            qty_out=qty,
            reason_code=str(self.reason("loss")),
        )
        try:
            save_operation(uuid.uuid4(), User.objects.get(pk=self.tech), [entry])
        except Refused as refusal:
            return refused(refusal.rule)
        return SAVED

    def review(self, event: object) -> str:
        values = {"event_id": event, "reviewer_id": self.admin, "note": ""}
        return self.app.insert("event_reviews", values)
