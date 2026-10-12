"""Cucumber settings.

Every value comes from an environment variable through `env()`. Locally they
come from `.env` (copied from `.env.example`); on GitHub the CI workflow sets
them. See `.env.example` for what each one means.
"""

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from cucumber.env import env

BASE_DIR = Path(__file__).resolve().parent.parent

# Debug pages show code and settings to whoever triggers an error, so debug is
# on only when DJANGO_DEBUG is exactly "1" (U0.3 AC12).
DEBUG = env("DJANGO_DEBUG") == "1"


def required(name: str, debug_default: str) -> str:
    """A variable that must be set when debug is off (U0.3 AC12).

    With debug on (local work only) a missing value falls back to
    `debug_default`. With debug off, Cucumber refuses to start and says which
    variable is missing, rather than run with an unsafe default.
    """
    value = env(name)
    if value:
        return value
    if DEBUG:
        return debug_default
    raise ImproperlyConfigured(
        f"{name} must be set when debug is off (DJANGO_DEBUG is not 1). "
        "See .env.example."
    )


SECRET_KEY = required("DJANGO_SECRET_KEY", "dev-only-not-a-secret")

ALLOWED_HOSTS = [
    host.strip()
    for host in required("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]
if not DEBUG and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must list real host names when debug is off, not '*'."
    )

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "cucumber.core",
    "cucumber.accounts",
    "cucumber.references",
    "cucumber.plants",
    "cucumber.batches",
    "cucumber.events",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "cucumber.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "cucumber.wsgi.application"

# Django connects as DB_USER. Migrations and tests use `cucumber_owner`; the
# running app will use `cucumber_app` (U0.2 design §4, set up in U0.4). With
# debug off it has no default, so a server can't fall back to the owner.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "cucumber"),
        "USER": required("DB_USER", "cucumber_owner"),
        "PASSWORD": required("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "127.0.0.1"),
        "PORT": env("DB_PORT", "5434"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Staff passwords: not too short, too common, all digits, or like the user name.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{name}"}
    for name in [
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    ]
]

# Where CSS and images are served from. Django's test server needs it too.
STATIC_URL = "static/"

# D-16: Bangkok time, English now with Thai to follow.
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Bangkok"
USE_I18N = True
USE_TZ = True
