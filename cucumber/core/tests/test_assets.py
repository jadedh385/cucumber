"""U0.10a AC1, AC2: one stylesheet built here, scripts and plugins pinned (§3).

The versions and hashes of the two committed tools live here, one place
per tool (§3.1); the Tailwind CLI's are in `scripts/css.py`. G3 pins each to
the latest patch at least two weeks old and replaces the placeholders with
the hashes the project publishes. Dependabot can't see these; they are
checked by hand at each phase release gate (§19).
"""

import hashlib
import html as entities
import json
import re
import subprocess
from base64 import b64encode
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client

ROOT = Path(settings.BASE_DIR)
CORE = ROOT / "cucumber/core"
BUILT_CSS = CORE / "static/core/cucumber.css"
BUILT_CSS_PATH = "cucumber/core/static/core/cucumber.css"

# htmx (§4.1): `htmx.min.js` from the npm package `htmx.org`, checked
# against the SHA-384 htmx publishes for that version. G3 pins.
HTMX_VERSION = "2.0.11"
HTMX_FILE = CORE / "static/core/vendor/htmx.min.js"
HTMX_SHA384 = "sha384-" + "A" * 64  # placeholder until G3 pins

# daisyUI (§3.1): the two plugin files from the release, committed.
DAISYUI_VERSION = "5.7.47"
DAISYUI_FILES = {
    CORE / "css/vendor/daisyui.mjs": "0" * 64,  # placeholder until G3 pins
    CORE / "css/vendor/daisyui-theme.mjs": "0" * 64,  # placeholder until G3 pins
}

# Every colour variable daisyUI 5's `light` theme sets (§3.2): a theme with a
# new name gets only the variables it gives, so each must be in `cucumber`.
LIGHT_COLOURS = [
    f"--color-{name}"
    for base in ["primary", "secondary", "accent", "neutral"]
    + ["info", "success", "warning", "error"]
    for name in (base, f"{base}-content")
] + ["--color-base-100", "--color-base-200", "--color-base-300", "--color-base-content"]


def sri_sha384(path: Path) -> str:
    """The file's hash as htmx publishes it (Subresource Integrity form)."""
    digest = hashlib.sha384(path.read_bytes()).digest()
    return f"sha384-{b64encode(digest).decode()}"


def built_css() -> str:
    assert BUILT_CSS.is_file(), "no built stylesheet: run `python -m scripts.css build`"
    return BUILT_CSS.read_text()


def cucumber_theme(css: str) -> str:
    """The body of the rule(s) that define the `cucumber` theme."""
    blocks = re.findall(r'\[data-theme="?cucumber"?\][^{]*\{([^}]*)\}', css)
    assert blocks, "the built CSS defines no cucumber theme"
    return "".join(blocks)


# ------------------------------------------------------------------- htmx
def test_htmx_is_committed_and_matches_its_published_hash() -> None:
    assert HTMX_FILE.is_file(), "htmx.min.js is missing"
    assert sri_sha384(HTMX_FILE) == HTMX_SHA384


def test_htmx_is_the_pinned_version() -> None:
    assert re.fullmatch(r"2\.0\.\d+", HTMX_VERSION)
    assert HTMX_FILE.is_file(), "htmx.min.js is missing"
    assert f'version:"{HTMX_VERSION}"' in HTMX_FILE.read_text()


# ---------------------------------------------------------------- daisyUI
@pytest.mark.parametrize("path", list(DAISYUI_FILES), ids=lambda path: path.name)
def test_each_daisyui_file_matches_the_release(path: Path) -> None:
    assert path.is_file(), f"{path.name} is missing"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == DAISYUI_FILES[path]


def test_daisyui_is_a_version_5_release() -> None:
    assert re.fullmatch(r"5\.\d+\.\d+", DAISYUI_VERSION)


def test_the_source_css_uses_the_committed_plugins_not_a_package() -> None:
    source = CORE / "css/source.css"
    assert source.is_file(), "core/css/source.css is missing"
    text = source.read_text()

    assert '@plugin "./vendor/daisyui.mjs"' in text
    assert '@plugin "./vendor/daisyui-theme.mjs"' in text
    assert 'name: "cucumber"' in text


# ------------------------------------------------------- the built stylesheet
def test_git_never_tracks_the_built_stylesheet() -> None:
    """So nobody re-adds a hand-written copy (§3.4)."""
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", BUILT_CSS_PATH],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", BUILT_CSS_PATH], cwd=ROOT, check=False
    )

    assert tracked.returncode != 0, f"git tracks {BUILT_CSS_PATH}"
    assert ignored.returncode == 0, f"{BUILT_CSS_PATH} is not in .gitignore"


