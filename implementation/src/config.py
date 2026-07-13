# SPDX-License-Identifier: CC-BY-SA-4.0
"""Configurazione globale di MissionManager.

Unico punto di definizione dei parametri di configurazione, organizzato per
concern: ogni area (database, security/identità, cli, plugin, estensioni, acl,
web, realtime) è una piccola ``dataclass`` con il proprio loader dedicato.

Ogni loader risolve i valori con priorità **variabili d'ambiente > file
YAML/TOML > default**. Il file di configurazione si passa via ``--config`` (CLI)
oppure con la variabile d'ambiente ``MISSIONMANAGER_CONFIG_FILE`` (tutte le
modalità).

Sezioni del file di configurazione:

  database:
    url, pool_size, max_overflow

  web:
    theme, secure_cookies

  security:                       # umbrella identità/autenticazione/CLI
    persons:
      backend (local|oidc), oidc_url, provider, realm, jwks_url, audience,
      issuer, subject_field, cache_ttl
    auth:
      backend (local|oidc), token_ttl,
      oidc_client_id, oidc_client_secret, oidc_redirect_uri,
      revocation_redis_url, revocation_redis_prefix
    rate_limit:
      redis_url, redis_prefix, window_seconds
    cli:
      identity_mode (anonymous|user), operator_id

  acl:
    read_threshold, write_threshold, admin_threshold, seeding_enabled

  realtime:
    redis_url, redis_prefix

  plugins / extensions:
    scan_paths, trust_registry_path / installed_registry_path
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from .shared.errors import ValidationError

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

try:
    import tomllib
    _HAS_TOML = True
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
        _HAS_TOML = True
    except ImportError:
        _HAS_TOML = False


# --------------------------------------------------------------------------- #
# Helper condivisi
# --------------------------------------------------------------------------- #

def _load_file(file_path: Optional[str]) -> dict:
    """Legge un file YAML o TOML e restituisce il contenuto come dizionario.

    Restituisce un dizionario vuoto se il percorso è assente, il file non
    esiste o la libreria di parsing richiesta non è installata. Un file
    sintatticamente non valido (o che non contiene un mapping al livello
    principale) solleva ``ValidationError`` con un messaggio esplicito, invece
    di lasciar propagare un traceback opaco del parser.
    """
    if not file_path or not os.path.exists(file_path):
        return {}
    with open(file_path, "rb") as fh:
        raw = fh.read()
    data = None
    try:
        if file_path.endswith((".yaml", ".yml")):
            if _HAS_YAML:
                data = yaml.safe_load(raw)
        elif file_path.endswith(".toml"):
            if _HAS_TOML:
                data = tomllib.loads(raw.decode())
    except Exception as exc:
        raise ValidationError(
            f"Errore di sintassi nel file di configurazione {file_path!r}: {exc}"
        ) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValidationError(
            f"Il file di configurazione {file_path!r} deve contenere un mapping "
            f"al livello principale, trovato invece: {type(data).__name__}"
        )
    return data


def _to_int(value, name: str) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ValidationError(
            f"Il valore '{name}' deve essere un intero, trovato: {value!r}"
        ) from None


def _to_bool(value, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "on"):
            return True
        if normalized in ("0", "false", "no", "off"):
            return False
    raise ValidationError(
        f"Il valore '{name}' deve essere booleano, trovato: {value!r}"
    )


_VALID_PERSON_BACKENDS = ("local", "oidc")
_VALID_OIDC_PROVIDERS = ("authentik", "keycloak")
_VALID_AUTH_BACKENDS = ("local", "oidc")


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #

@dataclass
class DatabaseConfig:
    """Parametri di connessione al database principale (SQLAlchemy)."""

    url: str = "postgresql+psycopg2://localhost/missionmanager"
    pool_size: int = 5
    max_overflow: int = 10


class DatabaseConfigLoader:
    """Carica la configurazione del database da file YAML/TOML e variabili d'ambiente."""

    @staticmethod
    def load(file_path: Optional[str] = None) -> DatabaseConfig:
        raw = _load_file(file_path or os.environ.get("MISSIONMANAGER_CONFIG_FILE", ""))
        db = raw.get("database", {})

        url = os.environ.get("MISSIONMANAGER_DATABASE_URL") or db.get("url", DatabaseConfig.url)
        pool_size = _to_int(db.get("pool_size", DatabaseConfig.pool_size), "database.pool_size")
        max_overflow = _to_int(
            db.get("max_overflow", DatabaseConfig.max_overflow), "database.max_overflow"
        )
        return DatabaseConfig(url=url, pool_size=pool_size, max_overflow=max_overflow)


