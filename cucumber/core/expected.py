"""What each database protection should look like (U0.7 design §8.1).

`guards.check()` compares the database with these. Each entry names the
migration that makes it as it is now, and is skipped until that migration
has run. A migration that changes a protection changes its entry here too,
on purpose: a function's body is pinned by its md5, so even a one-letter
change to a trigger function is reported until this file agrees.
"""

from dataclasses import dataclass

from cucumber.core import db_rules
from cucumber.core.db_rules import trigger_type

APP_ROLE = "cucumber_app"
OWNER_ROLE = "cucumber_owner"

CORE_0002 = "core.0002_protection_functions"
CORE_0003 = "core.0003_app_grants"
CORE_0005 = "core.0005_flag_grants"
U07 = "core.0006_audit_trail"
EVENTS_0002 = "events.0002_rules"
PLANTS_0002 = "plants.0002_rules"
BATCHES_0002 = "batches.0002_rules"
REFERENCES_0003 = "references.0003_rules"
ACCOUNTS_0001 = "accounts.0001_initial"


@dataclass(frozen=True)
class Trigger:
    table: str
    function: str
    tgtype: int  # pg_trigger.tgtype: timing and events
    arguments: tuple[str, ...] = ()


@dataclass(frozen=True)
class Function:
    md5: str  # md5 of pg_proc.prosrc, the body between the $$
    config: tuple[str, ...] = ()  # pg_proc.proconfig


@dataclass(frozen=True)
class AppRoleCheck:
    """A query that is true when the app role can get round the triggers."""

    sql: str
    problem: str
    migration: str


# ------------------------------------------------------------------ triggers

APPEND_ONLY_TYPE = trigger_type("BEFORE", "UPDATE OR DELETE")
NO_DELETE_TYPE = trigger_type("BEFORE", "DELETE")
BEFORE_UPDATE = trigger_type("BEFORE", "UPDATE")
BEFORE_INSERT = trigger_type("BEFORE", "INSERT")
TRUNCATE_TYPE = trigger_type("AFTER", "TRUNCATE", per="STATEMENT")

APPEND_ONLY_BY = {
    "audit_log": CORE_0002,
    "events": EVENTS_0002,
    "operations": EVENTS_0002,
    "event_reviews": EVENTS_0002,
    "skus": PLANTS_0002,
    "plant_status_changes": PLANTS_0002,
}
NO_DELETE_BY = {
    "plants": PLANTS_0002,
    "batches": BATCHES_0002,
    **dict.fromkeys([*db_rules.REFERENCE_LISTS, "vendors"], REFERENCES_0003),
    "auth_user": U07,
}

TRIGGERS: dict[str, tuple[Trigger, str]] = {
    **{
        f"{table}_append_only": (
            Trigger(table, "cucumber_append_only", APPEND_ONLY_TYPE),
            migration,
        )
        for table, migration in APPEND_ONLY_BY.items()
    },
    **{
        f"{table}_no_delete": (
            Trigger(table, "cucumber_no_delete", NO_DELETE_TYPE),
            migration,
        )
        for table, migration in NO_DELETE_BY.items()
    },
    **{
        f"{table}_code_rename": (
            Trigger(table, "cucumber_code_rename", BEFORE_UPDATE),
            REFERENCES_0003,
        )
        for table in db_rules.REFERENCE_LISTS
    },
    "plant_sku_static": (
        Trigger("plants", "plant_sku_static", BEFORE_UPDATE),
        PLANTS_0002,
    ),
    "events_recorded_at_now": (
        Trigger("events", "events_recorded_at_now", BEFORE_INSERT),
        EVENTS_0002,
    ),
    # U0.7: the trail (§4.1), the reason rule (§4.2), TRUNCATE (§4.4), §3.2.
    **{
        f"{spec.table}_audit": (
            Trigger(
                spec.table,
                "cucumber_audit",
                trigger_type("AFTER", spec.events),
                spec.arguments,
            ),
            U07,
        )
        for spec in db_rules.AUDITED_TABLES
    },
    **{
        f"{spec.table}_reason_required": (
            Trigger(
                spec.table, "cucumber_reason_required", BEFORE_UPDATE, spec.arguments
            ),
            U07,
        )
        for spec in db_rules.SWITCH_OFFS
    },
    **{
        f"{table}_truncate_noticed": (
            Trigger(table, "cucumber_truncate_noticed", TRUNCATE_TYPE),
            U07,
        )
        for table in db_rules.TRUNCATE_NOTICED_TABLES
    },
    "audit_log_stamp": (Trigger("audit_log", "audit_log_stamp", BEFORE_INSERT), U07),
}

# ----------------------------------------------------------------- functions

FIXED_SEARCH_PATH = (f"search_path={db_rules.SEARCH_PATH}",)

