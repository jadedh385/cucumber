"""Cucumber's addresses plus one test-only page that saves a row (AC20).

Used with `override_settings(ROOT_URLCONF=...)`, never by the running app.
"""

from django.contrib.auth.models import Group
from django.http import HttpRequest, HttpResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from cucumber.urls import handler500
from cucumber.urls import urlpatterns as cucumber_urlpatterns

SAVED_GROUP = "written-by-a-test-view"


@csrf_exempt  # so the CSRF check can't be what stops the save
def save_a_row(request: HttpRequest) -> HttpResponse:
    Group.objects.create(name=SAVED_GROUP)
    return HttpResponse("saved")


urlpatterns = [
    *cucumber_urlpatterns,
    path("test-only/save/", save_a_row, name="test_only_save"),
]

__all__ = ["handler500", "urlpatterns"]
