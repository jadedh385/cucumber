"""The kit's template tags (U0.10a §7.4, §7.6). G2 stub: built at G3."""

from django import template
from django.utils.safestring import SafeString

from cucumber.core.kit import Table
from cucumber.references.lists import ListName
from cucumber.references.reading import Item

register = template.Library()


@register.simple_tag
def item_text(name: ListName, found: dict[str, Item] | Item | None, code: str) -> str:
    """`{% item_text "stages" items code %}`: `core.kit.item_text`, escaped."""
    raise NotImplementedError("U0.10a G3")


@register.simple_tag
def kit_table(table: Table) -> SafeString:
    """`{% kit_table table %}`: `kit/table.html`, or `kit/empty.html` with no rows."""
    raise NotImplementedError("U0.10a G3")
