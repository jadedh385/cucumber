"""AC3, AC14: the matrix is written once, as the spec says, and nothing else decides.

`SPEC` is the spec's table typed in again by hand (u0.6-spec.md, "Permission
matrix"), so a wrong cell in `accounts/permissions.py` can't pass by being
checked against itself. Every other U0.6 test reads `MATRIX`.
"""

import re
from pathlib import Path

import pytest

from cucumber.accounts.permissions import (
    MATRIX,
    Built,
    Permission,
    Role,
    may,
    row_of,
)
from cucumber.core.refusals import MESSAGES

A, S, T, R = Role.ADMIN, Role.SUPERVISOR, Role.TECH, Role.READ_ONLY
NO_ROLE = None
ROLES_AND_NONE: list[Role | None] = [*Role, NO_ROLE]

# The spec's rows, in its order: who may, and where it is built today.
SPEC: list[tuple[Permission, set[Role | None], Built]] = [
    (Permission.LOG_WORK, {A, S, T}, Built.SERVICES),
    (Permission.SPLIT_CLOSE_LOSS, {A, S, T}, Built.SERVICES),
    (Permission.RELEASE_QUARANTINE, {A, S, T}, Built.SERVICES),
    (Permission.UNDO_OWN, {A, S, T}, Built.SERVICES),
    (Permission.REVIEW_EVENTS, {A, S}, Built.SERVICES),
    (Permission.VOID_OR_CORRECT, {A, S}, Built.SERVICES),
    (Permission.REVIEW_VOIDS, {A}, Built.SERVICES),
    (Permission.ENTER_FOR_OTHERS, {A, S}, Built.SERVICES),
    (Permission.PLANT_LIFECYCLE, {A}, Built.SERVICES),
    (Permission.RECLASSIFY_GENUS, {A}, Built.SERVICES),
    (Permission.ZOHO_LINK, {A}, Built.LATER),
    (Permission.EDIT_REFERENCE_LISTS, {A}, Built.LATER),
    (Permission.SEE_ZOHO_REFS, {A}, Built.LATER),
    (Permission.VIEW_DASHBOARDS, {A, S, T, R}, Built.LATER),
    (Permission.MANAGE_USERS, {A}, Built.BOTH),
    (Permission.OWN_ACCOUNT, {A, S, T, R, NO_ROLE}, Built.PAGES),
]

ROOT = Path(__file__).resolve().parents[3]
SEARCHED = [ROOT / "cucumber", ROOT / "scripts", ROOT / "uat", ROOT / "e2e"]


def python_files() -> list[Path]:
    return sorted(
        path
        for folder in SEARCHED
        for path in folder.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


# ----------------------------------------------------------- the rows (AC3)
def test_the_matrix_has_the_spec_s_rows_in_its_order() -> None:
    assert [row.permission for row in MATRIX] == [spec[0] for spec in SPEC]


@pytest.mark.parametrize(("permission", "allowed", "built"), SPEC)
def test_each_row_allows_the_spec_s_roles(
    permission: Permission, allowed: set[Role | None], built: Built
) -> None:
    row = row_of(permission)

    assert set(row.allowed) == allowed
    assert row.built == built
    assert row.label


def test_every_permission_has_exactly_one_row() -> None:
    assert sorted(row.permission for row in MATRIX) == sorted(Permission)


def test_the_roles_are_the_four_group_names() -> None:
    assert sorted(Role) == ["admin", "read_only", "supervisor", "tech"]


def test_a_role_equals_its_group_name() -> None:
    """`"admin" == Role.ADMIN`, so code reading group names still matches."""
    group_names: list[str] = ["admin", "read_only"]
    assert group_names == [Role.ADMIN, Role.READ_ONLY]


def test_roles_are_steps_each_allowing_what_the_one_below_does() -> None:
    """Spec Q1: Admin ⊇ Supervisor ⊇ Tech ⊇ Read Only, row by row."""
    steps = [R, T, S, A]
    for row in MATRIX:
        for lower, higher in zip(steps, steps[1:], strict=False):
            if lower in row.allowed:
                assert higher in row.allowed, (row.permission, lower, higher)


def test_every_refusal_a_row_names_has_a_message_for_staff() -> None:
    for row in MATRIX:
        assert row.refused_as in MESSAGES, row.permission


def test_only_entering_for_others_refuses_with_its_own_rule() -> None:
    """A Tech saving someone else's work meets N7's rule, not the role's."""
    own_rules = {row.permission: row.refused_as for row in MATRIX}

    assert own_rules.pop(Permission.ENTER_FOR_OTHERS) == "staff_must_be_you"
    assert set(own_rules.values()) == {"role_not_allowed"}


# ------------------------------------------------------- may(), generated (AC14)
@pytest.mark.parametrize("role", ROLES_AND_NONE, ids=str)
@pytest.mark.parametrize(
    ("permission", "allowed"), [(row.permission, row.allowed) for row in MATRIX]
)
def test_may_answers_each_cell_of_the_matrix(
    permission: Permission, allowed: frozenset[Role | None], role: Role | None
) -> None:
    assert may(role, permission) is (role in allowed)


def test_no_role_may_only_use_its_own_account() -> None:
    assert [row.permission for row in MATRIX if may(None, row.permission)] == [
        Permission.OWN_ACCOUNT
    ]


def test_read_only_may_change_nothing() -> None:
    assert {row.permission for row in MATRIX if may(R, row.permission)} == {
        Permission.VIEW_DASHBOARDS,
        Permission.OWN_ACCOUNT,
    }


# ------------------------------------------------- nothing else decides (AC3)
# Ways to ask "which role?" without the matrix. Inside accounts/ they are the
# matrix's own tools; events/reviews.py keeps rule 10 (design §4.2).
ROLE_LOOK_UPS = re.compile(
    r"\bhas_role\(|\bmembers_of\(|groups__name|"
    r"""name\s*=\s*["'](?:admin|supervisor|tech|read_only)["']"""
)
MAY_ASK_ROLES = ("cucumber/accounts/", "cucumber/events/reviews.py")


def test_no_code_outside_accounts_looks_up_a_role_by_itself() -> None:
    found = [
        f"{relative(path)}:{number}: {line.strip()}"
        for path in python_files()
        if not relative(path).startswith(MAY_ASK_ROLES)
        and "/tests/" not in relative(path)
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if ROLE_LOOK_UPS.search(line)
    ]

    assert found == []


# Django's groups.add()/set() on a user is ON CONFLICT DO NOTHING on
# PostgreSQL: a second role would be skipped, not refused (design §6.2).
# A flag's groups (`flag.groups`) are not roles and may use them.
GROUPS_ADD_OR_SET = re.compile(r"(\w+)\.groups\.(?:add|set)\(")


def test_nothing_gives_a_user_a_group_with_add_or_set() -> None:
    found = [
        f"{relative(path)}:{number}: {line.strip()}"
        for path in python_files()
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        for match in GROUPS_ADD_OR_SET.finditer(line)
        if match.group(1) != "flag"
    ]

    assert found == []
