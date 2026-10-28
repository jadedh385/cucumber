"""U0.10a AC26: every word a person reads goes through gettext (design §10.4, D-16).

Only English ships, so an untranslated text looks the same as a translated
one. Three checks find them:

- **Templates:** every template in every app, with its words marked
  (moved here from accounts' test_base_page.py, which covered one app).
- **Python:** an AST scan of every module under `cucumber/` (not tests, not
  migrations) at the places text reaches a screen. A plain string literal
  with words in it there fails, with file and line.
- **Refusals:** `MESSAGES` and `INTERNAL_MESSAGE` are marked `gettext_noop`
  (so `makemessages` finds them), and every message comes back through a
  fake translation that wraps each text in ⟦…⟧.

Both scans have self-tests, like U0.9's code scan.
"""

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from django.conf import settings
from django.utils.translation import gettext

from cucumber.accounts.menu import MENU
from cucumber.accounts.permissions import NotAllowed
from cucumber.core.refusals import INTERNAL_MESSAGE, MESSAGES, message_for, refuse
from cucumber.core.tests.fake_translation import wrapped, wrapping_translation

CODE = Path(settings.BASE_DIR) / "cucumber"
REFUSALS = CODE / "core/refusals.py"


# ================================================================ templates
# Parts of a template that are not text a person reads, or are already
# marked for translation. Removed before looking for left-over words.
NOT_TEXT = [
    r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}",
    r"{#.*?#}",
    r"<style\b.*?</style>",
    r"<script\b.*?</script>",
    r"<svg\b.*?</svg>",
    r"{%\s*blocktranslate\b.*?{%\s*endblocktranslate\s*%}",
    r"{%.*?%}",
    r"{{.*?}}",
    r"<[^>]*>",
    r"&\w+;",
]
# The app's name stays the same in Thai.
NAMES = {"Cucumber"}
READABLE_ATTRIBUTES = re.compile(
    r'\b(?:placeholder|aria-label|title|alt)="([^"]*[A-Za-z][^"]*)"'
)


def template_files() -> list[Path]:
    """Every template of every app."""
    return sorted(CODE.glob("*/templates/**/*.html"))


def words_not_marked(source: str) -> list[str]:
    readable = [
        value
        for value in READABLE_ATTRIBUTES.findall(source)
        if "{%" not in value and "{{" not in value
    ]
    for pattern in NOT_TEXT:
        source = re.sub(pattern, " ", source, flags=re.DOTALL)
    words = re.findall(r"[A-Za-z][A-Za-z'’]*", source)
    return readable + [word for word in words if word not in NAMES]


def test_templates_of_more_than_one_app_are_found() -> None:
    apps = {path.relative_to(CODE).parts[0] for path in template_files()}

    assert {"accounts", "core"} <= apps


def test_every_word_in_every_template_is_marked_for_translation() -> None:
    unmarked = {
        str(path.relative_to(CODE)): words
        for path in template_files()
        if (words := words_not_marked(path.read_text()))
    }

    assert unmarked == {}


def test_the_template_check_finds_plain_text() -> None:
    """Proves the check above would catch an unmarked word."""
    assert words_not_marked("<p>Log in</p>") == ["Log", "in"]
    assert words_not_marked('<input placeholder="Email">') == ["Email"]
    assert words_not_marked('<a aria-label="Home" href="/">') == ["Home"]
    assert words_not_marked("<p>{% translate 'Log in' %}</p>") == []
    assert (
        words_not_marked("{% blocktranslate %}Hi {{ n }}{% endblocktranslate %}") == []
    )
    assert words_not_marked("<svg><title>x</title><path d='M1 2'/></svg>") == []
    assert words_not_marked("<h1>Cucumber</h1>") == []


# =================================================================== Python
GETTEXT = {
    "_",
    "gettext",
    "gettext_lazy",
    "gettext_noop",
    "ngettext",
    "ngettext_lazy",
    "pgettext",
    "pgettext_lazy",
    "npgettext",
}
MESSAGE_CALLS = {"success", "error", "info", "warning"}
# The kit's own values: (call, its text arguments by place, by keyword).
KIT_TEXTS = {
    "MenuItem": ((0,), ("label",)),
    "Column": ((0,), ("label",)),
    "Empty": ((0, 1), ("message", "action_label")),
    "Fact": ((0,), ("label",)),
}
TEXT_KEYWORDS = {"label", "help_text", "empty_label", "error_messages"}
TEXT_ATTRIBUTES = {"label", "help_text", "empty_label", "error_messages"}


@dataclass(frozen=True)
class Plain:
    line: int
    text: str


