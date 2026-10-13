"""Values every page template can use (U0.4a design §4.4)."""

from django.http import HttpRequest


def environment(request: HttpRequest) -> dict[str, str]:
    """`environment`: local, staging or production, for the "Practice data" banner."""
    raise NotImplementedError("U0.4a G3")
