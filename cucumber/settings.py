"""Cucumber settings.

Every value comes from an environment variable through `env()`. Locally they
come from `.env` (copied from `.env.example`); on GitHub the CI workflow sets
them. See `.env.example` for what each one means.
"""

from pathlib import Path

from cucumber.env import env

BASE_DIR = Path(__file__).resolve().parent.parent

# Debug pages show code and settings to whoever triggers an error, so debug is
# on only when DJANGO_DEBUG is exactly "1" (U0.3 AC12).
DEBUG = env("DJANGO_DEBUG") == "1"

SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-not-a-secret")

ALLOWED_HOSTS = [
    host.strip()
    for host in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "cucumber.core",
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
# running app will use `cucumber_app` (U0.2 design §4, set up in U0.4).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "cucumber"),
        "USER": env("DB_USER", "cucumber_owner"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", "127.0.0.1"),
        "PORT": env("DB_PORT", "5434"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Where CSS and images are served from. Django's test server needs it too.
STATIC_URL = "static/"

# D-16: Bangkok time, English now with Thai to follow.
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Bangkok"
USE_I18N = True
USE_TZ = True
