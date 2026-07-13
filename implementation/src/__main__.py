# SPDX-License-Identifier: CC-BY-SA-4.0
"""CLI entrypoint: python -m src [--config PATH] <command> [args...]

Run from implementation/. The REST API and Web App frontends are pure ASGI
callables exposed by src.asgi (rest_app, web_app). Serving is handled entirely
by an external ASGI server (Hypercorn, Uvicorn, …) placed behind a reverse
proxy such as nginx — no web server code lives in this package.

CLI examples (run from implementation/):
  python -m src mission list
  python -m src --config /etc/missionmanager/config.yaml person list
  python -m src assignment create --mission-id <uuid> --person-id <uuid>
"""
import sys


def main(argv=None) -> None:
    raw = list(argv if argv is not None else sys.argv[1:])

    config_file = None
    if "--config" in raw:
        idx = raw.index("--config")
        if idx + 1 >= len(raw):
            print("Errore: --config richiede il percorso del file di configurazione", file=sys.stderr)
            raise SystemExit(2)
        config_file = raw[idx + 1]
        del raw[idx: idx + 2]

    from .bootstrap.cli import create_cli_app
    app = create_cli_app(config_file)
    app.run(args=raw, standalone_mode=True)


if __name__ == "__main__":
    main()
