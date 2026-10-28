"""U0.10a AC9, AC19, AC20: the kit's tags and includes (design §7.4, §7.6, §7.7).

`item_text` shows an item on a record, switched off or not. `kit_table` is
one `<table>` (cards below `lg`, by CSS), or the empty state when there are
no rows. `kit/detail.html` is a title, a line, and the facts as a `<dl>`.
The template decides layout only; text from the database is escaped.
"""

import re

import pytest
from django.template import Context, Template

from cucumber.core.kit import Column, Detail, Empty, Fact, Row, Table, item_text
from cucumber.core.tests.fake_translation import wrapped, wrapping_translation
from cucumber.references.lists import ListName
from cucumber.references.reading import Item, all_items, item
from cucumber.references.tests.support import switched_off

STAGES = {
    "P1": Item("P1", "Multiplication", True, 2),
    "P3": Item("P3", "Transport", False, None),
}
CONTAINERS = {
    "magenta_box": Item("magenta_box", "Magenta box", True),
    "jar": Item("jar", "Jar", False),
}
MEDIA = {"M001": Item("M001", "M001", True), "M003": Item("M003", "M003", False)}
ACTIONS = {"stage_change": Item("stage_change", "Stage Change", True)}


def render(source: str, **context: object) -> str:
    return Template("{% load kit %}" + source).render(Context(context))


def squeezed(html: str) -> str:
    return " ".join(html.split())


# ------------------------------------------------------------------ item_text
@pytest.mark.parametrize(
    ("name", "found", "code", "shown"),
    [
        (ListName.STAGES, STAGES, "P1", "P1 · Multiplication"),
        (ListName.STAGES, STAGES, "P3", "P3 · Transport (switched off)"),
        (ListName.CONTAINER_TYPES, CONTAINERS, "magenta_box", "Magenta box"),
        (ListName.CONTAINER_TYPES, CONTAINERS, "jar", "Jar (switched off)"),
        (ListName.MEDIA_CODES, MEDIA, "M001", "M001"),
        (ListName.MEDIA_CODES, MEDIA, "M003", "M003 (switched off)"),
        (ListName.ACTIONS, ACTIONS, "stage_change", "Stage Change"),
        (ListName.STAGES, STAGES, "Z9", "Z9"),
        (ListName.CONTAINER_TYPES, {}, "old_tub", "old_tub"),
    ],
    ids=[
        "active, code shown",
        "switched off, code shown",
        "active, label only",
        "switched off, label only",
        "labelled with its code",
        "labelled with its code, switched off",
        "fixed list",
        "no list holds it",
        "empty list",
    ],
)
def test_an_item_on_a_record_reads_as_its_list_shows_it(
    name: ListName, found: dict[str, Item], code: str, shown: str
) -> None:
    assert item_text(name, found, code) == shown


def test_one_item_reads_the_same_as_from_all_items() -> None:
    assert item_text(ListName.STAGES, STAGES["P3"], "P3") == (
        "P3 · Transport (switched off)"
    )


def test_no_item_reads_as_its_code() -> None:
    """Review L11: the tag takes the code, so `None` can still show it."""
    assert item_text(ListName.STAGES, None, "P9") == "P9"


def test_switched_off_is_translated() -> None:
    with wrapping_translation():
        shown = item_text(ListName.CONTAINER_TYPES, CONTAINERS, "jar")

    assert wrapped("(switched off)") in shown


@pytest.mark.django_db
def test_the_readers_feed_item_text() -> None:
    switched_off(ListName.STAGES, "P2")

    stages = all_items(ListName.STAGES)

    assert item_text(ListName.STAGES, stages, "P2") == "P2 · Growth (switched off)"
    assert item_text(ListName.GENERA, item(ListName.GENERA, "PHL"), "PHL") == (
        "PHL · Philodendron"
    )


def test_the_tag_names_the_list_and_takes_all_items_or_one() -> None:
    source = '{% item_text "stages" items "P3" %}|{% item_text "stages" one "P1" %}'

    html = render(source, items=STAGES, one=STAGES["P1"])

    assert html == "P3 · Transport (switched off)|P1 · Multiplication"


def test_the_tag_escapes_a_label() -> None:
    """Labels are typed by the Admin."""
    html = render(
        '{% item_text "container_types" items "tub" %}',
        items={"tub": Item("tub", "<b>Tub</b>", True)},
    )

    assert html == "&lt;b&gt;Tub&lt;/b&gt;"