# --------------------------------------------------------------------------- #
# Security / identità (backend persone + autenticazione + OIDC)
# --------------------------------------------------------------------------- #

@dataclass
class SecurityConfig:
    """Configurazione di identità, autenticazione e OIDC.

    Raccoglie in un unico contenitore il backend persone/gruppi, il backend di
    autenticazione, i parametri OIDC (sia lato admin API/validazione token sia
    lato Authorization Code flow) e il segreto applicativo. Le persone possono
    restare locali anche con login OIDC; quando auth OIDC è accompagnato dai
    parametri admin dell'IdP, il loader seleziona il backend persone OIDC salvo
    opt-out esplicito. Il backend persone OIDC richiede autenticazione OIDC e
    admin API dell'IdP.
    """

    # Backend persone/gruppi
    person_backend: str = "local"           # "local" | "oidc"

    # OIDC provider (admin API per person backend + validazione JWT per REST)
    oidc_url: Optional[str] = None
    oidc_admin_token: Optional[str] = None
    oidc_jwks_url: Optional[str] = None
    oidc_provider: str = "authentik"        # "authentik" | "keycloak"
    oidc_audience: Optional[str] = None
    oidc_issuer: Optional[str] = None
    oidc_realm: Optional[str] = None        # solo Keycloak
    # Campo utente dell'IdP a cui corrisponde il claim `sub` del token (P1).
    # None ⇒ si assume sub == id usato dall'admin API (Keycloak; Authentik con
    # Subject mode "Based on the User's ID"). Valori tipici Authentik: "uuid",
    # "username", "email".
    oidc_subject_field: Optional[str] = None
    # TTL (secondi) della cache in-memory su OidcPersonRepository.get (P4).
    # <= 0 disabilita la cache.
    oidc_cache_ttl: int = 30

    # OIDC Authorization Code flow (auth_backend=oidc)
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_redirect_uri: Optional[str] = None

    # Backend di autenticazione (come vengono verificate le credenziali)
    auth_backend: str = "local"             # "local" | "oidc"
    local_token_ttl: int = 3600            # secondi validità JWT locale
    token_revocation_redis_url: Optional[str] = None
    token_revocation_redis_prefix: str = "missionmanager"

    # Rate limiting REST condiviso tra worker (opzionale)
    rate_limit_redis_url: Optional[str] = None
    rate_limit_redis_prefix: str = "missionmanager"
    rate_limit_window_seconds: int = 60

    # Password policy locale forte, allineata a PhotoGallery.
    # Applicata da LocalAuthAdapter.set_password.
    password_min_length: int = 12
    password_require_uppercase: bool = True
    password_require_digit: bool = True
    password_require_special: bool = True
    # Account lockout locale: blocco temporizzato dopo troppi login falliti
    # (max_failed_attempts <= 0 disabilita il lockout).
    max_failed_attempts: int = 5
    lockout_duration_seconds: int = 300

    # Verifica TLS verso l'IdP OIDC: True (default), False (solo sviluppo) oppure
    # oidc_ca_bundle = path a un CA bundle custom (IdP con certificato self-signed).
    oidc_verify_tls: bool = True
    oidc_ca_bundle: Optional[str] = None

    # Segreto applicativo (firma JWT locale + sessioni Web). Letto SOLO dall'ambiente.
    secret_key: Optional[str] = None
    # Modalità dev della REST API (bypass validazione firma; solo sviluppo).
    rest_dev_mode: bool = False


