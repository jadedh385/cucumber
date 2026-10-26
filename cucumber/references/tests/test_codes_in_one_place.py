"""U0.9 AC22: only `cucumber/references/` names a list code (design §8).

An AST scan of `cucumber/**/*.py`, leaving out `cucumber/references/`,
migrations and tests, as U0.8's ID scan does. It reads string literals and
f-string parts (docstrings and comments are left alone) and fails on a literal
equal to a stage or location code, an event action or a count unit.

Five actions and `plant` are also ordinary words with other meanings in the
code, so `ALLOWED` lists each place that may use one, with the reason. It is
keyed by file and literal, not line, so an edit nearby doesn't break it.

Templates: a plain text search would hit page words (`out`, `count`, `lab`),
so only quoted strings inside `{% … %}` and `{{ … }}` and `value="…"`
attributes are read (review L6).

The test lists the codes itself, and checks them against `fixed.py` and the
seeded tables, so a new code can't slip past the scan.
"""

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from cucumber.core.tests.rows import fetch_all
from cucumber.references.fixed import Action, CountUnit

CODE = Path(__file__).resolve().parents[2]  # the `cucumber` package
LEFT_OUT_PACKAGE = "references"
LEFT_OUT_FOLDERS = ("migrations", "tests")

STAGES = ("S0", "P0", "P1", "P2", "A1", "P4", "P3", "T1", "C0")
LOCATIONS = ("lab", "nursery")
ACTIONS = (
    "intake", "subculture", "stage_change", "count", "contamination", "split",
    "quarantine", "release", "transfer", "out", "loss", "close", "correction",
    "void",
)  # fmt: skip
COUNT_UNITS = ("plant", "vessel", "mg")
KIND = {
    **dict.fromkeys(STAGES, "stage"),
    **dict.fromkeys(LOCATIONS, "location"),
    **dict.fromkeys(ACTIONS, "event action"),
    **dict.fromkeys(COUNT_UNITS, "count unit"),
}

ORIGIN = "the batch origin, its own list (U0.2a); it matches the action that made it"
FIELD = "the `plant` field of a model, not a count unit"
# (path relative to cucumber/, literal) → why that file may use it (design §8).
ALLOWED: dict[tuple[str, str], str] = {
    **{
        ("batches/models.py", origin): ORIGIN
        for origin in ("intake", "subculture", "split", "quarantine", "transfer")
    },
    ("events/projection.py", "quarantine"): (
        "QUARANTINE_ORIGIN, a batch origin; importing BatchOrigin would bring app"
        " models into a module of plain values (review L2)"
    ),
    ("batches/models.py", "plant"): FIELD,
    ("plants/models.py", "plant"): FIELD,
    ("ids/lookup.py", "plant"): FIELD + " (select_related)",
    ("ids/reading.py", "plant"): "the ID kind (U0.8 reading.Kind), not a count unit",
    ("core/guards.py", "plant"): "a word in a guard message (every new plant)",
    ("core/db_rules.py", "void"): "the `void` reason list, not the action",
    ("events/services.py", "out"): "an event's direction, not the action",
}

TEMPLATE_TAG = re.compile(r"\{%.*?%\}|\{\{.*?\}\}", re.DOTALL)
QUOTED = re.compile(r"""(["'])(.*?)\1""", re.DOTALL)
VALUE_ATTRIBUTE = re.compile(r"""\bvalue\s*=\s*(["'])(.*?)\1""", re.DOTALL)


def scanned_python() -> list[Path]:
    return sorted(
        path
        for path in CODE.rglob("*.py")
        if path.relative_to(CODE).parts[0] != LEFT_OUT_PACKAGE
        and not set(path.relative_to(CODE).parts[:-1]) & set(LEFT_OUT_FOLDERS)
    )


def scanned_templates() -> list[Path]:
    return sorted(CODE.rglob("templates/**/*.html"))


