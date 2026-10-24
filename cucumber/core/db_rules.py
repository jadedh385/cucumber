"""SQL for the database-level protection that migrations add (U0.2 design §4).

Each trigger raises with `USING CONSTRAINT = '<name>'` and has that name, so
a refusal reads like any constraint error (`diag.constraint_name`) and the
service can look up its message in design §7.1. The error code is
`restrict_violation` (23001), which Django raises as an IntegrityError.

Functions shared by many tables are created once (core migration 0002);
each app's migration attaches them to its own tables.

Migrations import this module, so once a migration has run in production
(from R1), never change what an existing helper produces: that would make a
fresh database differ from production. Change a rule with a new migration
(`CREATE OR REPLACE FUNCTION`, or a new trigger) instead (G4 review, M2).
"""

from dataclasses import dataclass

# --------------------------------------------------------- shared functions

FUNCTIONS = """
CREATE FUNCTION cucumber_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% rows are never changed or deleted', TG_TABLE_NAME
    USING ERRCODE = 'restrict_violation',
          CONSTRAINT = TG_TABLE_NAME || '_append_only';
END $$;

CREATE FUNCTION cucumber_no_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% rows are never deleted; void, retire or deactivate instead',
    TG_TABLE_NAME
    USING ERRCODE = 'restrict_violation',
          CONSTRAINT = TG_TABLE_NAME || '_no_delete';
END $$;

CREATE FUNCTION cucumber_code_rename() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.code IS DISTINCT FROM OLD.code THEN
    RAISE EXCEPTION '% code % can''t be renamed', TG_TABLE_NAME, OLD.code
      USING ERRCODE = 'restrict_violation',
            CONSTRAINT = TG_TABLE_NAME || '_code_rename';
  END IF;
  RETURN NEW;
END $$;
"""

DROP_FUNCTIONS = """
DROP FUNCTION cucumber_code_rename();
DROP FUNCTION cucumber_no_delete();
DROP FUNCTION cucumber_append_only();
"""


@dataclass(frozen=True)
class Sql:
    """A forward statement and the one that undoes it, for `RunSQL`."""

    forward: str
    reverse: str


def _trigger(table: str, rule: str, timing: str, function: str) -> Sql:
    name = f"{table}_{rule}"
    return Sql(
        forward=(
            f"CREATE TRIGGER {name} {timing} ON {table}"
            f" FOR EACH ROW EXECUTE FUNCTION {function}();"
        ),
        reverse=f"DROP TRIGGER {name} ON {table};",
    )


def append_only(table: str) -> Sql:
    """No UPDATE or DELETE, even for the table owner (AC13, AC19)."""
    return _trigger(
        table, "append_only", "BEFORE UPDATE OR DELETE", "cucumber_append_only"
    )


def no_delete(table: str) -> Sql:
    """No DELETE, even for the table owner (rule 9, AC6, AC20)."""
    return _trigger(table, "no_delete", "BEFORE DELETE", "cucumber_no_delete")


def code_rename(table: str) -> Sql:
    """Reference codes are permanent (AC20)."""
    return _trigger(table, "code_rename", "BEFORE UPDATE", "cucumber_code_rename")


def trigger_type(timing: str, events: str, per: str = "ROW") -> int:
    """`pg_trigger.tgtype` for a trigger, so the guard check can compare it.

    `timing` is BEFORE or AFTER, `events` e.g. "INSERT OR UPDATE".
    """
    bits = {"ROW": 1, "BEFORE": 2, "INSERT": 4, "DELETE": 8, "UPDATE": 16}
    bits |= {"TRUNCATE": 32}
    return sum(bits.get(word, 0) for word in [timing, per, *events.split(" OR ")])


def two_column_link(
    name: str, table: str, columns: str, target: str, target_columns: str
) -> Sql:
    """A foreign key over two columns, which Django can't declare (design M3).

    Not deferrable, so a bad link is refused by its own statement.
    """
    return Sql(
        forward=(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({columns})"
            f" REFERENCES {target} ({target_columns}) NOT DEFERRABLE;"
        ),
        reverse=f"ALTER TABLE {table} DROP CONSTRAINT {name};",
    )


# ------------------------------------------------- the audit trail (U0.7 §4)
#
# Each function's body is its own constant: the guard check compares the
# body's md5 with `pg_proc.prosrc` (U0.7 design §8.1). Every function fixes
# its search_path and names its tables `public.…` (review M1), and runs as
# the caller (not SECURITY DEFINER).

# `pg_temp` last, so a TEMP table can never shadow a real one.
SEARCH_PATH = "pg_catalog, public, pg_temp"

