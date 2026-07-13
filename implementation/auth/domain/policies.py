# SPDX-License-Identifier: CC-BY-SA-4.0
"""Pure domain policies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit

from auth.domain.access_control import AccessControlCapability
from auth.domain.errors import PasswordPolicyViolation, ValidationError


@dataclass(frozen=True)
class AccessControlModelSpec:
    id: str
    capabilities: frozenset[AccessControlCapability]
    required_providers: frozenset[str]
    admin_operations: frozenset[str]


@dataclass(frozen=True)
class PasswordPolicy:
    min_length: int = 12
    require_uppercase: bool = True
    require_digit: bool = True
    require_special: bool = True

    def validate(self, password: str) -> None:
        if len(password) < self.min_length:
            raise PasswordPolicyViolation("password is too short")
        if self.require_uppercase and not any(ch.isupper() for ch in password):
            raise PasswordPolicyViolation("password requires an uppercase character")
        if self.require_digit and not any(ch.isdigit() for ch in password):
            raise PasswordPolicyViolation("password requires a digit")
        if self.require_special and not any(not ch.isalnum() for ch in password):
            raise PasswordPolicyViolation("password requires a special character")


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class ReturnTargetPolicy:
    """Validate post-auth redirect targets as local, relative HTTP paths."""

    default_target: str = "/"

    def sanitize(self, target: str | None) -> str:
        if not target:
            return self.default_target
        if _CONTROL_CHARS.search(target) or "\\" in target:
            return self.default_target
        split = urlsplit(target)
        if split.scheme or split.netloc:
            return self.default_target
        if not split.path.startswith("/") or split.path.startswith("//"):
            return self.default_target
        return urlunsplit(("", "", split.path or "/", split.query, split.fragment))

    def is_valid(self, target: str | None) -> bool:
        if target is None:
            return False
        return self.sanitize(target) == target


class GrantConstraintPolicy:
    def validate(self, artifact: object, context: Mapping[str, object] | None = None) -> None:
        if artifact is None:
            raise ValidationError("artifact is required")


class SeedingPolicy(GrantConstraintPolicy):
    pass


class ResourceControlPolicy(GrantConstraintPolicy):
    pass


class LabelAssignmentPolicy(GrantConstraintPolicy):
    pass
