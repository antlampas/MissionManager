# SPDX-License-Identifier: CC-BY-SA-4.0
"""Bootstrap condiviso: costruisce tutti i componenti del sistema.

Questo modulo è il punto unico di composizione (Composition Root).
Tutti i frontend (REST, Web, CLI) chiamano build_system() e ricevono
un BootstrappedSystem pronto all'uso. Ogni sottosistema carica la propria
sezione di configurazione tramite il loader dedicato in ``config.py``.

Ordine di composizione:
  database → repository → cross-cutting concerns (rate_limit, audit)
  → plugin (loader+registry) → service applicativi → estensioni
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from ..infrastructure.repositories.activity_repository import SqlAlchemyActivityRepository
from ..infrastructure.repositories.assignment_repository import SqlAlchemyMissionAssignmentRepository
from ..infrastructure.repositories.badge_award_repository import SqlAlchemyBadgeAwardRepository
from ..infrastructure.repositories.badge_repository import SqlAlchemyBadgeRepository
from ..infrastructure.repositories.credential_repository import SqlAlchemyCredentialRepository
from ..infrastructure.repositories.mission_repository import SqlAlchemyMissionRepository
from ..infrastructure.repositories.models import Base
from ..infrastructure.repositories.session import (
    SqlAlchemySessionProvider,
    SqlAlchemyUnitOfWork,
)
from ..infrastructure.repositories.objective_repository import SqlAlchemyObjectiveRepository
from ..infrastructure.repositories.external_identity_repository import (
    SqlAlchemyExternalIdentityRepository,
)
from ..infrastructure.repositories.acl_entry_repository import (
    SqlAlchemyAclEntryRepository,
)
from ..infrastructure.acl import (
    MissionResourceHierarchyProvider,
    PersonProfileProvider,
)
from ..infrastructure.event_publisher import EventPublisher
from ..infrastructure.extensions.installed_registry import InstalledManifestRegistry
from ..infrastructure.extensions.loader import ExtensionLoader
from ..infrastructure.plugins.loader import PluginLoader
from ..infrastructure.plugins.trust_registry import PluginTrustRegistry
from ..infrastructure.security.audit_logger import AuditLogger, NoOpAuditLogger
from ..infrastructure.security.rate_limit import InMemoryRateLimitPolicy, NoOpRateLimitPolicy
from ..infrastructure.security.redis import RedisRateLimitPolicy
from ..config import (
    AclConfigLoader,
    DatabaseConfigLoader,
    ExtensionConfigLoader,
    PluginConfigLoader,
    RealtimeConfigLoader,
    SecurityConfig,
    SecurityConfigLoader,
)
from ..domain.repositories import PersonRepository
from ..application.services.activity_service import ActivityService
from ..application.services.assignment_service import AssignmentService
from ..application.services.auth_service import AuthService
from ..application.authorization import AuthorizationPolicy
from ..application.services.badge_service import BadgeService
from ..application.services.mission_service import MissionService
from ..application.services.person_service import PersonService
from ..application.services.acl_service import AclService, SeedingPolicy
from ..application.plugin_registry import PluginRegistry
from ..application.extension_registry import ExtensionRegistry


@dataclass
class BootstrappedSystem:
    """Container di tutti i componenti del sistema assemblati al bootstrap.

    Supporta accesso per attributo: ``system.mission``, ``system.event_publisher``, …
    """

    mission: MissionService
    assignment: AssignmentService
    activity: ActivityService
    badge: BadgeService
    person: PersonService
    acl: AclService
    person_repo: PersonRepository
    acl_entry_repo: SqlAlchemyAclEntryRepository
    auth_policy: AuthorizationPolicy
    auth_service: AuthService
    plugin_registry: PluginRegistry
    extension_registry: ExtensionRegistry
    event_publisher: EventPublisher
    rate_limit_policy: InMemoryRateLimitPolicy | RedisRateLimitPolicy | NoOpRateLimitPolicy
    audit_logger: AuditLogger | NoOpAuditLogger
    session: SqlAlchemySessionProvider
    uow: SqlAlchemyUnitOfWork


def build_system(config_file: Optional[str] = None) -> BootstrappedSystem:
    """Costruisce e restituisce tutti i componenti del sistema.

    ``config_file`` è il path del file di configurazione; se ``None`` viene
    letto da ``MISSIONMANAGER_CONFIG_FILE``. Ogni sottosistema carica la propria
    sezione tramite il loader dedicato (priorità env > file > default).

    Ogni unità di lavoro apre una ``Session`` propria tramite il provider
    contestuale; le chiamate annidate condividono la stessa transazione.
    """
    resolved_config = config_file or os.environ.get("MISSIONMANAGER_CONFIG_FILE")
    db_config = DatabaseConfigLoader.load(resolved_config)
    security_config = SecurityConfigLoader.load(resolved_config)
    acl_config = AclConfigLoader.load(resolved_config)
    plugin_config = PluginConfigLoader.load(resolved_config)
    ext_config = ExtensionConfigLoader.load(resolved_config)
    realtime_config = RealtimeConfigLoader.load(resolved_config)

    engine = create_engine(
        db_config.url,
        pool_size=db_config.pool_size,
        max_overflow=db_config.max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
    )
    _wait_for_db(engine)
    session_factory = sessionmaker(bind=engine)
    sessions = SqlAlchemySessionProvider(session_factory)
    uow = SqlAlchemyUnitOfWork(sessions)

    # ---- Repository ----
    mission_repo = SqlAlchemyMissionRepository(sessions)
    assignment_repo = SqlAlchemyMissionAssignmentRepository(sessions)
    objective_repo = SqlAlchemyObjectiveRepository(sessions)
    activity_repo = SqlAlchemyActivityRepository(sessions)
    badge_repo = SqlAlchemyBadgeRepository(sessions)
    badge_award_repo = SqlAlchemyBadgeAwardRepository(sessions)
    credential_repo = SqlAlchemyCredentialRepository(sessions)
    acl_entry_repo = SqlAlchemyAclEntryRepository(sessions)

    external_identity_repo = SqlAlchemyExternalIdentityRepository(sessions)
    person_repo, group_repo = _build_person_repos(
        security_config, sessions, external_identity_repo
    )

    # ---- Sistema Auth/ACL (DESIGN §10): ACL come modello Auth + servizio ACL ----
    profile_provider = PersonProfileProvider(person_repo)
    hierarchy_provider = MissionResourceHierarchyProvider(
        assignment_repo=assignment_repo,
        objective_repo=objective_repo,
        activity_repo=activity_repo,
    )
    auth_policy = AuthorizationPolicy(
        entry_repo=acl_entry_repo,
        profile_provider=profile_provider,
        hierarchy_provider=hierarchy_provider,
        uow=uow,
    )
    acl_svc = AclService(
        entry_repo=acl_entry_repo,
        authorization=auth_policy,
        seeding_policy=SeedingPolicy(enabled=acl_config.seeding_enabled),
        uow=uow,
    )
    # Il sistema nasce senza entry e nega tutto: semina le soglie di default
    # (una sola volta, su repository vuoto) da SYSTEM:global e radici di tipo.
    acl_svc.ensure_bootstrap_entries(
        read_threshold=acl_config.read_threshold,
        write_threshold=acl_config.write_threshold,
        admin_threshold=acl_config.admin_threshold,
    )

    # ---- Cross-cutting concerns ----
    event_publisher = EventPublisher(sessions, uow)
    if security_config.rate_limit_redis_url:
        rate_limit_policy = RedisRateLimitPolicy(
            security_config.rate_limit_redis_url,
            security_config.rate_limit_redis_prefix,
            window_seconds=security_config.rate_limit_window_seconds,
        )
    else:
        rate_limit_policy = InMemoryRateLimitPolicy()
    audit_logger = AuditLogger()
    event_publisher.register_consumer("audit", audit_logger.handle_outbox_event)

    # ---- Plugin ----
    trust_registry = PluginTrustRegistry(plugin_config.trust_registry_path)
    plugin_registry = PluginRegistry(trust_registry)
    if plugin_config.scan_paths:
        PluginLoader(plugin_config.scan_paths, trust_registry).load_into(plugin_registry)

    # ---- Services ----
    activity_svc = ActivityService(
        activity_repo=activity_repo,
        objective_repo=objective_repo,
        assignment_repo=assignment_repo,
        person_repo=person_repo,
        group_repo=group_repo,
        authorization_policy=auth_policy,
        plugin_registry=plugin_registry,
        event_publisher=event_publisher,
        uow=uow,
    )
    assignment_svc = AssignmentService(
        assignment_repo=assignment_repo,
        mission_repo=mission_repo,
        person_repo=person_repo,
        group_repo=group_repo,
        activity_svc=activity_svc,
        objective_repo=objective_repo,
        acl_service=acl_svc,
        authorization_policy=auth_policy,
        plugin_registry=plugin_registry,
        event_publisher=event_publisher,
        uow=uow,
    )
    mission_svc = MissionService(
        mission_repo=mission_repo,
        acl_service=acl_svc,
        authorization_policy=auth_policy,
        plugin_registry=plugin_registry,
        event_publisher=event_publisher,
        assignment_repo=assignment_repo,
        uow=uow,
    )
    badge_svc = BadgeService(
        badge_repo=badge_repo,
        badge_award_repo=badge_award_repo,
        assignment_repo=assignment_repo,
        activity_repo=activity_repo,
        person_repo=person_repo,
        acl_service=acl_svc,
        authorization_policy=auth_policy,
        plugin_registry=plugin_registry,
        event_publisher=event_publisher,
        uow=uow,
    )
    person_svc = PersonService(
        person_repo=person_repo,
        group_repo=group_repo,
        authorization_policy=auth_policy,
        plugin_registry=plugin_registry,
        acl_service=acl_svc,
        uow=uow,
    )

    revocation_store = None
    if security_config.token_revocation_redis_url:
        from ..infrastructure.security.redis import RedisTokenRevocationStore
        revocation_store = RedisTokenRevocationStore(
            security_config.token_revocation_redis_url,
            security_config.token_revocation_redis_prefix,
        )

    auth_svc = _build_auth_service(
        security_config,
        person_repo,
        credential_repo,
        uow,
        revocation_store=revocation_store,
    )

    # ---- Extensions ----
    installed_registry = InstalledManifestRegistry(ext_config.installed_registry_path)
    extension_loader = ExtensionLoader(
        scan_paths=ext_config.scan_paths,
        installed_registry=installed_registry,
        mission_svc=mission_svc,
        assignment_svc=assignment_svc,
        activity_svc=activity_svc,
        badge_svc=badge_svc,
        person_svc=person_svc,
        acl_svc=acl_svc,
        event_publisher=event_publisher,
    )
    extensions = extension_loader.load_all()
    extension_registry = ExtensionRegistry()
    for ext in extensions:
        try:
            extension_registry.register(ext)
        except Exception:
            logging.getLogger(__name__).exception(
                "Bootstrap: estensione non registrata: %s", ext.manifest.id
            )

    return BootstrappedSystem(
        mission=mission_svc,
        assignment=assignment_svc,
        activity=activity_svc,
        badge=badge_svc,
        person=person_svc,
        acl=acl_svc,
        person_repo=person_repo,
        acl_entry_repo=acl_entry_repo,
        auth_policy=auth_policy,
        auth_service=auth_svc,
        plugin_registry=plugin_registry,
        extension_registry=extension_registry,
        event_publisher=event_publisher,
        rate_limit_policy=rate_limit_policy,
        audit_logger=audit_logger,
        session=sessions,
        uow=uow,
    )


def _wait_for_db(engine, max_attempts: int = 12, base_delay: float = 2.0) -> None:
    """Attende che il DB sia pronto, con backoff esponenziale.

    Usato all'avvio Docker dove MySQL può impiegare qualche secondo dopo
    che il container risulta "healthy" a livello TCP.
    """
    _log = logging.getLogger(__name__)
    for attempt in range(max_attempts):
        try:
            Base.metadata.create_all(engine)
            return
        except OperationalError as exc:
            if attempt == max_attempts - 1:
                raise
            delay = min(base_delay * (2 ** attempt), 30.0)
            _log.warning(
                "DB non raggiungibile (tentativo %d/%d): %s — riprovo tra %.0fs",
                attempt + 1,
                max_attempts,
                exc.orig,
                delay,
            )
            time.sleep(delay)


def build_system_for_cli(config_file: Optional[str] = None) -> BootstrappedSystem:
    """Variante di build_system per la CLI: usa NoOp per rate_limit e audit.

    La CLI locale non ha bisogno di rate limiting o audit strutturato —
    questi componenti genererebbero rumore inutile nei log.
    """
    system = build_system(config_file)
    system.rate_limit_policy = NoOpRateLimitPolicy()
    system.audit_logger = NoOpAuditLogger()
    system.event_publisher.replace_consumer(
        "audit", system.audit_logger.handle_outbox_event
    )
    return system


def _build_person_repos(config: SecurityConfig, session, external_identity_repo):
    if config.person_backend == "oidc":
        from ..infrastructure.oidc.group_repository import OidcGroupRepository
        from ..infrastructure.oidc.person_repository import OidcPersonRepository

        if not config.oidc_url:
            raise RuntimeError("person_backend=oidc ma oidc_url non è configurata")
        if not config.oidc_admin_token:
            raise RuntimeError("person_backend=oidc ma oidc_admin_token non è configurata")

        oidc_url = _oidc_admin_base_url(config)
        oidc_verify = config.oidc_ca_bundle or config.oidc_verify_tls
        person_repo = OidcPersonRepository(
            oidc_url=oidc_url,
            admin_token=config.oidc_admin_token,
            provider=config.oidc_provider,
            identity_repo=external_identity_repo,
            subject_field=config.oidc_subject_field,
            cache_ttl=config.oidc_cache_ttl,
            verify=oidc_verify,
        )
        group_repo = OidcGroupRepository(
            oidc_url=oidc_url,
            admin_token=config.oidc_admin_token,
            provider=config.oidc_provider,
            identity_repo=external_identity_repo,
            verify=oidc_verify,
        )
    else:
        from ..infrastructure.repositories.group_repository import SqlAlchemyGroupRepository
        from ..infrastructure.repositories.person_repository import SqlAlchemyPersonRepository

        person_repo = SqlAlchemyPersonRepository(session)
        group_repo = SqlAlchemyGroupRepository(session)
        if config.auth_backend == "oidc":
            from ..infrastructure.oidc.local_person_repository import (
                LocalOidcPersonRepository,
            )

            person_repo = LocalOidcPersonRepository(
                person_repo,
                external_identity_repo,
                provider=config.oidc_provider,
            )

    return person_repo, group_repo


def _oidc_admin_base_url(config: SecurityConfig) -> str:
    """Normalizza l'endpoint admin dei provider senza ignorare ``oidc_realm``."""
    assert config.oidc_url is not None
    base = config.oidc_url.rstrip("/")
    if config.oidc_provider != "keycloak":
        return base
    if "/admin/realms/" in base:
        return base
    if not config.oidc_realm:
        raise RuntimeError("person_backend=oidc con Keycloak richiede oidc_realm")
    return f"{base}/admin/realms/{config.oidc_realm}"