AUDIT_BODY = """
DECLARE
  ignored text[] := string_to_array(TG_ARGV[1], ',');
  masked text[] := string_to_array(TG_ARGV[2], ',');
  shown text := CASE TG_OP WHEN 'INSERT' THEN 'set' ELSE 'changed' END;
  actor text := nullif(current_setting('cucumber.actor_id', true), '');
  old_row jsonb;
  new_row jsonb;
  before_row jsonb;
  after_row jsonb;
  masked_column text;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    old_row := to_jsonb(OLD) - ignored;
  END IF;
  IF TG_OP <> 'DELETE' THEN
    new_row := to_jsonb(NEW) - ignored;
  END IF;
  IF TG_OP = 'UPDATE' THEN
    SELECT jsonb_object_agg(o.key, o.value), jsonb_object_agg(o.key, n.value)
      INTO before_row, after_row
      FROM jsonb_each(old_row) AS o JOIN jsonb_each(new_row) AS n ON n.key = o.key
     WHERE n.value IS DISTINCT FROM o.value;
    IF before_row IS NULL THEN
      RETURN NULL;  -- nothing audited changed: no row, and nobody is needed
    END IF;
  ELSE
    before_row := old_row;
    after_row := new_row;
  END IF;
  IF actor IS NULL THEN
    RAISE EXCEPTION '% can''t be changed without saying who changes it',
      TG_TABLE_NAME
      USING ERRCODE = 'restrict_violation', CONSTRAINT = 'audit_actor_required';
  END IF;
  FOREACH masked_column IN ARRAY masked LOOP
    IF before_row ? masked_column THEN
      before_row := jsonb_set(before_row, ARRAY[masked_column], to_jsonb(shown));
    END IF;
    IF after_row ? masked_column THEN
      after_row := jsonb_set(after_row, ARRAY[masked_column], to_jsonb(shown));
    END IF;
  END LOOP;
  INSERT INTO public.audit_log
    (actor_id, table_name, row_pk, action, before, after, reason_code, note, via)
  VALUES (
    actor::integer,
    TG_TABLE_NAME,
    CASE TG_OP WHEN 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END
      ->> TG_ARGV[0],
    lower(TG_OP),
    before_row,
    after_row,
    nullif(current_setting('cucumber.reason_code', true), ''),
    nullif(current_setting('cucumber.note', true), ''),
    coalesce(
      nullif(current_setting('cucumber.via', true), ''),
      'sql as ' || session_user
    )
  );
  RETURN NULL;
END
"""

REASON_REQUIRED_BODY = """
DECLARE
  old_value text;
  new_value text := to_jsonb(NEW) ->> TG_ARGV[0];
  picked text := nullif(current_setting('cucumber.reason_code', true), '');
  needed text;
  picked_list text;
BEGIN
  IF TG_OP = 'UPDATE' THEN  -- a new row has no old value: off at birth counts
    old_value := to_jsonb(OLD) ->> TG_ARGV[0];
  END IF;
  IF new_value IS NOT DISTINCT FROM old_value THEN
    RETURN NEW;
  END IF;
  FOR i IN 1 .. TG_NARGS / 2 LOOP
    IF new_value = TG_ARGV[2 * i - 1] THEN
      needed := TG_ARGV[2 * i];
    END IF;
  END LOOP;
  IF needed IS NULL THEN
    RETURN NEW;  -- not switched off
  END IF;
  IF picked IS NULL THEN
    RAISE EXCEPTION '% % = % needs a reason', TG_TABLE_NAME, TG_ARGV[0], new_value
      USING ERRCODE = 'restrict_violation', CONSTRAINT = 'reason_required';
  END IF;
  -- Only `cucumber_anonymise` uses the PDPA reason, which no list offers.
  SELECT applies_to INTO picked_list FROM public.reasons
   WHERE code = picked AND (active OR code = 'deactivate_pdpa_request');
  IF picked_list IS DISTINCT FROM needed THEN
    RAISE EXCEPTION 'reason % is not on the % list', picked, needed
      USING ERRCODE = 'restrict_violation', CONSTRAINT = 'reason_wrong_list';
  END IF;
  RETURN NEW;
END
"""

TRUNCATE_NOTICED_BODY = """
BEGIN
  INSERT INTO public.audit_log (actor_id, table_name, row_pk, action, via)
  VALUES (NULL, TG_TABLE_NAME, '', 'truncate', 'sql as ' || session_user);
  RETURN NULL;
END
"""

AUDIT_LOG_STAMP_BODY = """
BEGIN
  NEW.at := now();
  NEW.db_user := session_user;
  RETURN NEW;
END
"""

SYSTEM_USERNAME_FIXED_BODY = """
BEGIN
  IF OLD.username = 'system@cucumber.invalid'
     AND NEW.username IS DISTINCT FROM OLD.username THEN
    RAISE EXCEPTION 'the System account can''t be renamed'
      USING ERRCODE = 'restrict_violation',
            CONSTRAINT = 'auth_user_system_username_fixed';
  END IF;
  RETURN NEW;
END
"""

