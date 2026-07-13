# SPDX-License-Identifier: CC-BY-SA-4.0
"""Entry point ASGI per la sola REST API.

    hypercorn "src.asgi_rest:app" --bind 0.0.0.0:8001
"""
from .bootstrap.rest import create_rest_app

app, _svcs = create_rest_app()
