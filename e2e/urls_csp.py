"""Cucumber's addresses plus one test-only page that breaks the CSP (U0.10a AC4).

Used with `override_settings(ROOT_URLCONF=...)` by the local live server,
never by the running app. The page runs an inline script and an inline
style, both of which the policy refuses; the console watcher (§5.3) must
catch them.
"""

from django.contrib.auth.decorators import login_not_required
from django.http import HttpRequest, HttpResponse
from django.urls import path

from cucumber.urls import handler403, handler500
from cucumber.urls import urlpatterns as cucumber_urlpatterns

BREAKS_THE_POLICY = "/test-only/breaks-the-policy/"
RAN = "the inline script ran"

PAGE = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Breaks the policy</title></head>
<body style="color: red">
<p>A page with inline code.</p>
<script>document.title = "{RAN}";</script>
</body></html>
"""


@login_not_required  # nobody to sign in: the page is all the test needs
def breaks_the_policy(request: HttpRequest) -> HttpResponse:
    return HttpResponse(PAGE)


urlpatterns = [
    *cucumber_urlpatterns,
    path(BREAKS_THE_POLICY.lstrip("/"), breaks_the_policy),
]

__all__ = ["handler403", "handler500", "urlpatterns"]