AUDIT_FUNCTIONS = {
    "cucumber_audit": AUDIT_BODY,
    "cucumber_reason_required": REASON_REQUIRED_BODY,
    "cucumber_truncate_noticed": TRUNCATE_NOTICED_BODY,
    "audit_log_stamp": AUDIT_LOG_STAMP_BODY,
    "cucumber_system_username_fixed": SYSTEM_USERNAME_FIXED_BODY,
}


def audit_function(name: str, body: str) -> Sql:
    return Sql(
        forward=(
            f"CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql"
            f" SET search_path = {SEARCH_PATH} AS $${body}$$;"
        ),
        reverse=f"DROP FUNCTION {name}();",
    )


@dataclass(frozen=True)
class Audited:
    """How `cucumber_audit` reads one table (U0.7 design §4.1)."""

    table: str
    key: str
    ignored: tuple[str, ...] = ()
    masked: tuple[str, ...] = ()
    deletes: bool = False  # a role, a flag or a flag's group removed

    @property
    def events(self) -> str:
        return "INSERT OR UPDATE OR DELETE" if self.deletes else "INSERT OR UPDATE"

    @property
    def arguments(self) -> tuple[str, str, str]:
        return (self.key, ",".join(self.ignored), ",".join(self.masked))


@dataclass(frozen=True)
class SwitchOff:
    """A column whose "off" values need a reason from a list (design §4.2)."""

    table: str
    column: str
    offs: tuple[tuple[str, str], ...]  # (off value, reason list)

    @property
    def arguments(self) -> tuple[str, ...]:
        return (self.column, *(part for off in self.offs for part in off))


def quoted(arguments: tuple[str, ...]) -> str:
    """Trigger arguments as SQL literals; they are this module's constants."""
    return ", ".join("'" + argument.replace("'", "''") + "'" for argument in arguments)


def audit(spec: Audited) -> Sql:
    """Write one audit row per change to `spec.table` (AC4)."""
    name = f"{spec.table}_audit"
    return Sql(
        forward=(
            f"CREATE TRIGGER {name} AFTER {spec.events} ON {spec.table}"
            f" FOR EACH ROW EXECUTE FUNCTION cucumber_audit({quoted(spec.arguments)});"
        ),
        reverse=f"DROP TRIGGER {name} ON {spec.table};",
    )


def reason_required(spec: SwitchOff) -> Sql:
    """No switching off without a reason from the right list (AC11)."""
    name = f"{spec.table}_reason_required"
    return Sql(
        forward=(
            f"CREATE TRIGGER {name} BEFORE INSERT OR UPDATE ON {spec.table}"
            " FOR EACH ROW"
            f" EXECUTE FUNCTION cucumber_reason_required({quoted(spec.arguments)});"
        ),
        reverse=f"DROP TRIGGER {name} ON {spec.table};",
    )


def truncate_noticed(table: str) -> Sql:
    """An emptied table leaves a `truncate` row (design §4.4)."""
    name = f"{table}_truncate_noticed"
    return Sql(
        forward=(
            f"CREATE TRIGGER {name} AFTER TRUNCATE ON {table}"
            " FOR EACH STATEMENT EXECUTE FUNCTION cucumber_truncate_noticed();"
        ),
        reverse=f"DROP TRIGGER {name} ON {table};",
    )


# Design §4.1, by column name (review L6). core 0006 makes these triggers and
# the guard check expects them; change one with a new migration and here.
REFERENCE_LISTS = ("genera", "stages", "media_codes", "locations", "reasons")
PERSONAL_COLUMNS = ("password", "username", "email", "first_name", "last_name")
BATCH_PROJECTION = (
    "live_count", "quarantined", "stage_code", "status", "closed_at", "voided_at",
)  # fmt: skip
AUDITED_TABLES = (
    Audited("plants", "id", ignored=("name_key",)),
    Audited("batches", "id", ignored=BATCH_PROJECTION),
    *(Audited(table, "code") for table in REFERENCE_LISTS),
    Audited("vendors", "zoho_contact_id", ignored=("synced_at",)),
    Audited("auth_user", "id", ignored=("last_login",), masked=PERSONAL_COLUMNS),
    Audited("auth_user_groups", "user_id", ignored=("id",), deletes=True),
    Audited("waffle_flag", "id", ignored=("modified",), deletes=True),
    Audited("waffle_flag_groups", "flag_id", ignored=("id",), deletes=True),
)

# Design §4.2: (off value, reason list) per column.
SWITCH_OFFS = (
    *(
        SwitchOff(table, "active", (("false", "archive"),))
        for table in (*REFERENCE_LISTS, "vendors")
    ),
    SwitchOff("auth_user", "is_active", (("false", "deactivate"),)),
    SwitchOff("plants", "status", (("retired", "retire"), ("voided", "void"))),
)

