"""U0.10a AC3: no JavaScript or style written into a page (§4.4).

Every template under `cucumber/*/templates/` is read. A script is a static
file loaded with `<script src="{% static … %}" defer></script>`; anything
else that would run code, or set a style the CSP refuses (§5), fails the
test with the file and what was found. The self-tests show each refused
pattern is caught and the allowed script tag passes. The CSP is the second
line and the E2E console watcher the third.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
TEMPLATES = sorted((ROOT / "cucumber").glob("*/templates/**/*.html"))

# Django comments are not sent to the browser, so a word in one is no code.
COMMENTS = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}|{#.*?#}", re.DOTALL)
SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.DOTALL | re.IGNORECASE)
STATIC_SRC = re.compile(r"""\bsrc\s*=\s*"\{%\s*static\s+['"][^'"]+['"]\s*%\}\"""")
REFUSED: list[tuple[str, re.Pattern[str]]] = [
    ("an on… attribute", re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)),
    ("hx-on", re.compile(r"\shx-on\b", re.IGNORECASE)),
    ("data-hx-on", re.compile(r"\sdata-hx-on\b", re.IGNORECASE)),
    (
        "hx-vals / hx-vars with code",
        re.compile(
            r"""\s(?:data-)?hx-va(?:ls|rs)\s*=\s*['"]\s*(?:js|javascript):""",
            re.IGNORECASE,
        ),
    ),
    (
        "an hx-trigger filter",
        re.compile(r"""\s(?:data-)?hx-trigger\s*=\s*['"][^'"]*\[""", re.IGNORECASE),
    ),
    (
        "a javascript: address",
        re.compile(r"""\s(?:href|src|action)\s*=\s*['"]\s*javascript:""", re.I),
    ),
    ("a style attribute", re.compile(r"\sstyle\s*=", re.IGNORECASE)),
    ("a style element", re.compile(r"<style\b", re.IGNORECASE)),
]


def inline_code(source: str) -> list[str]:
    """What in this template would run code or set a style inline."""
    source = COMMENTS.sub(" ", source)
    found: list[str] = []
    for attributes, body in SCRIPT.findall(source):
        if body.strip():
            found.append("a script with code inside")
        elif not STATIC_SRC.search(attributes):
            found.append("a script not loaded from {% static %}")
    found.extend(name for name, pattern in REFUSED if pattern.search(source))
    return found


def test_no_template_has_inline_script_or_style() -> None:
    found = {
        str(path.relative_to(ROOT)): problems
        for path in TEMPLATES
        if (problems := inline_code(path.read_text()))
    }

    assert TEMPLATES, "found no templates: has the folder moved?"
    assert found == {}


# ------------------------------------------------------------- self-tests
@pytest.mark.parametrize(
    ("markup", "problem"),
    [
        ("<script>alert(1)</script>", "a script with code inside"),
        ('<script type="module">\n  go()\n</script>', "a script with code inside"),
        ('<script src="/static/core/forms.js"></script>', "a script not loaded"),
        ('<script src="https://cdn.example/x.js"></script>', "a script not loaded"),
        ("<SCRIPT>go()</SCRIPT>", "a script with code inside"),
        ('<button onclick="go()">', "an on… attribute"),
        ('<body onload="go()">', "an on… attribute"),
        ("<img src=x ONERROR=go()>", "an on… attribute"),
        ('<form hx-on:submit="go()">', "hx-on"),
        ('<form hx-on::after-request="go()">', "hx-on"),
        ('<form hx-on="htmx:load: go()">', "hx-on"),
        ('<form data-hx-on:click="go()">', "data-hx-on"),
        ("<div hx-vals='js:{a: go()}'>", "hx-vals / hx-vars with code"),
        ('<div hx-vars="javascript:go()">', "hx-vals / hx-vars with code"),
        ('<div hx-trigger="click[ctrlKey]">', "an hx-trigger filter"),
        ('<a href="javascript:go()">', "a javascript: address"),
        ('<p style="color: red">', "a style attribute"),
        ("<style>p { color: red }</style>", "a style element"),
    ],
)
def test_the_scan_finds_each_refused_pattern(markup: str, problem: str) -> None:
    found = inline_code(markup)

    assert any(name.startswith(problem) for name in found), found


@pytest.mark.parametrize(
    "markup",
    [
        "<script src=\"{% static 'core/vendor/htmx.min.js' %}\" defer></script>",
        "<script defer src=\"{% static 'core/forms.js' %}\"></script>",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="htmx-config" content=\'{"allowEval": false}\'>',
        '<div hx-vals=\'{"kind": "plain"}\'>',
        '<div hx-trigger="change from:select">',
        '<button aria-label="Close" data-action="close">',
        '<p class="online">Online</p>',
        "{# never <script>go()</script> or style= #}",
        "{% comment %}an onclick= here is prose{% endcomment %}",
    ],
)
def test_the_scan_lets_allowed_markup_through(markup: str) -> None:
    assert inline_code(markup) == []