def call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def has_words(text: str) -> bool:
    """Letters left after markup and `{placeholders}` are taken out."""
    return re.search(r"[A-Za-z]", re.sub(r"<[^>]*>|\{[^}]*\}", "", text)) is not None


def plain_texts(node: ast.expr) -> Iterator[Plain]:
    """String literals with words in `node`, unless inside a gettext call.

    A call to anything else (`message_for(rule)`) is left alone: its
    argument is a key, not text.
    """
    if isinstance(node, ast.Call):
        return
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if has_words(node.value):
            yield Plain(node.lineno, node.value)
        return
    if isinstance(node, ast.JoinedStr):
        parts = "".join(
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
        if has_words(parts):
            yield Plain(node.lineno, parts)
        return
    if isinstance(node, ast.Dict):
        children: list[ast.expr] = [value for value in node.values if value]
    elif isinstance(node, ast.IfExp | ast.BoolOp | ast.BinOp | ast.Tuple | ast.List):
        children = [c for c in ast.iter_child_nodes(node) if isinstance(c, ast.expr)]
    else:
        return
    for child in children:
        yield from plain_texts(child)


def call_sinks(call: ast.Call) -> Iterator[ast.expr]:
    """The arguments of `call` that reach a screen."""
    name = call_name(call)
    places: tuple[int, ...] = ()
    keywords: tuple[str, ...] = ()
    is_messages = (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "messages"
    )
    if is_messages and name in MESSAGE_CALLS:
        places, keywords = (1,), ("message",)
    elif name == "ValidationError":
        places, keywords = (0,), ("message",)
    elif name == "add_error":
        places, keywords = (1,), ("error",)
    elif name == "format_html":
        places = (0,)
    elif name in KIT_TEXTS:
        places, keywords = KIT_TEXTS[name]
    yield from (call.args[place] for place in places if place < len(call.args))
    for keyword in call.keywords:
        if keyword.arg in keywords or keyword.arg in TEXT_KEYWORDS:
            yield keyword.value


def assigned_sinks(node: ast.Assign) -> Iterator[ast.expr]:
    """`field.label = …`, `error_messages = {…}`."""
    for target in node.targets:
        if isinstance(target, ast.Attribute) and target.attr in TEXT_ATTRIBUTES:
            yield node.value
        if isinstance(target, ast.Name) and target.id == "error_messages":
            yield node.value


def untranslated(source: str) -> list[Plain]:
    found: list[Plain] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and call_name(node) in GETTEXT:
            continue
        if isinstance(node, ast.Call):
            sinks = list(call_sinks(node))
        elif isinstance(node, ast.Assign):
            sinks = list(assigned_sinks(node))
        else:
            continue
        for sink in sinks:
            found.extend(plain_texts(sink))
    return found


def python_files() -> list[Path]:
    return [
        path
        for path in sorted(CODE.rglob("*.py"))
        if not {"tests", "migrations"} & set(path.relative_to(CODE).parts)
    ]


def test_the_python_scan_reads_the_apps() -> None:
    scanned = [path.relative_to(CODE) for path in python_files()]

    assert {"accounts/views.py", "accounts/forms.py", "core/kit.py"} <= set(
        map(str, scanned)
    )
    assert not any({"tests", "migrations"} & set(path.parts) for path in scanned)


def test_every_text_a_person_reads_in_python_goes_through_gettext() -> None:
    found = [
        f"{path.relative_to(CODE)}:{plain.line}: {plain.text!r}"
        for path in python_files()
        for plain in untranslated(path.read_text())
    ]

    assert found == []


@pytest.mark.parametrize(
    "source",
    [
        'messages.success(request, "Saved.")',
        'messages.error(request, f"{name} is off.")',
        'messages.info(request, message="Hi there.")',
        'raise ValidationError("Too long.")',
        'raise forms.ValidationError("Too long.", code="long")',
        'form.add_error("email", "Taken.")',
        'form.add_error(None, error="Taken.")',
        'format_html("{name} is gone.", name=name)',
        'MenuItem("Home", "home", Permission.OWN_ACCOUNT, "home", frozenset())',
        'MenuItem(label="Home", url_name="home")',
        'Column("Name", is_main=True)',
        'Empty("No staff yet.")',
        'Empty(_("No staff yet."), "Add", "/staff/new/")',
        'Empty(message=_("No staff yet."), action_label="Add")',
        'Fact("Role", role)',
        'forms.CharField(label="Name")',
        'forms.CharField(label=_("Name"), help_text="Your full name.")',
        'forms.ChoiceField(empty_label="Choose one")',
        'forms.CharField(error_messages={"required": "Say who."})',
        'self.fields["email"].label = "Email"',
        'error_messages = {"invalid_login": "Wrong."}',
        'forms.CharField(label="Name" if short else _("Full name"))',
        'messages.success(request, "Saved " + name)',
    ],
)
def test_the_python_scan_finds_a_plain_text(source: str) -> None:
    assert len(untranslated(source)) == 1, source


@pytest.mark.parametrize(
    "source",
    [
        'messages.success(request, _("Saved."))',
        'messages.error(request, gettext("Off."))',
        "messages.error(request, refusal.message)",
        "messages.error(request, refusal_text(refusal))",
        'raise ValidationError(message_for("password_same_as_temporary"))',
        'raise ValidationError(_("Too long."), code="too_long")',
        'form.add_error("email", refusal.message)',
        'form.add_error(None, gettext_lazy("Taken."))',
        'format_html("<strong>{}</strong>", name)',
        'format_html(_("{name} is gone."), name=name)',
        'format_html("{} · {}", code, label)',
        'MenuItem(_("Home"), "home", Permission.OWN_ACCOUNT, "home", frozenset())',
        'Empty("")',
        'Column(pgettext_lazy("staff", "Name"))',
        'forms.CharField(label=_("Name"), help_text=gettext_lazy("Full name."))',
        'forms.CharField(error_messages={"required": _("Say who.")})',
        'self.fields["email"].label = _("Email")',
        'error_messages = {"invalid_login": WRONG}',
        'logger.info("page refused account=%s", account)',
        'raise ImproperlyConfigured("DEBUG must be off.")',
        'MESSAGES = {"rule": gettext_noop("Words.")}',
    ],
)
def test_the_python_scan_passes_translated_or_non_screen_text(source: str) -> None:
    assert untranslated(source) == [], source


# ================================================================= refusals
def is_noop_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and call_name(node) == "gettext_noop"


def assigned_value(module: ast.Module, name: str) -> ast.expr:
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return node.value
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            return node.value
    raise AssertionError(f"{name} is not assigned in {REFUSALS.name}")


def unmarked_messages(value: ast.expr) -> list[int]:
    """Lines of `MESSAGES` values that aren't `gettext_noop(…)`."""
    assert isinstance(value, ast.Dict), "MESSAGES is a dict literal"
    lines: list[int] = []
    for key, entry in zip(value.keys, value.values, strict=True):
        if key is None:  # `**{… for rules in …}`, built from the lists
            assert isinstance(entry, ast.DictComp)
            if not is_noop_call(entry.value):
                lines.append(entry.lineno)
        elif not is_noop_call(entry):
            lines.append(entry.lineno)
    return lines


def test_every_refusal_message_is_marked_for_makemessages() -> None:
    module = ast.parse(REFUSALS.read_text())

    assert unmarked_messages(assigned_value(module, "MESSAGES")) == []


def test_the_internal_message_is_marked_too() -> None:
    module = ast.parse(REFUSALS.read_text())

    assert is_noop_call(assigned_value(module, "INTERNAL_MESSAGE"))


def test_the_marking_check_finds_a_plain_message() -> None:
    module = ast.parse('MESSAGES = {"a": gettext_noop("A."), "b": "B."}')

    assert unmarked_messages(assigned_value(module, "MESSAGES")) == [1]


def test_the_marking_check_reads_the_built_messages() -> None:
    source = 'MESSAGES = {**{f"{n}_pkey": "Taken." for n in names}}'

    assert unmarked_messages(assigned_value(ast.parse(source), "MESSAGES")) == [1]


# ------------------------------------------------------------ the fake one
def test_the_fake_translation_wraps_text_and_goes_away() -> None:
    with wrapping_translation():
        assert gettext("Saved.") == wrapped("Saved.")

    assert gettext("Saved.") == "Saved."


@pytest.mark.parametrize("rule", sorted(MESSAGES))
def test_every_refusal_message_comes_back_translated(rule: str) -> None:
    with wrapping_translation():
        assert message_for(rule) == wrapped(MESSAGES[rule])


def test_an_unknown_rule_gets_the_internal_message_translated() -> None:
    with wrapping_translation():
        assert message_for("no_such_rule") == wrapped(INTERNAL_MESSAGE)


def test_a_refusal_is_translated_when_it_is_raised() -> None:
    with wrapping_translation():
        refusal = refuse("list_item_inactive")
        not_allowed = NotAllowed("role_not_allowed")

    assert refusal.message == wrapped(MESSAGES["list_item_inactive"])
    assert not_allowed.message == wrapped(MESSAGES["role_not_allowed"])


def test_the_menu_labels_are_translated() -> None:
    with wrapping_translation():
        labels = [str(item.label) for item in MENU]

    assert all(label.startswith("⟦") for label in labels)