class SecurityConfigLoader:
    """Carica identità/autenticazione/OIDC dalle sottosezioni ``security.persons`` e ``security.auth``.

    ``secret_key``, ``rest_dev_mode`` e ``oidc_admin_token`` sono segreti letti
    esclusivamente dall'ambiente e non dal file di configurazione.
    """

    @staticmethod
    def load(file_path: Optional[str] = None) -> SecurityConfig:
        raw = _load_file(file_path or os.environ.get("MISSIONMANAGER_CONFIG_FILE", ""))
        security = raw.get("security", {})
        persons = security.get("persons", {})
        auth = security.get("auth", {})

        oidc_provider = (
            os.environ.get("MISSIONMANAGER_OIDC_PROVIDER")
            or persons.get("provider", SecurityConfig.oidc_provider)
        )
        if oidc_provider not in _VALID_OIDC_PROVIDERS:
            raise ValidationError(f"oidc_provider deve essere uno di {_VALID_OIDC_PROVIDERS}")

        auth_backend = (
            os.environ.get("MISSIONMANAGER_AUTH_BACKEND")
            or auth.get("backend", SecurityConfig.auth_backend)
        )
        if auth_backend not in _VALID_AUTH_BACKENDS:
            raise ValidationError(f"auth.backend deve essere uno di {_VALID_AUTH_BACKENDS}")

        # --- Parametri OIDC lato admin API / validazione token (sezione persons) ---
        oidc_url = os.environ.get("MISSIONMANAGER_OIDC_URL") or persons.get("oidc_url")
        oidc_admin_token = os.environ.get("MISSIONMANAGER_OIDC_ADMIN_TOKEN") or None
        oidc_jwks_url = os.environ.get("MISSIONMANAGER_OIDC_JWKS_URL") or persons.get("jwks_url")
        oidc_audience = os.environ.get("MISSIONMANAGER_OIDC_AUDIENCE") or persons.get("audience")
        oidc_issuer = os.environ.get("MISSIONMANAGER_OIDC_ISSUER") or persons.get("issuer")
        oidc_realm = os.environ.get("MISSIONMANAGER_OIDC_REALM") or persons.get("realm")
        oidc_subject_field = (
            os.environ.get("MISSIONMANAGER_OIDC_SUBJECT_FIELD") or persons.get("subject_field")
        )
        oidc_cache_ttl = _to_int(
            os.environ.get("MISSIONMANAGER_OIDC_CACHE_TTL")
            or persons.get("cache_ttl", SecurityConfig.oidc_cache_ttl),
            "persons.cache_ttl",
        )

        person_backend_env = os.environ.get("MISSIONMANAGER_PERSON_BACKEND")
        person_backend_file = persons.get("backend")
        if person_backend_env:
            person_backend = person_backend_env
        elif auth_backend == "oidc" and oidc_url and oidc_admin_token:
            # Modalità OIDC completa: login federato + gestione persone/gruppi
            # sull'IdP. Il token admin resta non richiesto per il solo login:
            # senza token si resta nel profilo auth OIDC + persone locali.
            person_backend = "oidc"
        else:
            person_backend = person_backend_file or SecurityConfig.person_backend
        if person_backend not in _VALID_PERSON_BACKENDS:
            raise ValidationError(f"person_backend deve essere uno di {_VALID_PERSON_BACKENDS}")

        # --- Parametri OIDC lato Authorization Code flow (sezione auth) ---
        oidc_client_id = (
            os.environ.get("MISSIONMANAGER_OIDC_CLIENT_ID") or auth.get("oidc_client_id")
        )
        oidc_client_secret = (
            os.environ.get("MISSIONMANAGER_OIDC_CLIENT_SECRET") or auth.get("oidc_client_secret")
        )
        oidc_redirect_uri = (
            os.environ.get("MISSIONMANAGER_OIDC_REDIRECT_URI") or auth.get("oidc_redirect_uri")
        )
        local_token_ttl = _to_int(
            os.environ.get("MISSIONMANAGER_LOCAL_TOKEN_TTL")
            or auth.get("token_ttl", SecurityConfig.local_token_ttl),
            "auth.token_ttl",
        )
        rate_limit = security.get("rate_limit", {})
        rate_limit_redis_url = (
            os.environ.get("MISSIONMANAGER_RATE_LIMIT_REDIS_URL")
            or rate_limit.get("redis_url")
        )
        rate_limit_redis_prefix = (
            os.environ.get("MISSIONMANAGER_RATE_LIMIT_REDIS_PREFIX")
            or rate_limit.get("redis_prefix", SecurityConfig.rate_limit_redis_prefix)
        )
        rate_limit_window_seconds = _to_int(
            os.environ.get("MISSIONMANAGER_RATE_LIMIT_WINDOW_SECONDS")
            or rate_limit.get("window_seconds", SecurityConfig.rate_limit_window_seconds),
            "security.rate_limit.window_seconds",
        )
        if rate_limit_window_seconds <= 0:
            raise ValidationError("security.rate_limit.window_seconds deve essere maggiore di zero")
        token_revocation_redis_url = (
            os.environ.get("MISSIONMANAGER_TOKEN_REVOCATION_REDIS_URL")
            or auth.get("revocation_redis_url")
            or rate_limit_redis_url
        )
        token_revocation_redis_prefix = (
            os.environ.get("MISSIONMANAGER_TOKEN_REVOCATION_REDIS_PREFIX")
            or auth.get("revocation_redis_prefix")
            or rate_limit_redis_prefix
        )

        # --- Password policy locale + account lockout (sezione auth) ---
        password = auth.get("password", {})
        password_min_length = _to_int(
            os.environ.get("MISSIONMANAGER_PASSWORD_MIN_LENGTH")
            or password.get("min_length", SecurityConfig.password_min_length),
            "auth.password.min_length",
        )
        password_require_uppercase = _to_bool(
            os.environ.get("MISSIONMANAGER_PASSWORD_REQUIRE_UPPERCASE")
            or str(password.get("require_uppercase", SecurityConfig.password_require_uppercase)),
            "auth.password.require_uppercase",
        )
        password_require_digit = _to_bool(
            os.environ.get("MISSIONMANAGER_PASSWORD_REQUIRE_DIGIT")
            or str(password.get("require_digit", SecurityConfig.password_require_digit)),
            "auth.password.require_digit",
        )
        password_require_special = _to_bool(
            os.environ.get("MISSIONMANAGER_PASSWORD_REQUIRE_SPECIAL")
            or str(password.get("require_special", SecurityConfig.password_require_special)),
            "auth.password.require_special",
        )
        max_failed_attempts = _to_int(
            os.environ.get("MISSIONMANAGER_MAX_FAILED_ATTEMPTS")
            or auth.get("max_failed_attempts", SecurityConfig.max_failed_attempts),
            "auth.max_failed_attempts",
        )
        lockout_duration_seconds = _to_int(
            os.environ.get("MISSIONMANAGER_LOCKOUT_DURATION_SECONDS")
            or auth.get("lockout_duration_seconds", SecurityConfig.lockout_duration_seconds),
            "auth.lockout_duration_seconds",
        )
        oidc_verify_tls = _to_bool(
            os.environ.get("MISSIONMANAGER_OIDC_VERIFY_TLS")
            or str(persons.get("verify_tls", SecurityConfig.oidc_verify_tls)),
            "persons.verify_tls",
        )
        oidc_ca_bundle = (
            os.environ.get("MISSIONMANAGER_OIDC_CA_BUNDLE") or persons.get("ca_bundle")
        )

        # --- Segreti letti solo dall'ambiente ---
        secret_key = os.environ.get("MISSIONMANAGER_SECRET_KEY") or None
        rest_dev_mode = _to_bool(
            os.environ.get("MISSIONMANAGER_REST_DEV_MODE") or "false",
            "MISSIONMANAGER_REST_DEV_MODE",
        )

        config = SecurityConfig(
            person_backend=person_backend,
            oidc_url=oidc_url,
            oidc_admin_token=oidc_admin_token,
            oidc_jwks_url=oidc_jwks_url,
            oidc_provider=oidc_provider,
            oidc_audience=oidc_audience,
            oidc_issuer=oidc_issuer,
            oidc_realm=oidc_realm,
            oidc_subject_field=oidc_subject_field,
            oidc_cache_ttl=oidc_cache_ttl,
            oidc_client_id=oidc_client_id,
            oidc_client_secret=oidc_client_secret,
            oidc_redirect_uri=oidc_redirect_uri,
            auth_backend=auth_backend,
            local_token_ttl=local_token_ttl,
            token_revocation_redis_url=token_revocation_redis_url,
            token_revocation_redis_prefix=token_revocation_redis_prefix,
            rate_limit_redis_url=rate_limit_redis_url,
            rate_limit_redis_prefix=rate_limit_redis_prefix,
            rate_limit_window_seconds=rate_limit_window_seconds,
            password_min_length=password_min_length,
            password_require_uppercase=password_require_uppercase,
            password_require_digit=password_require_digit,
            password_require_special=password_require_special,
            max_failed_attempts=max_failed_attempts,
            lockout_duration_seconds=lockout_duration_seconds,
            oidc_verify_tls=oidc_verify_tls,
            oidc_ca_bundle=oidc_ca_bundle,
            secret_key=secret_key,
            rest_dev_mode=rest_dev_mode,
        )
        _validate_backends(config)
        return config


