# SPDX-License-Identifier: CC-BY-SA-4.0
"""Hook point custom delle estensioni (DESIGN §15.7).

Un'estensione può dichiarare e scatenare propri hook point con nome nei punti
interni del suo flusso; i plugin vi si agganciano dichiarando il nome completo
nel manifest. I nomi sono namespaced per estensione:

    BEFORE_EXT:<ext_id>:<event>
    AFTER_EXT:<ext_id>:<event>

Il prefisso ``BEFORE_``/``AFTER_`` riusa la semantica del PluginRegistry:
i BEFORE_* dei plugin TRUSTED possono porre il veto (``ctx.abort = True`` →
``OperationAbortedError``), gli AFTER_* sono notifiche a operazione avvenuta.
Il namespace obbligatorio impedisce a un'estensione di scatenare hook core
"falsi" o di invadere il namespace di un'altra estensione: l'emettitore è
legato all'``ext_id`` verificato dal loader (checksum + registro installati)
e ogni servizio core scatena gli hook con i membri dell'enum ``HookPoint``,
mai con stringhe — un plugin registrato su una stringa qualsiasi non può
quindi intercettare i flussi core.
"""
from __future__ import annotations

import re
from typing import Any, Optional
from uuid import UUID

from ..domain.plugins import HookContext
from .plugin_registry import PluginRegistry

# Charset sicuro: niente ":" (separatore del namespace) né spazi.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_EVENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_EXT_HOOK_RE = re.compile(
    r"^(?:BEFORE|AFTER)_EXT:[A-Za-z0-9][A-Za-z0-9._-]*:[A-Za-z0-9][A-Za-z0-9._-]*$"
)


def is_extension_hook_name(value: object) -> bool:
    """True se ``value`` è un nome valido di hook custom di estensione."""
    return isinstance(value, str) and bool(_EXT_HOOK_RE.match(value))


def before_hook_name(ext_id: str, event: str) -> str:
    return f"BEFORE_EXT:{ext_id}:{event}"


def after_hook_name(ext_id: str, event: str) -> str:
    return f"AFTER_EXT:{ext_id}:{event}"


class ExtensionHookEmitter:
    """Facciata namespaced con cui un'estensione scatena i propri hook.

    Viene costruita dal loader e legata all'id dell'estensione: l'estensione
    non sceglie il namespace, può solo nominare l'evento. Con registry assente
    (nessun plugin configurato) le chiamate sono no-op.
    """

    def __init__(self, plugin_registry: Optional[PluginRegistry], ext_id: str) -> None:
        if not _ID_RE.match(ext_id or ""):
            raise ValueError(
                f"id estensione non utilizzabile come namespace hook: {ext_id!r}"
            )
        self._registry = plugin_registry
        self._ext_id = ext_id

    @property
    def extension_id(self) -> str:
        return self._ext_id

    def fire_before(
        self,
        event: str,
        payload: Optional[dict] = None,
        operator_id: Optional[UUID] = None,
    ) -> Optional[HookContext]:
        """Scatena ``BEFORE_EXT:<ext_id>:<event>``.

        Un plugin TRUSTED può abortire: ``OperationAbortedError`` propaga al
        chiamante (l'estensione non deve procedere con l'operazione).
        """
        return self._fire(before_hook_name(self._ext_id, self._validated(event)),
                          payload, None, operator_id)

    def fire_after(
        self,
        event: str,
        payload: Optional[dict] = None,
        result: Any = None,
        operator_id: Optional[UUID] = None,
    ) -> Optional[HookContext]:
        """Scatena ``AFTER_EXT:<ext_id>:<event>`` a operazione completata."""
        return self._fire(after_hook_name(self._ext_id, self._validated(event)),
                          payload, result, operator_id)

    def _fire(
        self,
        point: str,
        payload: Optional[dict],
        result: Any,
        operator_id: Optional[UUID],
    ) -> Optional[HookContext]:
        # Import locale: evita il ciclo application ↔ application.services.
        from .services._shared import fire_hook

        return fire_hook(
            self._registry, point, operator_id, dict(payload or {}), result=result
        )

    @staticmethod
    def _validated(event: str) -> str:
        if not isinstance(event, str) or not _EVENT_RE.match(event):
            raise ValueError(
                f"nome evento hook non valido: {event!r} (charset ammesso: "
                "alfanumerico, '.', '_', '-'; niente ':')"
            )
        return event
