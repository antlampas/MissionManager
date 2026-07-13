# SPDX-License-Identifier: CC-BY-SA-4.0
"""Raccolta di tutte le pagine degli endpoint di elenco delle admin API OIDC.

Gli endpoint di elenco dei provider sono paginati e restituire solo la prima
pagina falsa gli elenchi e i controlli che vi si basano (es. ``admin_exists``,
che scandisce ``person.list({})``). Questo helper normalizza le due convenzioni:

- **Authentik**: pagina con ``?page=N`` e risponde
  ``{"results": [...], "pagination": {"current", "total_pages", ...}}``.
  In assenza dell'oggetto ``pagination`` la risposta è trattata come pagina unica.
- **Keycloak**: pagina con ``?first=&max=`` e risponde con un array JSON;
  si continua finché una pagina restituisce meno di ``page_size`` righe.

``http`` è il modulo ``requests`` del repository chiamante (passato esplicitamente
così che il monkeypatch dei test resti efficace).
"""
from __future__ import annotations

from ...shared.errors import AuthenticationError, AuthorizationError

# Guardia anti-loop: un provider malfunzionante non deve far ciclare all'infinito.
_MAX_PAGES = 10_000


def collect_pages(
    http,
    provider: str,
    url: str,
    headers: dict,
    params: dict | None = None,
    timeout: int = 10,
    page_size: int = 100,
    verify: bool | str = True,
) -> list[dict]:
    """Restituisce tutte le righe dell'endpoint di elenco, seguendo la paginazione."""
    params = dict(params or {})
    if provider == "authentik":
        return _collect_authentik(http, url, headers, params, timeout, verify)
    return _collect_keycloak(http, url, headers, params, timeout, page_size, verify)


def _collect_authentik(http, url, headers, params, timeout, verify) -> list[dict]:
    rows: list[dict] = []
    page = 1
    for _ in range(_MAX_PAGES):
        resp = http.get(
            url,
            params={**params, "page": page},
            headers=headers,
            timeout=timeout,
            verify=verify,
        )
        _raise_for_status(resp, url)
        data = resp.json()
        if not isinstance(data, dict):
            rows.extend(data)
            break
        rows.extend(data.get("results", []))
        pagination = data.get("pagination")
        if not pagination:  # nessuna paginazione dichiarata: pagina unica
            break
        total_pages = pagination.get("total_pages")
        current = pagination.get("current", page)
        if total_pages is None or current >= total_pages:
            break
        page = current + 1
    return rows


def _collect_keycloak(http, url, headers, params, timeout, page_size, verify) -> list[dict]:
    rows: list[dict] = []
    first = 0
    for _ in range(_MAX_PAGES):
        resp = http.get(
            url,
            params={**params, "first": first, "max": page_size},
            headers=headers,
            timeout=timeout,
            verify=verify,
        )
        _raise_for_status(resp, url)
        data = resp.json()
        batch = data.get("results", data) if isinstance(data, dict) else data
        rows.extend(batch)
        if len(batch) < page_size:
            break
        first += page_size
    return rows


def _raise_for_status(resp, url: str) -> None:
    status = getattr(resp, "status_code", None)
    if status in {401, 403}:
        message = (
            f"Admin API OIDC non autorizzata (HTTP {status}) per {url}. "
            "Verifica MISSIONMANAGER_OIDC_ADMIN_TOKEN: deve essere un token API "
            "dell'identity provider con permessi di lettura/gestione utenti e gruppi."
        )
        if status == 401:
            raise AuthenticationError(message)
        raise AuthorizationError(message)
    resp.raise_for_status()
