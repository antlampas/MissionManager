# SPDX-License-Identifier: CC-BY-SA-4.0
"""Profile provider implementations."""

from __future__ import annotations

from auth.domain.access_control import SubjectRef, SubjectType
from auth.domain.profile import AuthorizationProfile
from auth.ports.repositories import AccountRepository, GroupMembershipRepository, ProfileRepository


class RepositoryProfileProvider:
    def __init__(
        self,
        accounts: AccountRepository,
        profiles: ProfileRepository,
        memberships: GroupMembershipRepository | None = None,
    ) -> None:
        self._accounts = accounts
        self._profiles = profiles
        self._memberships = memberships

    def profile_of(self, subject: SubjectRef) -> AuthorizationProfile:
        if subject.type is SubjectType.PUBLIC or subject.id is None:
            return AuthorizationProfile.anonymous()
        account = self._accounts.get_by_id(subject.id)
        if account is None or not account.is_active():
            return AuthorizationProfile.anonymous()
        profile = self._profiles.get(account.profile_id)
        if profile is None:
            return AuthorizationProfile.anonymous()
        if self._memberships is None:
            return profile
        groups = profile.groups | self._memberships.groups_for_account(account.id)
        return AuthorizationProfile(profile.id, profile.level, groups, max(profile.version, account.authz_version))


class StaticProfileProvider:
    def __init__(self, authenticated_profile: AuthorizationProfile | None = None) -> None:
        self._authenticated_profile = authenticated_profile or AuthorizationProfile(id=None, level=1000, groups=frozenset(), version=0)

    def profile_of(self, subject: SubjectRef) -> AuthorizationProfile:
        if subject.type is SubjectType.PUBLIC:
            return AuthorizationProfile.anonymous()
        return self._authenticated_profile
