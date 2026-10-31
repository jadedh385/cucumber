# Cucumber's one image: the app, its migrations and its commands (U0.4a
# design §2, AC1). Two stages on the same pinned Python, so the final image
# holds no build tools. No setting or password is baked in: each server
# passes its own through deploy/compose.server.yaml.

# ---------------------------------------------------------- 1. build stage
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.19@sha256:b46b03ddfcfbf8f547af7e9eaefdf8a39c8cebcba7c98858d3162bd28cf536f6 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app

# Packages first, so a code change doesn't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# The pinned Tailwind CLI, checked by its SHA-256 (U0.10a §3.3). Only css.py
# is copied first, so this layer is downloaded again only when it changes.
# Kept outside /app, so the run stage never copies it.
COPY scripts/__init__.py scripts/css.py scripts/
ENV CUCUMBER_TOOLS=/opt/tools
RUN /app/.venv/bin/python -m scripts.css fetch
COPY . .

# Build the one stylesheet from core/css/source.css (nothing is fetched at
# run time, AC2).
RUN /app/.venv/bin/python -m scripts.css build

# Gather CSS and images, with whitenoise's manifest. Settings need values to
# load, so fake ones are given on this line only: they never reach the image.
RUN DJANGO_ENVIRONMENT=production \
    DJANGO_SECRET_KEY=build-only-not-a-secret-collectstatic-needs-some-value \
    DJANGO_ALLOWED_HOSTS=build.invalid \
    DJANGO_CSRF_TRUSTED_ORIGINS=https://build.invalid \
    DB_USER=none DB_PASSWORD=none \
    /app/.venv/bin/python manage.py collectstatic --noinput

# ------------------------------------------------------------ 2. run stage
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS run
RUN groupadd --system --gid 10001 cucumber \
    && useradd --system --uid 10001 --gid cucumber --no-create-home cucumber
WORKDIR /app
# Owned by root, so the app can read its code but never change it.
COPY --from=build /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER cucumber
EXPOSE 8000

# gthread copes with slow phones on mobile data; --max-requests restarts a
# worker now and then, so slow memory growth never builds up. No control
# socket: it would go under a home folder the read-only container lacks.
CMD ["gunicorn", "cucumber.wsgi", "--bind", "0.0.0.0:8000", "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--timeout", "60", "--max-requests", "1000", "--max-requests-jitter", "100", "--no-control-socket"]
