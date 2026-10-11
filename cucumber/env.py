"""Read settings from environment variables, all in one place.

Every variable Cucumber reads goes through `env()`, so a test can list them
and check that `.env.example` names each one (U0.3 AC13).
"""

import os


def env(name: str, default: str = "") -> str:
    """Return the variable's value, or `default` when it is unset or blank."""
    value = os.environ.get(name, "").strip()
    return value or default
