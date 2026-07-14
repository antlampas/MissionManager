# SPDX-License-Identifier: CC-BY-SA-4.0
"""Helper condivisi tra i service applicativi.

Questo modulo contiene:
  - Istanze singleton delle policy di dominio usate da tutti i service
  - Factory per HookContext
  - Helper per la pubblicazione degli audit log

I service importano da qui invece di duplicare la logica.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
from contextvars import ContextVar, Token
from functools import wraps
from typing import Optional
from uuid import UUID

from ...domain.acl import Operation, ResourceRef
from ...domain.plugins import HookContext, HookPoint
from ...domain.exceptions import AuthorizationError, ValidationError
from ...domain.policies import (
    ActivityAssignmentPolicy,
    AssignmentStatusPolicy,
    BadgeAwardPolicy,
)

# ── Policy singleton ─────────────────────────────────────────────────────────
# Istanze condivise (stateless) delle policy di dominio.
# I service le importano direttamente senza dover istanziare ogni volta.

ASSIGNMENT_STATUS_POLICY = AssignmentStatusPolicy()
BADGE_AWARD_POLICY = BadgeAwardPolicy()
ACTIVITY_ASSIGNMENT_POLICY = ActivityAssignmentPolicy()


_UNSET = object()
_CURRENT_OPERATOR_ID: ContextVar[UUID | None | object] = ContextVar(
    "missionmanager_current_operator_id",
    default=_UNSET,
)
_ACL_BYPASS: ContextVar[bool] = ContextVar(
    "missionmanager_acl_bypass",
    default=False,
)


def set_current_operator_id(operator_id: Optional[UUID]) -> Token:
    """Imposta l'operatore corrente per i controlli service-level."""
    return _CURRENT_OPERATOR_ID.set(operator_id)


def reset_current_operator_id(token: Token) -> None:
    _CURRENT_OPERATOR_ID.reset(token)


@contextmanager
def acl_bypass():
    """Bypass esplicito per bootstrap controllati, mai implicito nelle service call."""
    token = _ACL_BYPASS.set(True)
    try:
        yield
    finally:
        _ACL_BYPASS.reset(token)


def _resolve_operator(operator_id: Optional[UUID]) -> tuple[Optional[UUID], bool]:
    if operator_id is not None:
        return operator_id, True
    current = _CURRENT_OPERATOR_ID.get()
    if current is _UNSET:
        return None, False
    return current, True


def require_acl(authorization, operator_id: Optional[UUID], operation: Operation, resource: ResourceRef) -> None:
    """Controllo ACL difensivo dentro i service.

    Se il middleware/decorator CLI ha impostato il contesto, anche ``None`` è
    significativo: viene valutato come profilo anonimo e quindi negato se l'ACL
    non concede esplicitamente l'operazione al pubblico. Le chiamate interne senza
    contesto falliscono chiuse, salvo bypass esplicito di bootstrap.
    """
    if _ACL_BYPASS.get():
        return
    if authorization is None:
        return
    principal_id, has_security_context = _resolve_operator(operator_id)
    if not has_security_context:
        raise AuthorizationError("Contesto di sicurezza mancante per il controllo ACL")
    if not authorization.is_allowed(principal_id, operation, resource):
        raise AuthorizationError("Accesso negato dalle ACL")


# ── HookContext factory ───────────────────────────────────────────────────────

def fire_hook(
    plugin_registry,
    hook_point: HookPoint,
    operator_id: Optional[UUID],
    payload: dict,
    result=None,
) -> Optional[HookContext]:
    """Esegue gli hook del punto indicato se il registry è presente.

    L'operatore è risolto in modo lasco: nei flussi anonimi ammessi (es. la
    creazione del primo amministratore) resta ``None`` nel contesto. I hook
    BEFORE_* possono abortire: il registry solleva ``OperationAbortedError``.
    """
    if plugin_registry is None:
        return None
    resolved_operator_id, _ = _resolve_operator(operator_id)
    ctx = HookContext(
        hook_point=hook_point,
        operator_id=resolved_operator_id,
        payload=payload,
    )
    if result is not None:
        ctx.result = result
    plugin_registry.fire(hook_point, ctx)
    return ctx


def make_hook_context(
    hook_point: HookPoint,
    operator_id: Optional[UUID] = None,
    payload: Optional[dict] = None,
) -> HookContext:
    """Crea un HookContext con un operatore effettivamente autenticato."""
    return HookContext(
        hook_point=hook_point,
        operator_id=require_operator_id(operator_id),
        payload=payload or {},
    )


def require_operator_id(operator_id: Optional[UUID]) -> UUID:
    """Impedisce che eventi e hook vengano attribuiti a UUID inventati."""
    resolved_operator_id, has_security_context = _resolve_operator(operator_id)
    if not has_security_context or resolved_operator_id is None:
        raise ValidationError(
            "operator_id è obbligatorio per le operazioni mutanti",
            field="operator_id",
        )
    return resolved_operator_id


def transactional(method):
    """Avvolge un caso d'uso mutante nell'unità di lavoro iniettata.

    Nei test unitari con repository in-memory ``_uow`` può essere ``None``;
    il comportamento rimane allora quello precedente.
    """
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        uow = getattr(self, "_uow", None)
        if uow is None:
            return method(self, *args, **kwargs)
        with uow.transaction():
            return method(self, *args, **kwargs)
    return wrapper


# ── Timestamp helper ─────────────────────────────────────────────────────────

def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)
