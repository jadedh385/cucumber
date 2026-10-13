"""Values every page template can use (U0.4a design §4.4)."""

from django.conf import settings
from django.http import HttpRequest


def environment(request: HttpRequest) -> dict[str, str]:
    """`environment`: local, staging or production, for the "Practice data" banner."""
    return {"environment": settings.ENVIRONMENT}