def _validate_backends(config: SecurityConfig) -> None:
    """Verifica le invarianti che coinvolgono più parametri di identità."""
    if config.person_backend == "oidc" and config.auth_backend != "oidc":
        raise ValidationError(
            "person_backend='oidc' richiede auth_backend='oidc': non e' supportata "
            "la gestione persone/gruppi sull'IdP con autenticazione locale "
            f"(person_backend={config.person_backend!r}, auth_backend={config.auth_backend!r})."
        )
    if (
        config.person_backend == "oidc"
        and config.oidc_provider == "keycloak"
        and not config.oidc_realm
    ):
        raise ValidationError("persons.realm è obbligatorio per Keycloak")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

@dataclass
class CliConfig:
    """Identità con cui la CLI esegue le operazioni."""

    identity_mode: str = "anonymous"        # "anonymous" | "user"
    operator_id: Optional[str] = None


class CliConfigLoader:
    """Carica l'identità CLI dalla sottosezione ``security.cli`` e dalle variabili d'ambiente."""

    @staticmethod
    def load(file_path: Optional[str] = None) -> CliConfig:
        raw = _load_file(file_path or os.environ.get("MISSIONMANAGER_CONFIG_FILE", ""))
        cli = raw.get("security", {}).get("cli", {})

        identity_mode = (
            os.environ.get("MISSIONMANAGER_CLI_IDENTITY_MODE")
            or cli.get("identity_mode", CliConfig.identity_mode)
        )
        operator_id = os.environ.get("MISSIONMANAGER_OPERATOR_ID") or cli.get("operator_id")

        if identity_mode == "user" and not operator_id:
            raise ValidationError(
                "cli_identity_mode 'user' richiede cli_operator_id. "
                "Impostare la variabile d'ambiente MISSIONMANAGER_OPERATOR_ID."
            )
        return CliConfig(identity_mode=identity_mode, operator_id=operator_id)


