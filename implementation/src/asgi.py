# SPDX-License-Identifier: CC-BY-SA-4.0
"""ASGI entry points lazy per MissionManager.

Serve the REST API (run from implementation/):
    hypercorn "src.asgi:rest_app" --bind 127.0.0.1:8001

Serve the Web App (run from implementation/):
    MISSIONMANAGER_SECRET_KEY="..." hypercorn "src.asgi:web_app" --bind 127.0.0.1:8000

Le callable sono costruite solo quando l'ASGI server chiede l'attributo relativo:
avviare ``rest_app`` non inizializza più la Web App né richiede la sua session key.
"""


def __getattr__(name: str):
    if name == "rest_app":
        from .bootstrap.rest import create_rest_app

        app, services = create_rest_app()
        globals()["rest_app"] = app
        globals()["_rest_svcs"] = services
        return app
    if name == "web_app":
        from .bootstrap.web import create_web_app

        app, services = create_web_app()
        globals()["web_app"] = app
        globals()["_web_svcs"] = services
        return app
    raise AttributeError(name)