def docstrings(tree: ast.AST) -> set[int]:
    """The ids of the docstring nodes, which the scan leaves alone."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            body = node.body
            if body and isinstance(body[0], ast.Expr):
                found.add(id(body[0].value))
    return found


def codes_in_source(source: str) -> list[tuple[int, str]]:
    """(line, literal) for every literal in this Python source that is a code."""
    tree = ast.parse(source)
    skip = docstrings(tree)
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if id(node) not in skip
        and isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value in KIND
    ]


def quoted_in_template(text: str) -> Iterator[tuple[int, str]]:
    """(line, text) of each quoted string in a tag and each `value=` attribute."""
    for tag in TEMPLATE_TAG.finditer(text):
        for quoted in QUOTED.finditer(tag.group()):
            yield text.count("\n", 0, tag.start() + quoted.start()) + 1, quoted[2]
    for attribute in VALUE_ATTRIBUTE.finditer(text):
        yield text.count("\n", 0, attribute.start()) + 1, attribute[2]


def codes_in_template(text: str) -> list[tuple[int, str]]:
    return [(line, value) for line, value in quoted_in_template(text) if value in KIND]


def everything_found() -> list[tuple[str, int, str]]:
    """(path, line, literal) for every code the scan finds, allowed or not."""
    found = []
    for path in scanned_python():
        source = path.read_text(encoding="utf-8")
        where = str(path.relative_to(CODE))
        found += [(where, line, code) for line, code in codes_in_source(source)]
    for path in scanned_templates():
        text = path.read_text(encoding="utf-8")
        where = str(path.relative_to(CODE))
        found += [(where, line, code) for line, code in codes_in_template(text)]
    return found


def report(found: list[tuple[str, int, str]]) -> list[str]:
    return [f"{where}:{line}: the {KIND[code]} {code!r}" for where, line, code in found]


# ------------------------------------------------------------------ AC22
def test_ac22_no_module_outside_references_names_a_list_code() -> None:
    not_allowed = [
        (where, line, code)
        for where, line, code in everything_found()
        if (where, code) not in ALLOWED
    ]

    assert report(not_allowed) == []


def test_ac22_every_allowed_place_says_why() -> None:
    assert [place for place, reason in ALLOWED.items() if not reason.strip()] == []


def test_ac22_every_allowed_place_is_still_there() -> None:
    """An entry that no longer matches anything is taken off the list."""
    found = {(where, code) for where, _, code in everything_found()}

    assert sorted(set(ALLOWED) - found) == []


def test_ac22_the_scan_reads_the_app_code_and_leaves_out_references_and_tests() -> None:
    scanned = {str(path.relative_to(CODE)) for path in scanned_python()}

    assert "events/projection.py" in scanned
    assert "batches/models.py" in scanned
    assert not [path for path in scanned if path.startswith("references/")]
    folders = {part for path in scanned for part in Path(path).parts[:-1]}
    assert not folders & set(LEFT_OUT_FOLDERS)


def test_ac22_the_scan_reads_every_template() -> None:
    scanned = {str(path.relative_to(CODE)) for path in scanned_templates()}

    assert "accounts/templates/base.html" in scanned


# ------------------------------------------------- the codes it looks for
def test_ac22_the_scan_knows_every_event_action_and_count_unit() -> None:
    assert sorted(ACTIONS) == sorted(Action.values)
    assert sorted(COUNT_UNITS) == sorted(CountUnit.values)


@pytest.mark.django_db
def test_ac22_the_scan_knows_every_stage_and_location() -> None:
    """The seeded tables; S0 comes with references 0008 (AC1)."""
    stages = [str(row[0]) for row in fetch_all("SELECT code FROM stages")]
    locations = [str(row[0]) for row in fetch_all("SELECT code FROM locations")]

    assert sorted(stages) == sorted(STAGES)
    assert sorted(locations) == sorted(LOCATIONS)


# ------------------------------------------------- the scan finds them all
CAUGHT = {
    "a stage": 'if stage == "P4":\n    pass\n',
    "a location": "LAB = 'lab'",
    "an action": 'kind = "stage_change"',
    "a count unit": 'unit = "vessel"',
    "an f-string part": 'text = f"{qty}mg"',
    "a default argument": 'def f(stage="S0"):\n    """Doc."""\n',
    "a list of them": 'ORDER = ["P0", "P1", "P2"]',
}
LEFT_ALONE = {
    "a docstring": 'def f():\n    """Moves the batch to P4 in the lab."""\n',
    "a comment": "x = 1  # P4, lab, count\n",
    "a longer string": 'text = "count the plants in the lab"',
    "another case": 'label = "Lab"',
    "a code inside a word": 'name = "lab_notes"',
}


@pytest.mark.parametrize("name", sorted(CAUGHT))
def test_ac22_the_scan_catches(name: str) -> None:
    assert codes_in_source(CAUGHT[name]) != []


@pytest.mark.parametrize("name", sorted(LEFT_ALONE))
def test_ac22_the_scan_leaves_alone(name: str) -> None:
    assert codes_in_source(LEFT_ALONE[name]) == []


TEMPLATE_CAUGHT = {
    "an if tag": '{% if batch.stage_code == "P4" %}potted{% endif %}',
    "single quotes": "{% if location == 'nursery' %}",
    "a variable tag": '{{ "lab" }}',
    "a filter argument": '{{ batch.action|default:"count" }}',
    "a value attribute": '<option value="vessel">Vessel</option>',
    "a tag over two lines": '{% if stage ==\n   "S0" %}',
}
TEMPLATE_LEFT_ALONE = {
    "page words": "<p>Count the plants in the lab, then close out.</p>",
    "a url name": "{% url 'accounts:home' %}",
    "a value from a variable": '<input value="{{ batch.stage_code }}">',
    "a class attribute": '<div class="lab">',
    "a word in a tag": "{% trans 'Lab' %}",
}


@pytest.mark.parametrize("name", sorted(TEMPLATE_CAUGHT))
def test_ac22_the_template_scan_catches(name: str) -> None:
    assert codes_in_template(TEMPLATE_CAUGHT[name]) != []


@pytest.mark.parametrize("name", sorted(TEMPLATE_LEFT_ALONE))
def test_ac22_the_template_scan_leaves_alone(name: str) -> None:
    assert codes_in_template(TEMPLATE_LEFT_ALONE[name]) == []


def test_ac22_the_template_scan_gives_the_line() -> None:
    text = "<p>\n</p>\n{% if stage == 'P4' %}\n<option value=\"mg\">"

    assert sorted(codes_in_template(text)) == [(3, "P4"), (4, "mg")]
