"""Start Cucumber's settings in a fresh Python with only the given variables.

Nothing from the developer's own environment or .env leaks in, so a test
sees exactly what a server with those variables would (U0.3 AC12, U0.4a AC5).
"""

import json
import os
import subprocess
import sys
from collections.abc import Sequence
from typing import Any

from django.conf import settings

PRINT_DEBUG = "import cucumber.settings as s; print(s.DEBUG)"


def run_python(
    arguments: Sequence[str], variables: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=settings.BASE_DIR,
        env={"PATH": os.environ["PATH"], **variables},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def load_settings(variables: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Import the settings; prints DEBUG when they load."""
    return run_python(["-c", PRINT_DEBUG], variables)


def settings_values(variables: dict[str, str], names: Sequence[str]) -> dict[str, Any]:
    """The named settings, Django's defaults included, as JSON values.

    Tuples come back as lists and paths as text; an unknown name as None.
    """
    code = (
        "import json; from django.conf import settings as s; "
        f"print(json.dumps({{n: getattr(s, n, None) for n in {list(names)!r}}}, "
        "default=str))"
    )
    django_settings = {"DJANGO_SETTINGS_MODULE": "cucumber.settings"}
    result = run_python(["-c", code], {**django_settings, **variables})
    assert result.returncode == 0, error_line(result)
    values = json.loads(result.stdout)
    assert isinstance(values, dict)
    return values


def error_line(result: subprocess.CompletedProcess[str]) -> str:
    """The exception's own line; the traceback above it echoes source code."""
    lines = result.stderr.strip().splitlines()
    return lines[-1] if lines else ""