# --------------------------------------------------------------------------- #
# Plugin
# --------------------------------------------------------------------------- #

@dataclass
class PluginConfig:
    """Configurazione del sistema di plugin."""

    scan_paths: list[str] = field(default_factory=list)
    trust_registry_path: Optional[str] = None   # JSON: {plugin_name: "TRUSTED"|"SANDBOXED"}


class PluginConfigLoader:
    """Carica la configurazione dei plugin da file YAML/TOML e variabili d'ambiente.

    ``MISSIONMANAGER_PLUGINS_SCAN_PATHS`` accetta più percorsi separati da ``:``.
    """

    @staticmethod
    def load(file_path: Optional[str] = None) -> PluginConfig:
        raw = _load_file(file_path or os.environ.get("MISSIONMANAGER_CONFIG_FILE", ""))
        plugins = raw.get("plugins", {})

        scan_env = os.environ.get("MISSIONMANAGER_PLUGINS_SCAN_PATHS")
        if scan_env:
            scan_paths = [p.strip() for p in scan_env.split(":") if p.strip()]
        else:
            scan_paths = list(plugins.get("scan_paths", []))

        trust_path = (
            os.environ.get("MISSIONMANAGER_PLUGINS_TRUST_REGISTRY")
            or plugins.get("trust_registry_path")
        )
        return PluginConfig(scan_paths=scan_paths, trust_registry_path=trust_path)


