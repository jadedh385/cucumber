"""The kit's template tags (U0.10a §7.4, §7.6)."""

from django import template
from django.template.loader import render_to_string
from django.utils.safestring import SafeString

from cucumber.core import kit
from cucumber.core.kit import Table
from cucumber.references.lists import ListName
from cucumber.references.reading import Item

register = template.Library()


@register.simple_tag
def item_text(name: ListName, found: dict[str, Item] | Item | None, code: str) -> str:
    """`{% item_text "stages" items code %}`: `core.kit.item_text`, escaped."""
    return kit.item_text(ListName(name), found, code)


@register.simple_tag
def kit_table(table: Table) -> SafeString:
    """`{% kit_table table %}`: `kit/table.html`, or `kit/empty.html` with no rows."""
    if not table.rows:
        return render_to_string("kit/empty.html", {"empty": table.empty})
    rows = [
        (row.href, zip(table.columns, row.cells, strict=True)) for row in table.rows
    ]
    return render_to_string("kit/table.html", {"table": table, "rows": rows})
