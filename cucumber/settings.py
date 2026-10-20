"""Cucumber settings.

Every value comes from an environment variable through `env()`. Locally they
come from `.env` (copied from `.env.example`); on GitHub the CI workflow sets
them; on the servers, each environment's `secrets.env` (copied from
`deploy/secrets.env.example`). See those files for what each one means.
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


# Which copy this is (U0.4a design §4.2): local work, staging or production.
ENVIRONMENTS = ("local", "staging", "production")
ENVIRONMENT = required("DJANGO_ENVIRONMENT", "local")
if ENVIRONMENT not in ENVIRONMENTS:
    raise ImproperlyConfigured(
        f"DJANGO_ENVIRONMENT must be local, staging or production, not {ENVIRONMENT!r}."
    )
IS_SERVER = ENVIRONMENT in ("staging", "production")
if IS_SERVER and DEBUG:
    raise ImproperlyConfigured(
        f"DJANGO_DEBUG must be off when DJANGO_ENVIRONMENT is {ENVIRONMENT}."
    )


def required_on_servers(name: str) -> str:
    """A variable staging and production can't start without (U0.4a AC5)."""
    value = env(name)
    if value or not IS_SERVER:
        return value
    raise ImproperlyConfigured(
        f"{name} must be set when DJANGO_ENVIRONMENT is {ENVIRONMENT}. "
        "See deploy/secrets.env.example."
    )


def comma_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = required("DJANGO_SECRET_KEY", "dev-only-not-a-secret")
# Django's own rule for `check --deploy`, checked at every server start too.
SECRET_KEY_MIN_LENGTH = 50
SECRET_KEY_MIN_DIFFERENT_CHARACTERS = 5
if IS_SERVER and (
    len(SECRET_KEY) < SECRET_KEY_MIN_LENGTH
    or len(set(SECRET_KEY)) < SECRET_KEY_MIN_DIFFERENT_CHARACTERS
    or SECRET_KEY.startswith("django-insecure-")
):
    raise ImproperlyConfigured(
        f"DJANGO_SECRET_KEY must be at least {SECRET_KEY_MIN_LENGTH} random "
        f"characters when DJANGO_ENVIRONMENT is {ENVIRONMENT}. "
        "See deploy/secrets.env.example."
    )

ALLOWED_HOSTS = comma_list(required("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1"))
if not DEBUG and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must list real host names when debug is off, not '*'."
    )

# Forms are sent through Cloudflare, so Django must trust the public address.
CSRF_TRUSTED_ORIGINS = comma_list(required_on_servers("DJANGO_CSRF_TRUSTED_ORIGINS"))
if IS_SERVER and not all(o.startswith("https://") for o in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured(
        "Each DJANGO_CSRF_TRUSTED_ORIGINS entry must start with https://."
    )

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "waffle",
    "cucumber.core",
    "cucumber.accounts",
    "cucumber.references",
    "cucumber.plants",
    "cucumber.batches",
    "cucumber.events",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves CSS and images from the app itself (U0.4a design §2).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # U0.5 design §5, in this order: the 30-day limit, then every page needs a
    # login, then a temporary password must be changed first.
    "cucumber.accounts.middleware.SessionLimit",
    "cucumber.accounts.middleware.LoginRequired",
    "cucumber.accounts.middleware.PasswordChangeDue",
    # U0.6 design §3: each page's matrix row must allow the person's role.
    "cucumber.accounts.middleware.RoleRequired",
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
                "cucumber.core.context_processors.environment",
                "cucumber.accounts.context_processors.permissions",
            ],
        },
    },
]

WSGI_APPLICATION = "cucumber.wsgi.application"

# Django connects as DB_USER. Migrations and tests use `cucumber_owner`; the
# running app uses `cucumber_app` (U0.2 design §4). With debug off it has no
# default, so a server can't fall back to the owner.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "cucumber"),
        "USER": required("DB_USER", "cucumber_owner"),
        "PASSWORD": required("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "127.0.0.1"),
        "PORT": env("DB_PORT", "5434"),
        # A save waiting on another save's lock gives up after 5 seconds
        # instead of hanging (U0.4a AC8).
        "OPTIONS": {"options": "-c lock_timeout=5s"},
        # Reuse a connection for a minute, checking it first, so a database
        # restart leaves no broken connections behind.
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
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

# Logging in (U0.5 design §4). Staff use their own phones (spec Q2): a session
# ends after 7 days without a page, and always 30 days after logging in
# (SESSION_MAX_AGE in accounts/services.py, checked by SessionLimit).
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_AGE = 7 * 24 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# CSS and images. `collectstatic` gathers them into staticfiles/ for the image.
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Feature flags (U0.4a design §7). Waffle's cache would be separate in every
# gunicorn worker, so a change could show on some pages and not others; the
# dummy cache means one small query per check and no stale answers.
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "flags": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
}
WAFFLE_CACHE_NAME = "flags"
WAFFLE_CREATE_MISSING_FLAGS = False  # flags are made by migrations only
WAFFLE_FLAG_DEFAULT = False  # a missing flag is off
WAFFLE_OVERRIDE = False  # `?dwft_<name>=1` must not switch a flag

# Errors and warnings go to the container log, one plain line each. No error
# emails, and no request bodies, cookies or settings are written.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        # Cucumber's own lines, e.g. logins and account changes (U0.5 design §8),
        # written through the root's console handler.
        "cucumber": {"level": "INFO"},
    },
}

# D-16: Bangkok time, English now with Thai to follow.
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Bangkok"
USE_I18N = True
USE_TZ = True


# ------------------------------------------- staging and production (AC7)
def hsts_seconds() -> int:
    """From DJANGO_HSTS_SECONDS: 1 hour at first, raised in U0.4b (design §4.3)."""
    value = env("DJANGO_HSTS_SECONDS", "3600")
    if not value.isdigit():
        raise ImproperlyConfigured(
            f"DJANGO_HSTS_SECONDS must be whole seconds, e.g. 3600, not {value!r}."
        )
    return int(value)


if IS_SERVER:
    # Cloudflare ends HTTPS and says so in this header. Safe because the
    # app's port is open to the server itself only.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = hsts_seconds()
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False
    # W021 asks for preload, which works only for a whole domain, and
    # southeastcanopy.com isn't Cucumber's alone to preload.
    SILENCED_SYSTEM_CHECKS = ["security.W021"]
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        },
    }