# The append-only tables (core 0003's INSERT_ONLY) and the audited ones.
APPEND_ONLY_TABLES = (
    "events", "operations", "event_reviews", "plant_status_changes", "skus",
    "audit_log",
)  # fmt: skip
TRUNCATE_NOTICED_TABLES = tuple(
    dict.fromkeys([*APPEND_ONLY_TABLES, *(spec.table for spec in AUDITED_TABLES)])
)

AUDIT_LOG_STAMP = Sql(
    forward=(
        "CREATE TRIGGER audit_log_stamp BEFORE INSERT ON audit_log"
        " FOR EACH ROW EXECUTE FUNCTION audit_log_stamp();"
    ),
    reverse="DROP TRIGGER audit_log_stamp ON audit_log;",
)

# G4 review, item 7: `audited()` finds System by its name.
SYSTEM_USERNAME_FIXED = Sql(
    forward=(
        "CREATE TRIGGER auth_user_system_username_fixed BEFORE UPDATE ON auth_user"
        " FOR EACH ROW EXECUTE FUNCTION cucumber_system_username_fixed();"
    ),
    reverse="DROP TRIGGER auth_user_system_username_fixed ON auth_user;",
)

# ------------------------------------------------- ids from a sequence (U0.8 §5.1)
#
# `plants.id`, `batches.id` and `events.id` have no default: a BEFORE INSERT
# trigger takes the number from the table's sequence, and only the owner may
# choose one (the V.2 import, Q1). Any later migration that alters one of
# these `id` columns must keep the trigger and the sequence, or the guard
# check reports it (U0.8 design §6).

ID_TABLES = ("plants", "batches", "events")  # the app's lock order
ID_FIXED_TABLES = ("plants", "batches")  # events is append-only already

ID_FROM_SEQUENCE_BODY = """
BEGIN
  IF NEW.id IS NULL THEN
    NEW.id := nextval(TG_ARGV[0]);
  ELSIF session_user = 'cucumber_owner' THEN
    -- The V.2 import keeps plant numbers already in use (Q1): move the
    -- generator past them, so the next new row never collides. The lock
    -- keeps app saves (and a second import) from taking numbers between
    -- the read and the setval (review M1).
    EXECUTE format('LOCK TABLE public.%I IN SHARE ROW EXCLUSIVE MODE', TG_TABLE_NAME);
    IF NEW.id > coalesce(pg_sequence_last_value(TG_ARGV[0]::regclass), 0) THEN
      PERFORM setval(TG_ARGV[0], NEW.id);
    END IF;
  ELSE
    RAISE EXCEPTION '% ids are given by the database, not chosen', TG_TABLE_NAME
      USING ERRCODE = 'restrict_violation',
            CONSTRAINT = TG_TABLE_NAME || '_id_from_sequence';
  END IF;
  RETURN NEW;
END
"""

ID_FIXED_BODY = """
BEGIN
  IF NEW.id IS DISTINCT FROM OLD.id THEN
    RAISE EXCEPTION '% id % can''t be changed', TG_TABLE_NAME, OLD.id
      USING ERRCODE = 'restrict_violation', CONSTRAINT = TG_TABLE_NAME || '_id_fixed';
  END IF;
  RETURN NEW;
END
"""

ID_FUNCTIONS = {
    "cucumber_id_from_sequence": ID_FROM_SEQUENCE_BODY,
    "cucumber_id_fixed": ID_FIXED_BODY,
}


def sequence_of(table: str) -> str:
    """The sequence that hands out `table.id`, schema-qualified."""
    return f"public.{table}_id_seq"


def id_from_sequence(table: str) -> Sql:
    """New ids come from the sequence; only the owner may choose one (AC13)."""
    name = f"{table}_id_from_sequence"
    return Sql(
        forward=(
            f"CREATE TRIGGER {name} BEFORE INSERT ON {table} FOR EACH ROW"
            " EXECUTE FUNCTION"
            f" cucumber_id_from_sequence({quoted((sequence_of(table),))});"
        ),
        reverse=f"DROP TRIGGER {name} ON {table};",
    )


def id_fixed(table: str) -> Sql:
    """An id never changes, for any role (review H1)."""
    return _trigger(table, "id_fixed", "BEFORE UPDATE", "cucumber_id_fixed")


# Design §3.1 (review M4): what `audited(SYSTEM, via="migration")` sets, as
# SQL, for a data migration that changes an audited table.
AS_SYSTEM_SQL = """
SELECT set_config('cucumber.actor_id',
  (SELECT id::text FROM auth_user WHERE username = 'system@cucumber.invalid'),
  true);
SELECT set_config('cucumber.via', 'migration', true);
"""
