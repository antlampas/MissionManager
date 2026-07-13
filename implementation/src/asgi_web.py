# SPDX-License-Identifier: CC-BY-SA-4.0
"""Entry point ASGI per la sola Web App.

    hypercorn "src.asgi_web:app" --bind 0.0.0.0:8000
"""
from .bootstrap.web import create_web_app

app, _svcs = create_web_app()