# --------------------------------------------------------------------------- #
# Estensioni
# --------------------------------------------------------------------------- #

@dataclass
class ExtensionConfig:
    """Configurazione del sistema di estensioni."""

    scan_paths: list[str] = field(default_factory=list)
    installed_registry_path: Optional[str] = None   # JSON: {ext_name: {code_checksum: ...}}


class ExtensionConfigLoader:
    """Carica la configurazione delle estensioni da file YAML/TOML e variabili d'ambiente.

    ``MISSIONMANAGER_EXTENSIONS_SCAN_PATHS`` accetta più percorsi separati da ``:``.
    """

    @staticmethod
    def load(file_path: Optional[str] = None) -> ExtensionConfig:
        raw = _load_file(file_path or os.environ.get("MISSIONMANAGER_CONFIG_FILE", ""))
        ext = raw.get("extensions", {})

        scan_env = os.environ.get("MISSIONMANAGER_EXTENSIONS_SCAN_PATHS")
        if scan_env:
            scan_paths = [p.strip() for p in scan_env.split(":") if p.strip()]
        else:
            scan_paths = list(ext.get("scan_paths", []))

        installed_path = (
            os.environ.get("MISSIONMANAGER_EXTENSIONS_INSTALLED_REGISTRY")
            or ext.get("installed_registry_path")
        )
        return ExtensionConfig(scan_paths=scan_paths, installed_registry_path=installed_path)


# --------------------------------------------------------------------------- #
# ACL (DESIGN §10)
# --------------------------------------------------------------------------- #

@dataclass
class AclConfig:
    """Soglie ACL di bootstrap.

    Convenzione D3/D8: una soglia ``L`` è soddisfatta da chi ha livello ``<= L``
    (numero più basso = più privilegio). Le soglie sono usate una sola volta,
    per seminare le entry di default su ``SYSTEM:global`` e sulle radici di tipo
    quando il repository ACL è vuoto; da lì in poi le regole si amministrano come
    ``AclEntry`` (pagina ``/acl`` e REST).
    """

    read_threshold: int = 100     # lettura (VIEW/LIST)
    write_threshold: int = 50     # mutazioni operative (Gestore)
    admin_threshold: int = 0      # anagrafica, profili e MANAGE_ACL (Amministratore)
    # Seeding automatico (D7): alla creazione di una risorsa il creatore riceve
    # le entry previste dalla SeedingPolicy (default: MANAGE_ACL sulla risorsa).
    seeding_enabled: bool = True


