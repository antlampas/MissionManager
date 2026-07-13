# SPDX-License-Identifier: CC-BY-SA-4.0
"""Redirect and anti-forgery helpers."""

from __future__ import annotations

import hashlib
import hmac

from auth.domain.policies import ReturnTargetPolicy
from auth.domain.request import AuthRequest


class ReturnTargetRedirectValidator:
    def __init__(self, policy: ReturnTargetPolicy | None = None) -> None:
        self._policy = policy or ReturnTargetPolicy()

    def is_valid(self, target: str | None) -> bool:
        return self._policy.is_valid(target)

    def sanitize(self, target: str | None) -> str:
        return self._policy.sanitize(target)


class HmacAntiForgeryProtector:
    """Small framework-neutral anti-forgery helper.

    The default ``verify(AuthRequest)`` convention looks for a credential
    presentation with ``issuer == "anti_forgery"`` and ``value_ref`` containing
    the issued token. Runtime adapters can also call ``verify_token`` directly.
    """

    def __init__(self, secret: str) -> None:
        self._secret = secret.encode("utf-8")

    def issue(self, secret_id: str) -> str:
        signature = hmac.new(self._secret, secret_id.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{secret_id}:{signature}"

    def verify(self, request: AuthRequest) -> bool:
        for credential in request.credential_presentations:
            if credential.issuer == "anti_forgery" and credential.value_ref:
                return self.verify_token(credential.value_ref)
        return False

    def verify_token(self, token: str) -> bool:
        try:
            secret_id, signature = token.split(":", 1)
        except ValueError:
            return False
        expected = self.issue(secret_id).split(":", 1)[1]
        return hmac.compare_digest(signature, expected)