# ------------------------------------------------------------------ kit_table
NO_STAFF = Empty("No staff yet. Add the first person.", "Add", "/staff/new/")
STAFF_TABLE = Table(
    columns=(Column("Name", is_main=True), Column("Email"), Column("Role")),
    rows=(
        Row(("Gene", "gene@example.com", "Tech"), "/staff/3/"),
        Row(("Pim", "pim@example.com", "Supervisor"), "/staff/4/"),
    ),
    empty=NO_STAFF,
)


def table_html(table: Table) -> str:
    return render("{% kit_table table %}", table=table)


def test_a_table_is_one_table_with_its_column_labels_in_order() -> None:
    html = table_html(STAFF_TABLE)

    assert html.count("<table") == 1
    headers = [
        squeezed(cell) for cell in re.findall(r"<th\b[^>]*>(.*?)</th>", html, re.S)
    ]
    assert headers == ["Name", "Email", "Role"]


def test_each_row_shows_its_cells_in_order() -> None:
    rows = re.findall(r"<tr\b[^>]*>.*?</tr>", table_html(STAFF_TABLE), re.S)
    body = [row for row in rows if "<td" in row]

    assert len(body) == 2
    for row, cells in zip(body, [r.cells for r in STAFF_TABLE.rows], strict=True):
        texts = [
            squeezed(re.sub(r"<[^>]+>", " ", cell))
            for cell in re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.S)
        ]
        assert texts == list(cells)


def test_the_main_cell_links_to_the_row() -> None:
    html = table_html(STAFF_TABLE)

    assert re.search(r'<a\b[^>]*href="/staff/3/"[^>]*>\s*Gene\s*</a>', html)
    assert re.search(r'<a\b[^>]*href="/staff/4/"[^>]*>\s*Pim\s*</a>', html)


def test_a_table_escapes_its_cells() -> None:
    table = Table(
        (Column("Name", is_main=True),), (Row(("<i>Gene</i>",), "/staff/3/"),), NO_STAFF
    )

    html = table_html(table)

    assert "<i>Gene</i>" not in html
    assert "&lt;i&gt;Gene&lt;/i&gt;" in html


def test_a_table_with_rows_shows_no_empty_state() -> None:
    assert NO_STAFF.message not in table_html(STAFF_TABLE)


def test_a_table_with_no_rows_shows_the_empty_state_instead() -> None:
    html = table_html(Table(STAFF_TABLE.columns, (), NO_STAFF))

    assert "<table" not in html
    assert NO_STAFF.message in html
    assert re.search(r'<a\b[^>]*href="/staff/new/"[^>]*>\s*Add\s*</a>', html)


# ---------------------------------------------------------------- empty state
def empty_html(empty: Empty) -> str:
    return render('{% include "kit/empty.html" with empty=empty %}', empty=empty)


def test_the_empty_state_says_its_message_with_its_button() -> None:
    html = empty_html(NO_STAFF)

    assert NO_STAFF.message in html
    assert re.search(r'<a\b[^>]*href="/staff/new/"[^>]*>\s*Add\s*</a>', html)


def test_the_empty_state_without_an_action_has_no_button() -> None:
    html = empty_html(Empty("No work to show yet. Lab work will appear here."))

    assert "No work to show yet." in html
    assert "<a" not in html


# --------------------------------------------------------------------- detail
GENE = Detail(
    title="Gene",
    line="gene@example.com",
    facts=(Fact("Role", "Tech"), Fact("State", "Active")),
)


def detail_html(detail: Detail) -> str:
    return render('{% include "kit/detail.html" with detail=detail %}', detail=detail)


def test_a_detail_shows_its_title_then_its_line() -> None:
    html = detail_html(GENE)

    assert re.search(r"<h1\b[^>]*>\s*Gene\s*</h1>", html)
    assert html.index("Gene") < html.index("gene@example.com")


def test_a_detail_shows_its_facts_as_terms_and_values_in_order() -> None:
    html = detail_html(GENE)

    terms = [
        squeezed(term) for term in re.findall(r"<dt\b[^>]*>(.*?)</dt>", html, re.S)
    ]
    values = [squeezed(v) for v in re.findall(r"<dd\b[^>]*>(.*?)</dd>", html, re.S)]
    assert (terms, values) == (["Role", "State"], ["Tech", "Active"])
    assert html.count("<dl") == 1


def test_a_detail_without_a_line_shows_none() -> None:
    html = detail_html(Detail("Gene", (Fact("Role", "Tech"),)))

    assert "gene@example.com" not in html
    assert re.search(r"<h1\b[^>]*>\s*Gene\s*</h1>", html)


def test_a_detail_escapes_its_values() -> None:
    html = detail_html(Detail("<b>Gene</b>", (Fact("Role", "<i>Tech</i>"),)))

    assert "<b>Gene</b>" not in html
    assert "<i>Tech</i>" not in html
