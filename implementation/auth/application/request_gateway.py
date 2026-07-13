# SPDX-License-Identifier: CC-BY-SA-4.0
"""Canonical request gateway."""

from __future__ import annotations

from auth.application.dtos import RequestOutcome, RequestOutcomeKind
from auth.application.authorization_service import AuthorizationService
from auth.domain.errors import (
    AuthenticationError,
    AuthorizationDenied,
    ForgeryProtectionError,
    RateLimitExceeded,
    SetupRequired,
    ValidationError,
)
from auth.domain.request import AuthRequest, CredentialMode
from auth.ports.authorization import IdentityResolver
from auth.ports.repositories import AccountRepository
from auth.ports.security import AntiForgeryProtector, RateLimitPolicy, RedirectValidator


class RequestGateway:
    def __init__(
        self,
        identity_resolver: IdentityResolver,
        authorization_service: AuthorizationService,
        *,
        accounts: AccountRepository | None = None,
        rate_limit_policy: RateLimitPolicy | None = None,
        anti_forgery: AntiForgeryProtector | None = None,
        redirect_validator: RedirectValidator | None = None,
    ) -> None:
        self._identity_resolver = identity_resolver
        self._authorization_service = authorization_service
        self._accounts = accounts
        self._rate_limit_policy = rate_limit_policy
        self._anti_forgery = anti_forgery
        self._redirect_validator = redirect_validator

    def handle(self, request: AuthRequest) -> RequestOutcome:
        try:
            identity = self.require(request)
        except RateLimitExceeded as exc:
            return RequestOutcome(RequestOutcomeKind.RATE_LIMITED, retry_after_seconds=exc.retry_after_seconds, reason=str(exc))
        except ForgeryProtectionError as exc:
            return RequestOutcome(RequestOutcomeKind.FORGERY_PROTECTION_FAILED, reason=str(exc))
        except AuthenticationError as exc:
            kind = RequestOutcomeKind.AUTHENTICATION_REQUIRED
            has_real_credential = any(credential.kind.value != "none" for credential in request.credential_presentations)
            if has_real_credential and not request.protection.allow_anonymous:
                kind = RequestOutcomeKind.AUTHENTICATION_FAILED
            return RequestOutcome(kind, reason=str(exc))
        except AuthorizationDenied as exc:
            return RequestOutcome(RequestOutcomeKind.AUTHORIZATION_DENIED, reason=str(exc))
        except SetupRequired as exc:
            return RequestOutcome(RequestOutcomeKind.INTERACTION_REQUIRED, reason=str(exc))
        except ValidationError as exc:
            return RequestOutcome(RequestOutcomeKind.INVALID_REQUEST, reason=str(exc))
        return RequestOutcome(
            RequestOutcomeKind.ALLOWED,
            identity=identity,
            return_target=request.return_target,
        )

    def require(self, request: AuthRequest):
        self._validate_request(request)
        if self._rate_limit_policy is not None:
            result = self._rate_limit_policy.check(request)
            if not result.allowed:
                raise RateLimitExceeded(retry_after_seconds=result.retry_after_seconds)
        if request.protection.require_return_target and self._redirect_validator is not None:
            if not self._redirect_validator.is_valid(request.return_target):
                raise ValidationError("invalid return target")
        if self._requires_anti_forgery(request):
            if self._anti_forgery is None or not self._anti_forgery.verify(request):
                raise ForgeryProtectionError("anti-forgery validation failed")
        identity = self._identity_resolver.resolve(request)
        if identity.account_id is None and not request.protection.allow_anonymous:
            raise AuthenticationError("authentication required")
        if request.protection.require_active_account and identity.account_id is not None and self._accounts is not None:
            account = self._accounts.get_by_id(identity.account_id)
            if account is None or not account.is_active():
                raise AuthenticationError("authentication failed")
        if request.operation is None or request.resource is None:
            raise ValidationError("operation and resource are required")
        self._authorization_service.require(identity, request.operation, request.resource)
        return identity

    def _validate_request(self, request: AuthRequest) -> None:
        if request.mutation and request.operation is None:
            raise ValidationError("mutating requests require an operation")
        if any(c.mode is CredentialMode.ASSERTED for c in request.credential_presentations) and not request.origin.trusted:
            raise ValidationError("asserted credentials require a trusted origin")

    def _requires_anti_forgery(self, request: AuthRequest) -> bool:
        if request.protection.require_anti_forgery:
            return True
        return request.mutation and any(c.mode is CredentialMode.AMBIENT for c in request.credential_presentations)