FUNCTIONS: dict[str, tuple[Function, str]] = {
    "cucumber_append_only": (Function("7bdd6eea648eff40c4afea7ae00aa29b"), CORE_0002),
    "cucumber_no_delete": (Function("4eddf5ec2f0156dd3bcffbd3fedef00a"), CORE_0002),
    "cucumber_code_rename": (Function("d0407593fe12ebc99cbbf0aef032ca30"), CORE_0002),
    "plant_sku_static": (Function("f51c40c6ffb137669eccb8fbaa842e3c"), PLANTS_0002),
    "events_recorded_at_now": (
        Function("6b39bcb8499eae732cc2b6620ea91a7f"),
        EVENTS_0002,
    ),
    "cucumber_audit": (
        Function("c3b863e03ddaf1ce53e760c46ff4cd84", FIXED_SEARCH_PATH),
        U07,
    ),
    "cucumber_reason_required": (
        Function("fdbda1a7fdeb9f64947fa656a41e3b1d", FIXED_SEARCH_PATH),
        U07,
    ),
    "cucumber_truncate_noticed": (
        Function("047c6677192ed22753e934b09ed1d058", FIXED_SEARCH_PATH),
        U07,
    ),
    "audit_log_stamp": (
        Function("b265eb44fc5ee489b61a4d3b653ca266", FIXED_SEARCH_PATH),
        U07,
    ),
}

# -------------------------------------------------------------------- grants
#
# Exactly what `cucumber_app` may do with each table: core 0003, core 0005,
# accounts 0001's DELETE grants and U0.7's revoke. A table missing here is
# reported, so a new table can't take the default grants unnoticed.

TABLE_PRIVILEGES = (
    "SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER",
)  # fmt: skip
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")

READ = frozenset({"SELECT"})
ADD = frozenset({"SELECT", "INSERT"})
ADD_CHANGE = frozenset({"SELECT", "INSERT", "UPDATE"})
ADD_REMOVE = frozenset({"SELECT", "INSERT", "DELETE"})
ALL_BUT_TRUNCATE = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})

PRIVILEGES: dict[str, tuple[frozenset[str], str]] = {
    **dict.fromkeys(APPEND_ONLY_BY, (ADD, CORE_0003)),
    **dict.fromkeys(
        ["plants", "batches", *db_rules.REFERENCE_LISTS, "vendors", "auth_user"],
        (ADD_CHANGE, CORE_0003),
    ),
    **dict.fromkeys(
        ["django_session", "auth_user_groups"], (ALL_BUT_TRUNCATE, CORE_0003)
    ),
    **dict.fromkeys(
        [
            "auth_group",
            "auth_permission",
            "auth_group_permissions",
            "django_content_type",
            "django_migrations",
        ],
        (READ, CORE_0003),
    ),
    "auth_user_user_permissions": (READ, U07),
    **dict.fromkeys(
        ["accounts_login_failure", "accounts_password_change_due"],
        (ADD_REMOVE, ACCOUNTS_0001),
    ),
    "waffle_flag": (frozenset({"SELECT", "UPDATE"}), CORE_0005),
    "waffle_flag_groups": (ADD_REMOVE, CORE_0005),
    **dict.fromkeys(
        ["waffle_flag_users", "waffle_switch", "waffle_sample"], (READ, CORE_0005)
    ),
}

# ------------------------------------------------------------------ app role
#
# Any of these would let the app role switch the triggers off or catch the
# audit rows (review M1). The queries take %(app)s and %(owner)s.

APP_ROLE_CHECKS = {
    "superuser": AppRoleCheck(
        "SELECT coalesce("
        "(SELECT rolsuper FROM pg_roles WHERE rolname = %(app)s), false)",
        f"{APP_ROLE} is a superuser",
        CORE_0003,
    ),
    "owner member": AppRoleCheck(
        "SELECT pg_has_role(%(app)s, %(owner)s, 'MEMBER')",
        f"{APP_ROLE} is a member of {OWNER_ROLE}",
        CORE_0003,
    ),
    "role setting": AppRoleCheck(
        "SELECT EXISTS (SELECT 1 FROM pg_db_role_setting s"
        " JOIN pg_roles r ON r.oid = s.setrole WHERE r.rolname = %(app)s"
        " AND array_to_string(s.setconfig, ',') LIKE '%%session_replication_role%%')",
        f"{APP_ROLE} has session_replication_role set, which switches triggers off",
        CORE_0003,
    ),
    "temp": AppRoleCheck(
        "SELECT has_database_privilege(%(app)s, current_database(), 'TEMP')",
        f"{APP_ROLE} may make TEMP tables in this database",
        U07,
    ),
    "create": AppRoleCheck(
        "SELECT has_schema_privilege(%(app)s, 'public', 'CREATE')",
        f"{APP_ROLE} may CREATE tables in schema public",
        CORE_0003,
    ),
}
