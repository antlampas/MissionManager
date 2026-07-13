# SPDX-License-Identifier: CC-BY-SA-4.0
"""Secure random adapter."""

from __future__ import annotations

import secrets
import uuid


class SecretsSecureRandom:
    def token_urlsafe(self, nbytes: int = 32) -> str:
        return secrets.token_urlsafe(nbytes)

    def uuid4_hex(self) -> str:
        return uuid.uuid4().hex