def test_the_built_stylesheet_holds_the_cucumber_theme() -> None:
    theme = cucumber_theme(built_css())

    assert "--color-primary:" in theme


def test_the_cucumber_theme_sets_every_colour_of_daisyuis_light() -> None:
    theme = cucumber_theme(built_css())

    missing = [name for name in LIGHT_COLOURS if f"{name}:" not in theme]
    assert missing == []


def test_buttons_and_inputs_are_44_pixels_tall() -> None:
    """`--size-field: 0.275rem` (§3.2, AC7); the E2E size checks measure it."""
    assert re.search(r"--size-field:\s*0?\.275rem", cucumber_theme(built_css()))


@pytest.mark.django_db
def test_pages_use_the_cucumber_theme() -> None:
    html = Client().get("/accounts/login/").content.decode()

    assert re.search(r'<html\b[^>]*\bdata-theme="cucumber"', html)


# Every page is one of these two (AC1): the 500 and Busy pages are bare,
# so they render with no database (§7.8).
PAGE_SHELLS = {"core/templates/base.html", "core/templates/kit/bare.html"}


def test_only_the_two_shells_open_a_page() -> None:
    opening = {
        str(path.relative_to(ROOT / "cucumber"))
        for path in sorted((ROOT / "cucumber").glob("*/templates/**/*.html"))
        if "<html" in path.read_text()
    }

    assert opening == PAGE_SHELLS


@pytest.mark.parametrize("shell", sorted(PAGE_SHELLS))
def test_each_shell_uses_the_cucumber_theme(shell: str) -> None:
    source = (ROOT / "cucumber" / shell).read_text()

    assert re.search(r'<html\b[^>]*\bdata-theme="cucumber"', source)


# htmx's settings (§4.1): data in a meta tag, read by htmx itself.
HTMX_CONFIG = {
    "timeout": 20000,
    "allowEval": False,
    "allowScriptTags": False,
    "includeIndicatorStyles": False,
    "selfRequestsOnly": True,
    "historyCacheSize": 0,
    "responseHandling": [
        {"code": "204", "swap": False},
        {"code": "[23]..", "swap": True},
        {"code": "422", "swap": True},
        {"code": "...", "swap": False, "error": True},
    ],
}


@pytest.mark.django_db
def test_htmx_gets_every_setting_from_the_meta_tag() -> None:
    page = Client().get("/accounts/login/").content.decode()
    meta = re.search(
        r"""<meta\b[^>]*\bname="htmx-config"[^>]*\bcontent=(["'])(.*?)\1""", page
    )

    assert meta, "no htmx-config meta"
    assert json.loads(entities.unescape(meta.group(2))) == HTMX_CONFIG


# ------------------------------------- AC2: nothing from another site (scan)
TEMPLATES = sorted((ROOT / "cucumber").glob("*/templates/**/*.html"))
ADDRESS = re.compile(r'\b(src|href|action)\s*=\s*"([^"]*)"')
# `{% static %}` files, `{% url %}` pages, a value from the view, or a path
# on this site; never another host (`https:`, `//host`, `data:`).
ALLOWED_ADDRESS = re.compile(r"\{%\s*(static|url)\s|\{\{|#|/(?!/)|\?")


def foreign_addresses(source: str) -> list[str]:
    return [
        f'{attribute}="{value}"'
        for attribute, value in ADDRESS.findall(source)
        if not ALLOWED_ADDRESS.match(value)
    ]


def test_no_template_loads_anything_from_another_site() -> None:
    found = {
        str(path.relative_to(ROOT)): addresses
        for path in TEMPLATES
        if (addresses := foreign_addresses(path.read_text()))
    }

    assert TEMPLATES, "found no templates: has the folder moved?"
    assert found == {}


@pytest.mark.parametrize(
    "markup",
    [
        '<script src="https://cdn.jsdelivr.net/npm/htmx.org"></script>',
        '<link rel="stylesheet" href="//cdn.example.com/daisy.css">',
        '<img src="http://example.com/logo.png">',
        '<img src="data:image/png;base64,AAAA">',
        '<form action="https://elsewhere.example/">',
        '<link href="cucumber.css">',
    ],
)
def test_the_scan_finds_an_address_on_another_site(markup: str) -> None:
    assert foreign_addresses(markup) != []


@pytest.mark.parametrize(
    "markup",
    [
        "<script src=\"{% static 'core/vendor/htmx.min.js' %}\" defer></script>",
        "<a href=\"{% url 'home' %}\">",
        '<a href="{{ reload }}">',
        '<a href="/">',
        '<a href="#main">',
        '<form action="?next=/staff/">',
    ],
)
def test_the_scan_lets_this_sites_addresses_through(markup: str) -> None:
    assert foreign_addresses(markup) == []
