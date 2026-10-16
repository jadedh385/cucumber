"""Make a server's secrets file, on the server itself (U0.4b design §10.1).

    uv run --no-dev python -m scripts.make_secrets production

Fills `deploy/secrets.env.example` with this environment's fixed values and
new random secrets, and writes `~/cucumber/<environment>/secrets.env` readable
by its owner only. It never overwrites an existing file and never prints a
secret: only the first 8 characters of each one's SHA-256, so the setup log
can show production's differ from staging's (U0.4a G4). Standard library
only: the server runs it with `uv run --no-dev`.
"""

import hashlib
import os
import secrets
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from scripts.server import ENVIRONMENTS, ServerError, place_for

TEMPLATE = Path(__file__).resolve().parent.parent / "deploy" / "secrets.env.example"
RANDOM_NAMES = (
    "DJANGO_SECRET_KEY",
    "POSTGRES_PASSWORD",
    "DB_OWNER_PASSWORD",
    "DB_APP_PASSWORD",
)
# Bytes of randomness; token_urlsafe(50) gives 67 characters, above the app's
# 50-character minimum for the secret key (settings.SECRET_KEY_MIN_LENGTH).
SECRET_KEY_BYTES = 50
PASSWORD_BYTES = 32
PRIVATE_FILE = 0o600
PRIVATE_FOLDER = 0o700
DOMAIN = "southeastcanopy.com"

# Fixed per environment: names (U0.4b §3), ports (U0.4a §3), memory caps
# (staging U0.4a Q1, production U0.4b Q3). The tunnel starts off; U0.4b
# sets its token and COMPOSE_PROFILES=tunnel.
FIXED: Mapping[str, Mapping[str, str]] = {
    "staging": {
        "host": f"cucumber-staging.{DOMAIN}",
        "APP_PORT": "8001",
        "DB_LOCAL_PORT": "5435",
        "APP_MEMORY_LIMIT": "512m",
        "DB_MEMORY_LIMIT": "512m",
        "TUNNEL_MEMORY_LIMIT": "128m",
    },
    "production": {
        "host": f"cucumber.{DOMAIN}",
        "APP_PORT": "8000",
        "DB_LOCAL_PORT": "5436",
        "APP_MEMORY_LIMIT": "1g",
        "DB_MEMORY_LIMIT": "1536m",
        "TUNNEL_MEMORY_LIMIT": "128m",
    },
}


def values_for(environment: str, make_random: Callable[[int], str]) -> dict[str, str]:
    """Every value in the secrets file; `make_random` is `secrets.token_urlsafe`."""
    if environment not in ENVIRONMENTS:
        raise ServerError(
            f"The environment must be staging or production, not {environment!r}."
        )
    fixed = FIXED[environment]
    host = fixed["host"]
    return {
        "DJANGO_ENVIRONMENT": environment,
        "DJANGO_SECRET_KEY": make_random(SECRET_KEY_BYTES),
        "DJANGO_ALLOWED_HOSTS": host,
        "DJANGO_CSRF_TRUSTED_ORIGINS": f"https://{host}",
        "DJANGO_HSTS_SECONDS": "3600",
        "POSTGRES_PASSWORD": make_random(PASSWORD_BYTES),
        "DB_OWNER_PASSWORD": make_random(PASSWORD_BYTES),
        "DB_APP_PASSWORD": make_random(PASSWORD_BYTES),
        "APP_PORT": fixed["APP_PORT"],
        "DB_LOCAL_PORT": fixed["DB_LOCAL_PORT"],
        "TUNNEL_TOKEN": "not-set-until-U0.4b",
        "COMPOSE_PROFILES": "",
        "APP_MEMORY_LIMIT": fixed["APP_MEMORY_LIMIT"],
        "DB_MEMORY_LIMIT": fixed["DB_MEMORY_LIMIT"],
        "TUNNEL_MEMORY_LIMIT": fixed["TUNNEL_MEMORY_LIMIT"],
    }


def fill_template(template: str, values: Mapping[str, str]) -> str:
    """The template with each `NAME=` line given its value; comments kept.

    Refuses if the template and `values` don't name exactly the same settings,
    so a setting added to the example can't be left out by mistake.
    """
    lines = []
    in_template = set()
    for line in template.splitlines(keepends=True):
        name, equals, _ = line.partition("=")
        if line.lstrip().startswith("#") or not equals:
            lines.append(line)
            continue
        name = name.strip()
        if name not in values:
            raise ServerError(f"No value for {name} in the secrets template.")
        in_template.add(name)
        lines.append(f"{name}={values[name]}\n")
    missing = sorted(set(values) - in_template)
    if missing:
        raise ServerError(f"The secrets template has no line for {', '.join(missing)}.")
    return "".join(lines)


def fingerprint(value: str) -> str:
    """The first 8 characters of the SHA-256: shows two secrets differ, safely."""
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def write_private(path: Path, text: str) -> None:
    """Create `path` readable by its owner only; never replace an existing file."""
    try:
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, PRIVATE_FILE)
    except FileExistsError:
        raise ServerError(
            f"{path} already exists, so nothing was changed. "
            "Its secrets are in use: never make them again."
        ) from None
    with os.fdopen(handle, "w") as file:
        file.write(text)


def main(
    argv: Sequence[str] | None = None, os_environ: Mapping[str, str] | None = None
) -> int:
    """Make the file; 0 when made, 1 when stopped."""
    args = sys.argv[1:] if argv is None else argv
    shell = os.environ if os_environ is None else os_environ
    try:
        if len(args) != 1:
            raise ServerError("Say which environment: staging or production.")
        values = values_for(args[0], secrets.token_urlsafe)
        place = place_for(args[0], shell)
        place.folder.mkdir(mode=PRIVATE_FOLDER, parents=True, exist_ok=True)
        place.folder.chmod(PRIVATE_FOLDER)
        write_private(place.secrets, fill_template(TEMPLATE.read_text(), values))
    except ServerError as error:
        print(f"Stopped: {error}")
        return 1
    print(f"Made {place.secrets} (only you can read it).")
    print("Fingerprints for the setup log (first 8 characters of each SHA-256):")
    for name in RANDOM_NAMES:
        print(f"  {name} {fingerprint(values[name])}")
    print(f"Next: save the whole file in Bitwarden. On this Mac: cat {place.secrets}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
