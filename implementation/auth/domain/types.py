# SPDX-License-Identifier: CC-BY-SA-4.0
"""Typed identifiers shared by the pure domain model."""

from typing import NewType

AccountId = NewType("AccountId", str)
ClientRef = NewType("ClientRef", str)
ExternalIdentityId = NewType("ExternalIdentityId", str)
GroupId = NewType("GroupId", str)
ProfileId = NewType("ProfileId", str)
RefreshTokenId = NewType("RefreshTokenId", str)
SessionId = NewType("SessionId", str)
TokenFamilyId = NewType("TokenFamilyId", str)