def _build_auth_service(
    config: SecurityConfig,
    person_repo,
    credential_repo,
    uow,
    revocation_store=None,
) -> AuthService:
    local_auth = None
    oidc_client = None

    if config.auth_backend == "local":
        if not config.secret_key:
            raise RuntimeError(
                "auth_backend=local richiede secret_key (MISSIONMANAGER_SECRET_KEY)"
            )
        from ..infrastructure.auth.local import LocalAuthAdapter, PasswordPolicy
        local_auth = LocalAuthAdapter(
            secret_key=config.secret_key,
            person_repo=person_repo,
            cred_repo=credential_repo,
            token_ttl=config.local_token_ttl,
            password_policy=PasswordPolicy(
                min_length=config.password_min_length,
                require_uppercase=config.password_require_uppercase,
                require_digit=config.password_require_digit,
                require_special=config.password_require_special,
            ),
            max_failed_attempts=config.max_failed_attempts,
            lockout_duration_seconds=config.lockout_duration_seconds,
            revocation_store=revocation_store,
            uow=uow,
        )

    elif config.auth_backend == "oidc":
        if not config.oidc_issuer:
            raise RuntimeError(
                "auth_backend=oidc richiede oidc_issuer (URL emittente OIDC)"
            )
        if not config.oidc_client_id:
            raise RuntimeError("auth_backend=oidc richiede oidc_client_id")
        from ..infrastructure.auth.oidc_client import OidcAuthClient
        oidc_client = OidcAuthClient(
            issuer_url=config.oidc_issuer,
            client_id=config.oidc_client_id,
            client_secret=config.oidc_client_secret,
            verify=config.oidc_ca_bundle or config.oidc_verify_tls,
        )

    return AuthService(
        person_repo=person_repo,
        local_auth=local_auth,
        oidc_client=oidc_client,
        oidc_redirect_uri=config.oidc_redirect_uri,
        person_backend=config.person_backend,
        auth_backend=config.auth_backend,
        oidc_auto_provision_local=(
            config.person_backend == "local" and config.auth_backend == "oidc"
        ),
        password_min_length=config.password_min_length,
        password_require_uppercase=config.password_require_uppercase,
        password_require_digit=config.password_require_digit,
        password_require_special=config.password_require_special,
        uow=uow,
    )
