"""Cucumber's addresses plus one test-only page that names no matrix row.

Used with `override_settings(ROOT_URLCONF=...)` to prove such a page is
refused, never by the running app (U0.6 design §3.1).
"""

from django.http import HttpRequest, HttpResponse
from django.urls import path

from cucumber.urls import handler500
from cucumber.urls import urlpatterns as cucumber_urlpatterns

NO_ROW_PAGE = "/test-only/no-row/"


def page_without_a_row(request: HttpRequest) -> HttpResponse:
    return HttpResponse("this should never be shown")


urlpatterns = [
    *cucumber_urlpatterns,
    path("test-only/no-row/", page_without_a_row, name="test_only_no_row"),
]

__all__ = ["handler500", "urlpatterns"]
