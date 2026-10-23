"""U0.8 AC15, review M3: only `cucumber/ids/` builds an ID (design §12).

An AST scan of `cucumber/**/*.py`, leaving out `cucumber/ids/`, migrations
and tests, plus a text scan of the templates. It reads string literals and
f-strings (docstrings and comments are left alone) and fails on:

- the literal prefixes `PLT-`, `BAT-`, `EVT-` and `· B`;
- any zero-padded number format: `0Nd` in an f-string spec (nested specs
  included), `"%0Nd"`, `"{:0Nd}".format`, and `stringformat:"0Nd"`.

Anything allowed outside `ids/` goes on `ALLOWED`, with the reason.
"""

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

CODE = Path(__file__).resolve().parents[2]  # the `cucumber` package
LEFT_OUT = ("ids", "migrations", "tests")
ID_PREFIXES = ("PLT-", "BAT-", "EVT-", "· B")
PERCENT_PADDED = re.compile(r"%0\d+d")
FORMAT_PADDED = re.compile(r"\{[^{}]*:0\d+d\}")
TEMPLATE_PADDED = re.compile(r"""stringformat:\s*["']0\d+d["']""")
SPEC_PADDED = re.compile(r"^0[0-9N]+d$")  # N stands for a nested {…}

# "<path relative to cucumber/>:<line>" → why it may build an ID itself.
ALLOWED: dict[str, str] = {}


def scanned_python() -> list[Path]:
    return sorted(
        path
        for path in CODE.rglob("*.py")
        if not set(path.relative_to(CODE).parts[:-1]) & set(LEFT_OUT)
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


def spec_text(spec: ast.expr) -> str:
    """A format spec as text, with each nested {…} written as N."""
    if not isinstance(spec, ast.JoinedStr):
        return ""
    return "".join(
        str(part.value) if isinstance(part, ast.Constant) else "N"
        for part in spec.values
    )


def problems_in_text(text: str) -> Iterator[str]:
    for prefix in ID_PREFIXES:
        if prefix in text:
            yield f"the ID prefix {prefix!r}"
    for pattern in (PERCENT_PADDED, FORMAT_PADDED):
        for match in pattern.finditer(text):
            yield f"the zero-padded format {match.group()!r}"


def problems_in_source(source: str) -> list[tuple[int, str]]:
    """(line, what) for every ID built in this Python source."""
    tree = ast.parse(source)
    skip = docstrings(tree)
    found = []
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found += [(node.lineno, what) for what in problems_in_text(node.value)]
        if isinstance(node, ast.FormattedValue) and node.format_spec is not None:
            spec = spec_text(node.format_spec)
            if SPEC_PADDED.match(spec):
                found.append((node.lineno, f"the zero-padded f-string spec {spec!r}"))
    return found


def problems_in_template(text: str) -> list[tuple[int, str]]:
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        found += [(number, what) for what in problems_in_text(line)]
        found += [
            (number, f"the zero-padded filter {match.group()!r}")
            for match in TEMPLATE_PADDED.finditer(line)
        ]
    return found


def everything_found() -> list[str]:
    found = []
    for path in scanned_python():
        source = path.read_text(encoding="utf-8")
        found += [
            f"{path.relative_to(CODE)}:{line}: {what}"
            for line, what in problems_in_source(source)
        ]
    for path in scanned_templates():
        text = path.read_text(encoding="utf-8")
        found += [
            f"{path.relative_to(CODE)}:{line}: {what}"
            for line, what in problems_in_template(text)
        ]
    return [item for item in found if item.split(": ", 1)[0] not in ALLOWED]


# ------------------------------------------------------------------ AC15
def test_ac15_no_module_outside_ids_builds_an_id_itself() -> None:
    assert everything_found() == []


def test_ac15_the_scan_reads_the_app_code_and_leaves_out_ids_and_tests() -> None:
    scanned = {str(path.relative_to(CODE)) for path in scanned_python()}

    assert "plants/services.py" in scanned
    assert "events/services.py" in scanned
    assert not [path for path in scanned if path.startswith("ids/")]
    folders = {part for path in scanned for part in Path(path).parts[:-1]}
    assert not folders & {"tests", "migrations"}


def test_ac15_every_allowed_place_says_why() -> None:
    assert all(reason.strip() for reason in ALLOWED.values())


# ------------------------------------------------- the scan finds them all
CAUGHT = {
    "plant prefix": 'label = "PLT-" + str(number)',
    "batch prefix in an f-string": 'label = f"BAT-{number}"',
    "event prefix": "PREFIX = 'EVT-'",
    "short name separator": 'name = sku + " · B" + str(seq)',
    "f-string padding": 'text = f"{number:05d}"',
    "nested f-string padding": 'text = f"{genus}{number:0{DIGITS}d}"',
    "percent padding": 'text = "%03d" % number',
    "str.format padding": 'text = "{:04d}".format(number)',
    "named str.format padding": 'text = "{n:03d}".format(n=number)',
}
LEFT_ALONE = {
    "docstring": 'def f():\n    """Gives PLT-0042, padded with f"{n:04d}"."""\n',
    "comment": "x = 1  # PLT-0042, %04d\n",
    "unpadded format": 'text = f"{number:5d}"',
    "a width that isn't a number": 'text = f"{number:>4}"',
}


@pytest.mark.parametrize("name", sorted(CAUGHT))
def test_ac15_the_scan_catches(name: str) -> None:
    assert problems_in_source(CAUGHT[name]) != []


@pytest.mark.parametrize("name", sorted(LEFT_ALONE))
def test_ac15_the_scan_leaves_alone(name: str) -> None:
    assert problems_in_source(LEFT_ALONE[name]) == []


@pytest.mark.parametrize(
    "line",
    ['{{ batch.plant_seq|stringformat:"03d" }}', "<td>PLT-{{ plant.pk }}</td>"],
)
def test_ac15_the_template_scan_catches(line: str) -> None:
    assert problems_in_template(line) != []