class AclConfigLoader:
    """Carica le soglie ACL dalla sezione ``acl`` e dalle variabili d'ambiente."""

    @staticmethod
    def load(file_path: Optional[str] = None) -> AclConfig:
        raw = _load_file(file_path or os.environ.get("MISSIONMANAGER_CONFIG_FILE", ""))
        acl = raw.get("acl", {})

        read_threshold = _to_int(
            os.environ.get("MISSIONMANAGER_ACL_READ_THRESHOLD")
            or acl.get("read_threshold", AclConfig.read_threshold),
            "acl.read_threshold",
        )
        write_threshold = _to_int(
            os.environ.get("MISSIONMANAGER_ACL_WRITE_THRESHOLD")
            or acl.get("write_threshold", AclConfig.write_threshold),
            "acl.write_threshold",
        )
        admin_threshold = _to_int(
            os.environ.get("MISSIONMANAGER_ACL_ADMIN_THRESHOLD")
            or acl.get("admin_threshold", AclConfig.admin_threshold),
            "acl.admin_threshold",
        )
        seeding_env = os.environ.get("MISSIONMANAGER_ACL_SEEDING_ENABLED")
        if seeding_env is not None:
            seeding_enabled = _to_bool(seeding_env, "MISSIONMANAGER_ACL_SEEDING_ENABLED")
        else:
            seeding_enabled = _to_bool(
                acl.get("seeding_enabled", AclConfig.seeding_enabled), "acl.seeding_enabled"
            )
        return AclConfig(
            read_threshold=read_threshold,
            write_threshold=write_threshold,
            admin_threshold=admin_threshold,
            seeding_enabled=seeding_enabled,
        )


# --------------------------------------------------------------------------- #
# Web App / sessione
# --------------------------------------------------------------------------- #

@dataclass
class WebConfig:
    """Configurazione del frontend Web."""

    theme: str = "default"
    # Marca il cookie di sessione della Web App come Secure (HTTPS-only).
    # True di default (sicuro in produzione dietro TLS); imposta a False per lo
    # sviluppo locale su HTTP, altrimenti il browser scarta il cookie e il
    # login/setup falliscono con "Token CSRF mancante o non valido".
    secure_cookies: bool = True


class WebConfigLoader:
    """Carica la configurazione del web frontend dalla sezione ``web``."""

    @staticmethod
    def load(file_path: Optional[str] = None) -> WebConfig:
        raw = _load_file(file_path or os.environ.get("MISSIONMANAGER_CONFIG_FILE", ""))
        web = raw.get("web", {})

        theme = os.environ.get("MISSIONMANAGER_WEB_THEME") or web.get("theme", WebConfig.theme)
        secure_env = os.environ.get("MISSIONMANAGER_WEB_SECURE_COOKIES")
        if secure_env is not None:
            secure_cookies = _to_bool(secure_env, "MISSIONMANAGER_WEB_SECURE_COOKIES")
        else:
            secure_cookies = _to_bool(
                web.get("secure_cookies", WebConfig.secure_cookies), "web.secure_cookies"
            )
        return WebConfig(theme=theme, secure_cookies=secure_cookies)


# --------------------------------------------------------------------------- #
# Realtime (WebSocket)
# --------------------------------------------------------------------------- #

@dataclass
class RealtimeConfig:
    """Distribuzione realtime opzionale: se ``redis_url`` è None il notifier è in-process."""

    redis_url: Optional[str] = None
    redis_prefix: str = "missionmanager"


class RealtimeConfigLoader:
    """Carica la configurazione realtime dalla sezione ``realtime``."""

    @staticmethod
    def load(file_path: Optional[str] = None) -> RealtimeConfig:
        raw = _load_file(file_path or os.environ.get("MISSIONMANAGER_CONFIG_FILE", ""))
        realtime = raw.get("realtime", {})

        redis_url = os.environ.get("MISSIONMANAGER_REDIS_URL") or realtime.get("redis_url")
        redis_prefix = (
            os.environ.get("MISSIONMANAGER_REDIS_PREFIX")
            or realtime.get("redis_prefix", RealtimeConfig.redis_prefix)
        )
        return RealtimeConfig(redis_url=redis_url, redis_prefix=redis_prefix)


__all__ = [
    "_load_file",
    "DatabaseConfig",
    "DatabaseConfigLoader",
    "SecurityConfig",
    "SecurityConfigLoader",
    "CliConfig",
    "CliConfigLoader",
    "PluginConfig",
    "PluginConfigLoader",
    "ExtensionConfig",
    "ExtensionConfigLoader",
    "AclConfig",
    "AclConfigLoader",
    "WebConfig",
    "WebConfigLoader",
    "RealtimeConfig",
    "RealtimeConfigLoader",
]
