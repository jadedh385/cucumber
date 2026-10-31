"""`{% htmx_config %}`: htmx's settings for the head's meta tag (U0.10a §4.1).

Data, not script, so the CSP allows it; htmx reads the meta itself. The
timeout is read from settings when the page is made, so a test can shorten
it (§8.3).
"""

import json

from django import template
from django.conf import settings

register = template.Library()

# Every setting but the timeout. `allowEval` and `allowScriptTags` off: htmx
# never runs text as code. `includeIndicatorStyles` off: htmx would add a
# <style> element, which the CSP refuses (source.css has the classes).
# `historyCacheSize` 0: no copies of pages in a shared phone's storage. 422
# is swapped: a refused form comes back with its messages (§11.2).
HTMX_SETTINGS = {
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


@register.simple_tag
def htmx_config() -> str:
    """The JSON for `<meta name="htmx-config">` (escaped by the template)."""
    return json.dumps({"timeout": settings.HTMX_TIMEOUT_MS, **HTMX_SETTINGS})
