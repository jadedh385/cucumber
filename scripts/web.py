"""One plain HTTP request, for the deploy health check and the Discord post.

Standard library only: the server runs the scripts with `uv run --no-dev`.
"""

import urllib.error
import urllib.request
from collections.abc import Mapping

TIMEOUT_SECONDS = 10


def request(
    url: str, headers: Mapping[str, str], data: bytes | None = None
) -> tuple[int, str]:
    """GET (or POST when `data` is given); returns (status, body).

    An answer with an error status is returned like any other. Not reaching
    the address at all raises OSError, as urllib does.
    """
    if not url.startswith(("http://", "https://")):
        raise ValueError("only http:// and https:// addresses are allowed")
    method = "GET" if data is None else "POST"
    sent = urllib.request.Request(url, data=data, headers=dict(headers), method=method)  # noqa: S310 (scheme checked above)
    try:
        with urllib.request.urlopen(sent, timeout=TIMEOUT_SECONDS) as answer:  # noqa: S310
            return answer.status, answer.read().decode(errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(errors="replace")
