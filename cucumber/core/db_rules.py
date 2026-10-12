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
