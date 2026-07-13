# SPDX-License-Identifier: CC-BY-SA-4.0
"""Authorization profiles and groups."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from auth.domain.errors import ValidationError
from auth.domain.types import GroupId, ProfileId

ANON_SENTINEL = 2**31 - 1
PUBLIC_GROUP = "public"


class GroupSource(Enum):
    LOCAL = "local"
    OIDC_TRUSTED = "oidc_trusted"
    EXTERNAL = "external"


@dataclass(frozen=True)
class AuthorizationProfile:
    id: ProfileId | None
    level: int
    groups: frozenset[str]
    version: int

    def __post_init__(self) -> None:
        if self.level < 0:
            raise ValidationError("profile level cannot be negative")
        if self.version < 0:
            raise ValidationError("profile version cannot be negative")
        normalized = frozenset(g.strip() for g in self.groups if g and g.strip())
        object.__setattr__(self, "groups", normalized | {PUBLIC_GROUP})

    @staticmethod
    def anonymous() -> AuthorizationProfile:
        return AuthorizationProfile(
            id=None,
            level=ANON_SENTINEL,
            groups=frozenset({PUBLIC_GROUP}),
            version=0,
        )

    def satisfies_level(self, threshold: int) -> bool:
        return self.level <= threshold


@dataclass(frozen=True)
class Group:
    id: GroupId
    description: str | None
    source: GroupSource
