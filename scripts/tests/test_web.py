"""The one HTTP request the health check and the Discord post make (scripts/web.py).

Against a real little server on this machine, so urllib's own behaviour
(error statuses, POST bodies, headers) is what is checked.
"""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts.web import request


class Answers(BaseHTTPRequestHandler):
    """`/ok` answers 200 with the Host header it got; anything else 503."""

    received: list[tuple[str, bytes, str]] = []

    def do_GET(self) -> None:
        self.answer()

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        self.answer(self.rfile.read(length))

    def answer(self, body: bytes = b"") -> None:
        self.received.append((self.command, body, self.headers.get("Host", "")))
        status = 200 if self.path == "/ok" else 503
        text = f"{status} for {self.headers.get('Host')}".encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(text)))
        self.end_headers()
        self.wfile.write(text)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the test output quiet."""


@pytest.fixture
def server() -> Iterator[str]:
    Answers.received = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Answers)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_a_get_returns_the_status_and_body_with_the_headers_sent(server: str) -> None:
    status, body = request(f"{server}/ok", {"Host": "cucumber.example.com"})

    assert (status, body) == (200, "200 for cucumber.example.com")


def test_an_error_status_is_returned_not_raised(server: str) -> None:
    status, body = request(f"{server}/starting", {})

    assert status == 503
    assert body.startswith("503")


def test_data_makes_it_a_post_with_that_body(server: str) -> None:
    status, _ = request(f"{server}/ok", {"Content-Type": "application/json"}, b"{}")

    assert status == 200
    assert Answers.received[-1][:2] == ("POST", b"{}")


def test_nothing_listening_raises_an_os_error() -> None:
    with pytest.raises(OSError):
        request("http://127.0.0.1:9/health/", {})


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/"])
def test_only_web_addresses_are_allowed(url: str) -> None:
    with pytest.raises(ValueError, match="http"):
        request(url, {})
