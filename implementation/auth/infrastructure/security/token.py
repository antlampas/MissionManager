# SPDX-License-Identifier: CC-BY-SA-4.0
"""Stdlib HMAC token signer for local/dev deployments."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any, Mapping

from auth.domain.errors import AuthenticationError, ValidationError
from auth.ports.security import TokenValidationContext


class HmacTokenSigner:
    def __init__(self, secret: str, *, algorithm: str = "HS256", kid: str | None = None) -> None:
        if not secret:
            raise ValidationError("token signer secret is required")
        if algorithm != "HS256":
            raise ValidationError("HmacTokenSigner supports HS256 only")
        self._secret = secret.encode("utf-8")
        self._algorithm = algorithm
        self._kid = kid

    def sign(self, claims: Mapping[str, Any], *, kid: str | None = None) -> str:
        header = {"typ": "JWT", "alg": self._algorithm}
        effective_kid = kid or self._kid
        if effective_kid:
            header["kid"] = effective_kid
        header_b64 = _b64_json(header)
        payload_b64 = _b64_json(dict(claims))
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        signature = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        return f"{header_b64}.{payload_b64}.{_b64(signature)}"

    def verify(self, token: str, expected: TokenValidationContext) -> Mapping[str, Any]:
        try:
            header_b64, payload_b64, signature_b64 = token.split(".", 2)
            header = _json_b64(header_b64)
            payload = _json_b64(payload_b64)
        except Exception as exc:
            raise AuthenticationError("authentication failed") from exc
        if header.get("alg") not in expected.algorithms:
            raise AuthenticationError("authentication failed")
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(self._secret, signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_sig, _unb64(signature_b64)):
            raise AuthenticationError("authentication failed")
        if payload.get("iss") != expected.issuer or payload.get("aud") != expected.audience:
            raise AuthenticationError("authentication failed")
        now_ts = int(expected.now.timestamp())
        if int(payload.get("nbf", 0)) > now_ts:
            raise AuthenticationError("authentication failed")
        if int(payload.get("exp", 0)) <= now_ts:
            raise AuthenticationError("authentication failed")
        return payload


def _b64_json(value: Mapping[str, Any]) -> str:
    return _b64(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _json_b64(value: str) -> dict[str, Any]:
    decoded = _unb64(value)
    data = json.loads(decoded)
    if not isinstance(data, dict):
        raise ValueError("token segment is not an object")
    return data


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
