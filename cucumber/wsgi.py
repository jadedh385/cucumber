"""Entry point for the web server that runs Cucumber."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cucumber.settings")

application = get_wsgi_application()
