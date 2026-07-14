# MissionManager

Sistema per la **gestione del ciclo di vita di missioni operative**. Gli operatori definiscono missioni articolate in obiettivi e attività, le assegnano a persone e gruppi, avanzano gli stati lungo una macchina a stati disciplinata e riconoscono i completamenti con badge propagati automaticamente agli assegnatari.

La stessa logica di business è accessibile tramite tre interfacce distinte:

- **REST API JSON** asincrona (Quart — callable ASGI)
- **Web App** asincrona con notifiche realtime via WebSocket (Quart — callable ASGI)
- **CLI** da terminale (Click)

Le interfacce web e REST API sono **callable ASGI pure**: non includono alcun server web. Il serving è delegato a un ASGI server esterno (Hypercorn, Uvicorn, ecc.) posizionato dietro un reverse proxy come nginx.

---

## Indice

1. [Scopo del progetto](#1-scopo-del-progetto)
2. [Architettura](#2-architettura)
   - 2.1 [Modello del dominio](#21-modello-del-dominio)
   - 2.2 [Architettura a cinque layer](#22-architettura-a-cinque-layer)
   - 2.3 [Struttura del codice](#23-struttura-del-codice)
3. [Installazione](#3-installazione)
   - 3.1 [Vista sistemista: messa in esercizio](#31-vista-sistemista-messa-in-esercizio)
4. [Configurazione](#4-configurazione)
5. [Quickstart — CLI](#5-quickstart--cli)
   - 5.1 [Uso operativo per utenti](#51-uso-operativo-per-utenti)
6. [Deployment — Web App](#6-deployment--web-app)
7. [Deployment — REST API](#7-deployment--rest-api)
8. [Sistema di Plugin](#8-sistema-di-plugin)
9. [Sistema di Estensioni](#9-sistema-di-estensioni)
10. [Documentazione di riferimento](#10-documentazione-di-riferimento)
11. [Licenza](#11-licenza)

---

## 1. Scopo del progetto

MissionManager gestisce il ciclo di vita completo di operazioni strutturate:

- **Blueprint di missione**: definizione riutilizzabile con obiettivi e attività
- **Assegnazioni**: ogni missione può essere assegnata a più persone o gruppi; ogni assegnazione porta la propria copia indipendente di obiettivi e attività con stato ed esito autonomi
- **Ciclo di vita**: macchina a stati `UNASSIGNED → ASSIGNED → IN_PROGRESS → COMPLETED/FAILED` applicata nel dominio
- **Badge**: riconoscimenti propagati automaticamente agli assegnatari al completamento di un'assegnazione o di un'attività
- **Gestione persone e gruppi**: ciclo di vita completo, con backend locale (database) o remoto (OIDC: Authentik/Keycloak)
- **Plugin ed estensioni**: hook su operazioni esistenti e aggiunta di nuove operazioni senza modificare il core

---

## 2. Architettura

### 2.1 Modello del dominio

Le entità principali e le loro relazioni:

```
Mission (blueprint)
  ├── AssignmentPolicy     ← limiti su quante volte può essere assegnata
  └── [Objective]
        └── [Activity]     ← almeno 1 per obiettivo (definite al momento della creazione)

MissionAssignment (esecuzione)
  ├── status: UNASSIGNED → ASSIGNED → IN_PROGRESS → COMPLETED/FAILED
  ├── assignee: Person | Group
  ├── [Objective (copia)]
  │     └── [Activity (copia)]  ← stato e assegnatari propri
  └── BadgeAward?          ← creato solo a COMPLETED, propagato agli assegnatari

Badge                      ← definizione riutilizzabile del riconoscimento
BadgeAward                 ← assegnazione a un MissionAssignment o a un'Activity

Person  ←  Profile         ← profilo ACL (level + groups; livello più basso = più privilegiato)
AclEntry                   ← regola di autorizzazione: chi (soggetto+livello/gruppo) può
                             fare cosa (Operation) su quale risorsa, ALLOW|DENY
Group   →  [Person]        ← aggregato di persone
Zone    (attributo opzionale di Group: GEOGRAPHIC | VIRTUAL)
```

**Regole di dominio chiave:**

- Una missione deve avere ≥ 1 obiettivo; ogni obiettivo deve avere ≥ 1 attività valida con titolo non vuoto (creati insieme)
- L'esito di obiettivi e assegnazioni è **calcolato** dagli stati terminali delle entità figlio, non impostato manualmente
- La transizione `ASSIGNED → IN_PROGRESS` su un `MissionAssignment` scatta **automaticamente** quando la prima attività interna passa a `IN_PROGRESS`
- Un `BadgeAward` può essere creato solo se il target è in stato `COMPLETED`; ogni target riceve al massimo un `BadgeAward`
- Il controllo ACL è **dichiarativo a entry** (`AclEntry`, DENY > ALLOW > default-deny, ereditarietà gerarchica) e avviene **al confine del sistema** (middleware dei frontend), mai nelle entità di dominio — vedi [DESIGN §10](design/DESIGN.md#10-sistema-acl-e-autorizzazione)

### 2.2 Architettura a cinque layer

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 5 — Frontends                                        │
│  REST API (Quart /api)  │  Web App (Quart /)  │  CLI (Click)│
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│  Layer 4 — Services                                         │
│  MissionService · AssignmentService · ActivityService       │
│  BadgeService · PersonService                               │
│  PluginRegistry · ExtensionRegistry                         │
│  AuthorizationPolicy · DTO                                  │
└──────────────────────────────┬──────────────────────────────┘
                               │ usa contratti
┌──────────────────────────────▼──────────────────────────────┐ ┌──────────────────┐
│  Layer 2 — Ports (contratti astratti)                       │◄─┤  Layer 3         │
│  *Repository · PersonRepository · GroupRepository           │  │  Adapters        │
│  OperatorIdentityProvider · MissionHook · MissionExtension  │  │  (SQLAlchemy,    │
└──────────────────────────────┬──────────────────────────────┘  │   OIDC, Hook)    │
                               │                                  │                  │
┌──────────────────────────────▼──────────────────────────────┐  │ implementano i   │
│  Layer 1 — Domain (nucleo, nessuna dipendenza esterna)      │◄─┤ contratti Layer 2│
│  Mission · MissionAssignment · Objective · Activity         │  └──────────────────┘
│  Badge · BadgeAward · Status (enum comportamentale)         │
│  AssignmentPolicy · Profile · AclEntry · Person · Group ·   │
│  Zone                                                       │
└─────────────────────────────────────────────────────────────┘
```

**Principio fondamentale**: le dipendenze puntano sempre verso l'interno. Il Domain non dipende da nulla. I Services dipendono dai contratti del Layer 2, mai dagli adapter del Layer 3. Gli adapter vengono iniettati tramite Dependency Injection al bootstrap.

**`Status` come enum comportamentale**: la macchina a stati è incapsulata nell'enum stesso tramite `can_transition_to()` e `is_terminal()`, evitando logica condizionale dispersa nei service.

**Backend persone intercambiabile**: `PersonRepository` e `GroupRepository` sono contratti. L'implementazione concreta si seleziona tramite configurazione:
- `local` — SQLAlchemy su PostgreSQL o MySQL
- `oidc` — Authentik o Keycloak via API admin REST

### 2.3 Struttura del codice

```
implementation/
  src/
    domain/
      entities.py          ← Mission, MissionAssignment, Objective, Activity,
                              Badge, BadgeAward, Person, Group, Zone
      value_objects.py     ← AssignmentPolicy
      acl.py               ← nucleo ACL: AclEntry, Profile, Operation, Permission
      enums.py             ← Status, AssigneeType, ZoneType
      exceptions.py        ← re-export delle eccezioni applicative
      repositories.py      ← contratti repository (Protocol)
      identity.py          ← OperatorIdentityProvider
      plugins.py           ← MissionHook, HookContext, HookPoint, PluginManifest
      extensions.py        ← MissionExtension, ExtensionManifest, RouteSpec, ...
    infrastructure/
      base.py              ← RepositoryAdapter[T] (classe base astratta)
      repositories/        ← implementazioni SQLAlchemy (PostgreSQL / MySQL)
      oidc/                ← implementazioni OIDC (Authentik / Keycloak)
      identity/            ← OperatorIdentityAdapter per REST, Web, CLI
      auth/                ← autenticazione locale e client OIDC
      plugins/             ← loader e trust registry dei plugin
      extensions/          ← loader e integrity registry delle estensioni
      security/            ← rate limit e audit logger
    application/
      services/
        mission_service.py
        assignment_service.py
        activity_service.py
        badge_service.py
        person_service.py
        auth_service.py
        dto.py             ← MissionDTO, AssignmentDTO, ObjectiveDTO, ...
      authorization.py     ← AuthorizationPolicy (stateless)
      plugin_registry.py
      extension_registry.py
    frontend/
      api/                 ← RestApp (Quart), AuthMiddleware, ErrorHandler, Router*
      web/                 ← create_web_blueprint() / create_web_app(), ACLMiddleware, RealtimeNotifier, Handler*
      cli/                 ← CLIApp, OutputFormatter, Commands*
    bootstrap/
      rest.py              ← create_rest_app() — factory ASGI per la REST API
      web.py               ← create_web_app() — factory ASGI per la Web App
      cli.py               ← create_cli_app()
      common.py            ← costruzione service condivisa
    config.py              ← loader modulari per concern (*ConfigLoader) — YAML/TOML + variabili d'ambiente
    asgi.py                ← callable ASGI già pronte: rest_app, web_app
    __main__.py            ← entrypoint CLI del package Python
```

---

## 3. Installazione

**Requisiti**: Python 3.11+ (Python 3.10 supportato con `tomli` come dipendenza aggiuntiva).

```bash
# 1. Spostati nella directory che contiene il package sorgente
cd "MissionManager/implementation"

# 2. Crea e attiva un ambiente virtuale
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate          # Windows

# 3. Installa le dipendenze Python del progetto
pip install -r src/requirements.txt
```

**Dipendenze principali:**

| Pacchetto | Ruolo |
|-----------|-------|
| `quart>=0.19` | Framework web asincrono — espone callable ASGI (REST API + Web App) |
| `click>=8.1` | Framework CLI |
| `sqlalchemy>=2.0` | ORM per PostgreSQL e MySQL |
| `psycopg2-binary>=2.9` | Driver PostgreSQL |
| `pymysql>=1.1` | Driver MySQL |
| `PyYAML>=6.0` | Lettura configurazione YAML |
| `PyJWT[crypto]>=2.8` | Validazione JWT (modalità OIDC) |
| `requests>=2.31` | Client HTTP per API admin OIDC |

> **ASGI server e reverse proxy** — non inclusi nel progetto. Installare separatamente nell'ambiente di deployment:
> ```bash
> pip install hypercorn   # oppure: pip install uvicorn
> ```
> nginx (o altro reverse proxy) va configurato sul sistema operativo host.

**Preparazione database** (backend `local`):

```bash
# PostgreSQL (raccomandato)
createdb missionmanager

# oppure MySQL
mysql -u root -e "CREATE DATABASE missionmanager CHARACTER SET utf8mb4;"
```

Le tabelle vengono create automaticamente al primo avvio tramite SQLAlchemy.

### 3.1 Vista sistemista: messa in esercizio

Per un'installazione amministrata su server, prepara l'ambiente in questo ordine:

1. Crea un utente di sistema dedicato, una directory applicativa e un virtualenv Python sotto `implementation/`.
2. Crea il database PostgreSQL o MySQL e un utente DB con privilegi limitati allo schema MissionManager.
3. Copia un file di configurazione in un percorso gestito, ad esempio `/etc/missionmanager/config.yaml`, partendo da `implementation/config.yaml` e cambiando almeno `database.url`, backend persone/autenticazione e percorsi plugin/estensioni.
4. Fornisci i segreti solo via ambiente o secret manager: `MISSIONMANAGER_SECRET_KEY`, eventuale `MISSIONMANAGER_OIDC_CLIENT_SECRET`, eventuale `MISSIONMANAGER_OIDC_ADMIN_TOKEN`.
5. Installa e avvia un ASGI server esterno per `src.asgi:web_app` e/o `src.asgi:rest_app`; in produzione tienilo dietro un reverse proxy TLS.
6. Se usi più worker o processi separati REST/Web e vuoi notifiche realtime coerenti, configura `MISSIONMANAGER_REDIS_URL`.
7. Esegui il primo bootstrap amministrativo con `person create-superuser` o tramite `/setup` della Web App.

Esempio minimale di unità systemd per la Web App:

```ini
[Unit]
Description=MissionManager Web App
After=network.target

[Service]
User=missionmanager
WorkingDirectory=/opt/missionmanager/implementation
Environment=MISSIONMANAGER_CONFIG_FILE=/etc/missionmanager/config.yaml
Environment=MISSIONMANAGER_SECRET_KEY=change-this-with-a-secret-manager-value
ExecStart=/opt/missionmanager/implementation/.venv/bin/hypercorn src.asgi:web_app --bind 127.0.0.1:8000 --workers 4
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Per la REST API usa la stessa struttura sostituendo `src.asgi:web_app` con
`src.asgi:rest_app` e una porta interna diversa, ad esempio `127.0.0.1:8001`.
Le sezioni [Deployment — Web App](#6-deployment--web-app) e
[Deployment — REST API](#7-deployment--rest-api) mostrano i blocchi nginx di
riferimento.

---

## 4. Configurazione

Il sistema legge la configurazione da un file YAML o TOML. Il path viene passato con `--config` oppure tramite la variabile d'ambiente `MISSIONMANAGER_CONFIG_FILE`. Le variabili d'ambiente hanno **priorità sul file** di configurazione.

**Esempio `config.yaml`:**

```yaml
# Persistenza — database principale (missioni, badge, assegnazioni)
database:
  url: postgresql+psycopg2://user:pass@localhost/missionmanager
  pool_size: 5
  max_overflow: 10

# Frontend Web / sessione Quart. Nota: secret_key si legge SOLO da
# MISSIONMANAGER_SECRET_KEY (mai dal file), almeno 32 caratteri.
web:
  theme: default
  secure_cookies: true           # false per dev locale su HTTP

# Sicurezza — umbrella: backend persone, autenticazione, OIDC, identità CLI.
# Per login OIDC senza admin API dell'IdP usa auth.backend=oidc senza
# MISSIONMANAGER_OIDC_ADMIN_TOKEN. Se auth.backend=oidc e sono presenti
# MISSIONMANAGER_OIDC_URL + MISSIONMANAGER_OIDC_ADMIN_TOKEN, utenti/gruppi sono
# gestiti sull'IdP tramite admin API, salvo MISSIONMANAGER_PERSON_BACKEND=local.
security:
  persons:
    backend: local               # local (SQLAlchemy) | oidc (Authentik/Keycloak)
    # Per backend: oidc
    # oidc_url: https://auth.example.com
    # provider: authentik         # oppure: keycloak
    # realm: master               # solo per Keycloak
    # jwks_url: https://auth.example.com/application/o/missionmanager/jwks/   # REST + auth oidc
    # audience: missionmanager    # REST + auth oidc
    # subject_field: uuid         # campo IdP ↔ claim `sub`; ometti se sub == id admin
    # cache_ttl: 30               # TTL (s) cache get() utenti OIDC; <=0 disabilita
    # admin_token: impostare con MISSIONMANAGER_OIDC_ADMIN_TOKEN
    # verify_tls: true            # false o ca_bundle per IdP con cert self-signed
    # ca_bundle: /path/to/ca.pem
  auth:
    backend: local               # local (password + JWT locale) | oidc
    token_ttl: 3600
    # Hardening backend locale (login timing-safe + policy + lockout):
    max_failed_attempts: 5        # <=0 disabilita il lockout
    lockout_duration_seconds: 300
    password:
      min_length: 12              # default restrittivo; riduci esplicitamente se serve
      require_uppercase: true
      require_digit: true
      require_special: true
    # Per backend: oidc (Authorization Code flow):
    # oidc_client_id: missionmanager
    # oidc_client_secret: ...     # meglio via MISSIONMANAGER_OIDC_CLIENT_SECRET
    # oidc_redirect_uri: https://app.example.com/auth/callback
  cli:
    identity_mode: user           # "anonymous" | "user"
    # operator_id: impostare con MISSIONMANAGER_OPERATOR_ID

# Sistema ACL — soglie di bootstrap (vedi design/DESIGN.md §10.8).
# Convenzione: livello più basso = più privilegiato; una soglia L è soddisfatta
# da chi ha livello <= L. Usate SOLO per seminare le entry di default al primo
# avvio (database vuoto); da lì in poi le regole si amministrano come AclEntry
# (pagina web /acl, REST /api/acl/entries, CLI `acl`).
acl:
  read_threshold: 100      # lettura (VIEW/LIST)
  write_threshold: 50      # mutazioni operative (Gestore)
  admin_threshold: 0       # identità, profili e MANAGE_ACL (Amministratore)
  seeding_enabled: true    # il creatore di una risorsa riceve MANAGE_ACL su di essa

# Realtime multi-worker opzionale: senza Redis, le notifiche WebSocket restano
# in-process; con Redis vengono distribuite tra processi REST/Web separati.
realtime:
  # redis_url: redis://localhost:6379/0
  redis_prefix: missionmanager

# Plugin e Estensioni (opzionali)
plugins:
  scan_paths:
    - /var/lib/missionmanager/plugins

extensions:
  scan_paths:
    - /var/lib/missionmanager/extensions
```

**Variabili d'ambiente disponibili:**

| Variabile | Descrizione |
|-----------|-------------|
| `MISSIONMANAGER_CONFIG_FILE` | Path al file di configurazione |
| `MISSIONMANAGER_DATABASE_URL` | URL SQLAlchemy (es. `postgresql+psycopg2://...`) |
| `MISSIONMANAGER_PERSON_BACKEND` | `local` o `oidc` |
| `MISSIONMANAGER_OIDC_URL` | URL base dell'identity provider OIDC |
| `MISSIONMANAGER_OIDC_ADMIN_TOKEN` | Token admin OIDC per operazioni su Person/Group; con `auth_backend=oidc` e `OIDC_URL` abilita il backend persone OIDC salvo `MISSIONMANAGER_PERSON_BACKEND=local` |
| `MISSIONMANAGER_OIDC_JWKS_URL` | URL JWKS per validazione JWT (richiesto per REST con auth_backend=oidc) |
| `MISSIONMANAGER_OIDC_ISSUER` | URL emittente OIDC per validazione JWT (richiesto con auth_backend=oidc) |
| `MISSIONMANAGER_OIDC_AUDIENCE` | Audience OIDC per validazione JWT (richiesto per REST con auth_backend=oidc) |
| `MISSIONMANAGER_OIDC_PROVIDER` | Provider OIDC: `authentik` (default) o `keycloak` |
| `MISSIONMANAGER_OIDC_SUBJECT_FIELD` | Campo utente IdP a cui corrisponde il claim `sub` (es. `uuid`); ometti se `sub` == id admin |
| `MISSIONMANAGER_OIDC_CACHE_TTL` | TTL (secondi) della cache di lettura utenti OIDC; `<=0` disabilita (default 30) |
| `MISSIONMANAGER_AUTH_BACKEND` | `local` o `oidc` |
| `MISSIONMANAGER_LOCAL_TOKEN_TTL` | Durata in secondi dei JWT locali |
| `MISSIONMANAGER_OIDC_CLIENT_ID` | Client ID OIDC per Authorization Code + PKCE |
| `MISSIONMANAGER_OIDC_CLIENT_SECRET` | Client secret OIDC opzionale |
| `MISSIONMANAGER_OIDC_REDIRECT_URI` | Redirect URI OIDC |
| `MISSIONMANAGER_SECRET_KEY` | Chiave segreta per JWT locali e sessioni Web; richiesta da auth locale e Web App |
| `MISSIONMANAGER_OPERATOR_ID` | UUID dell'operatore per la CLI |
| `MISSIONMANAGER_CLI_IDENTITY_MODE` | `anonymous` o `user` |
| `MISSIONMANAGER_ACL_READ_THRESHOLD` | Soglia di bootstrap per le entry di lettura (default 100) |
| `MISSIONMANAGER_ACL_WRITE_THRESHOLD` | Soglia di bootstrap per le mutazioni operative (default 50) |
| `MISSIONMANAGER_ACL_ADMIN_THRESHOLD` | Soglia di bootstrap per identità/profili/MANAGE_ACL (default 0) |
| `MISSIONMANAGER_ACL_SEEDING_ENABLED` | Seeding automatico del creatore (default `true`) |
| `MISSIONMANAGER_PLUGINS_SCAN_PATHS` | Path plugin separati da `:` |
| `MISSIONMANAGER_PLUGINS_TRUST_REGISTRY` | JSON dei trust level plugin |
| `MISSIONMANAGER_EXTENSIONS_SCAN_PATHS` | Path estensioni separati da `:` |
| `MISSIONMANAGER_EXTENSIONS_INSTALLED_REGISTRY` | JSON delle estensioni approvate e checksum |
| `MISSIONMANAGER_REST_DEV_MODE` | Modalità sviluppo REST: `1`/`true` disabilita auth (default: `false`) |
| `MISSIONMANAGER_WEB_THEME` | Tema Web App: `default` o `dark` |
| `MISSIONMANAGER_WEB_SECURE_COOKIES` | Cookie di sessione Web App `Secure` (HTTPS-only). Default `true`; impostare a `false` per dev locale su HTTP (vedi nota sotto) |
| `MISSIONMANAGER_REDIS_URL` | URL Redis opzionale per realtime WebSocket multi-worker |
| `MISSIONMANAGER_REDIS_PREFIX` | Prefisso chiavi/canali Redis (default: `missionmanager`) |

> Host, porta e SSL sono configurati sull'ASGI server esterno, non in questo file.

---

## 5. Quickstart — CLI

Nel layout sorgente attuale il package Python si trova in `implementation/src`, quindi dalla directory `implementation/` l'entrypoint è:

```bash
# Help generale
python -m src --help

# Con file di configurazione esplicito
python -m src --config /etc/missionmanager/config.yaml mission list

# Modalità "user": l'operatore è identificato da MISSIONMANAGER_OPERATOR_ID
export MISSIONMANAGER_OPERATOR_ID="<uuid-persona>"
python -m src mission list
```

Se il package viene installato o rinominato come `missionmanager`, sostituire `python -m src` con `python -m missionmanager`.
Il flag `--config` deve precedere il sottocomando.

### Primo avvio: amministratore iniziale

Al primo avvio il sistema non ha operatori abilitati (le entry di default vengono
seminate, ma nessuna persona esiste). Il comando `person create-superuser` crea
l'amministratore iniziale (ACL **livello 0**, il tier amministrativo: più basso = più
privilegiato) senza richiedere autenticazione, finché un amministratore non esiste già.
Il comportamento dipende dalla combinazione di backend configurata.

```bash
# persons=local, auth=local: crea l'utente locale finché il database è vuoto.
# persons=local, auth=oidc: il primo callback OIDC crea l'admin iniziale.
# persons=oidc, auth=oidc: crea l'utente nell'IdP con acl_level=0 e password
#                          via admin API, finché l'IdP non contiene già admin.
python -m src person create-superuser --nickname admin
# (la password viene chiesta in modo interattivo)
```

La Web App offre lo stesso flusso da browser: finché manca un amministratore, `/login`
redirige a `/setup`, che crea l'admin (in locale o delegando all'IdP in modalità OIDC).

### 5.1 Uso operativo per utenti

Gli utenti operativi usano normalmente la **Web App**:

1. Aprono l'URL pubblicato dal sistemista e accedono da `/login`; al primo avvio l'amministratore iniziale completa `/setup`.
2. Gli amministratori gestiscono persone, gruppi, profili ACL e regole ACL dalle sezioni **Persone**, **Gruppi** e **ACL**.
3. I gestori creano i blueprint da **Missioni**, definendo obiettivi e attività al momento della creazione.
4. I gestori creano le **Assegnazioni** a persone o gruppi e ne seguono l'avanzamento.
5. Gli operatori aggiornano lo stato delle attività assegnate; il sistema propaga automaticamente lo stato dell'assegnazione quando necessario.
6. I badge vengono creati nella sezione **Badge** e assegnati a missioni o attività completate; i premi sono poi visibili sulle persone coinvolte.

Per automazioni e integrazioni, gli utenti tecnici possono usare la **REST API**:
prima effettuano il login locale su `/api/auth/login` o completano il flusso OIDC,
poi inviano il token con `Authorization: Bearer <token>` agli endpoint operativi.
La **CLI** espone gli stessi casi d'uso per script amministrativi e attività
manuali da terminale; il flag globale `--config` deve precedere il sottocomando.

### Gestione persone e gruppi (ruolo Amministratore)

```bash
# Crea una persona (nasce con il profilo ACL meno privilegiato)
python -m src person add \
  --nickname "Alpha" --nickname "Alpha-2"

# Assegna il profilo ACL (operazione riservata MANAGE_PROFILES)
python -m src person set-acl <person-uuid> \
  --acl-level 50 --acl-group commanders

# Lista tutte le persone / dettaglio di una persona
python -m src person list
python -m src person get <person-uuid>

# Aggiorna i nickname di una persona
python -m src person update <person-uuid> \
  --nickname "Bravo II"

# Rimuove una persona
python -m src person remove <person-uuid>

# Crea / aggiorna / rimuove un gruppo
python -m src person group-add
python -m src person group-update <group-uuid> --name "Alfa"
python -m src person group-remove <group-uuid>

# Lista gruppi e membri
python -m src person group-list
python -m src person group-members <group-uuid>

# Aggiunge / rimuove un membro di un gruppo (MANAGE_MEMBERS sul gruppo)
python -m src person group-member-add <group-uuid> <person-uuid>
python -m src person group-member-remove <group-uuid> <person-uuid>
```

### Regole ACL (entry)

Le regole di autorizzazione sono `AclEntry` amministrabili anche da CLI
(l'autorizzazione è il `MANAGE_ACL` di `AclService`: sulla risorsa per i
delegati dal seeding, su `SYSTEM:global` per il tier amministrativo).

```bash
# Elenca tutte le entry (incluse le soglie di default del bootstrap)
python -m src acl list

# Consenti al gruppo "viewers" di vedere l'intero albero operativo
python -m src acl add --resource-type MISSION --resource-id "*" \
  --operation VIEW --permission ALLOW --group viewers

# Nega il cambio di stato a chi ha livello >= 60 su una specifica assegnazione
python -m src acl add --resource-type ASSIGNMENT --resource-id <uuid> \
  --operation UPDATE_STATUS --permission DENY --level 2147483647 --group sospesi

# Rimuovi una entry
python -m src acl remove <entry-uuid>
```

### Missioni (ruolo Gestore Missioni)

```bash
# Crea un blueprint di missione con obiettivi e attività
python -m src mission create \
  --title "Operazione Alba" \
  --desc "Operazione di ricognizione e estrazione" \
  --objectives '[{"description":"Ricognizione","activities":[{"title":"Pattuglia Nord","description":""},{"title":"Pattuglia Sud","description":""}]},{"description":"Estrazione","activities":[{"title":"Trasporto unità","description":""}]}]'

# Lista blueprint disponibili
python -m src mission list

# Dettaglio di un blueprint
python -m src mission get <mission-uuid>

# Il blueprint è immutabile dopo la creazione: obiettivi e attività si definiscono
# solo con `mission create`, non esiste un comando per aggiungerli o modificarli.

# Elimina un blueprint
python -m src mission delete <mission-uuid>
```

### Assegnazioni

```bash
# Assegna la missione a una persona (nasce in stato ASSIGNED)
python -m src assignment create \
  --mission-id <mission-uuid> \
  --assignee-type PERSON \
  --assignee-id <person-uuid>

# Assegna la missione a un gruppo (nasce in stato ASSIGNED)
python -m src assignment create \
  --mission-id <mission-uuid> \
  --assignee-type GROUP \
  --assignee-id <group-uuid>

# Crea un'assegnazione senza assegnatario (nasce in stato UNASSIGNED)
python -m src assignment create \
  --mission-id <mission-uuid>

# Imposta l'assegnatario su un'assegnazione UNASSIGNED
python -m src assignment assign <assignment-uuid> \
  --type PERSON \
  --id <person-uuid>

# Aggiorna lo stato di un'assegnazione
python -m src assignment status <assignment-uuid> IN_PROGRESS
python -m src assignment status <assignment-uuid> COMPLETED

# Dettaglio di un'assegnazione (con obiettivi, attività e badge)
python -m src assignment get <assignment-uuid>
```

### Attività

```bash
# Assegna un'attività a una persona (deve essere membro del gruppo o la persona diretta)
python -m src activity assign <activity-uuid> \
  --person-id <person-uuid>

# Rimuove un assegnatario da un'attività
python -m src activity unassign <activity-uuid> \
  --person-id <person-uuid>

# Aggiorna lo stato di un'attività
python -m src activity status <activity-uuid> IN_PROGRESS
python -m src activity status <activity-uuid> COMPLETED

# Dettaglio attività
python -m src activity get <activity-uuid>
```

### Badge

```bash
# Crea una definizione di badge
python -m src badge create \
  --name "Veterano" \
  --desc "Completamento con esito positivo" \
  --image-url "https://example.com/badge.png"

# Lista badge disponibili
python -m src badge list

# Assegna un badge a un'assegnazione completata
# (propagato automaticamente agli assegnatari)
python -m src badge award-assignment \
  --assignment-id <assignment-uuid> \
  --badge-id <badge-uuid>

# Assegna un badge a un'attività completata
python -m src badge award-activity \
  --activity-id <activity-uuid> \
  --badge-id <badge-uuid>
```

---

## 6. Deployment — Web App

La Web App può essere usata in **due modalità**:

- **Standalone** (sotto, *Avvio dell'ASGI server* + *Configurazione nginx*): app Quart
  preconfigurata, esposta come **callable ASGI** in `src.asgi:web_app` e servita da un ASGI server
  esterno. È il caso d'uso tipico.
- **Come Blueprint** (in fondo, *Uso come Blueprint in un'altra applicazione Quart*): la stessa Web
  App montata su un'**altra applicazione Quart**, per affiancarla a route proprie. Internamente la
  modalità standalone non è che questo blueprint registrato su un'app Quart minimale.

Entrambe partono dalla stessa factory `create_web_blueprint()`; `create_web_app()` è il wrapper
standalone che vi aggiunge l'app Quart e la `secret_key`.

La Web App, in **entrambe** le modalità, richiede `MISSIONMANAGER_SECRET_KEY` (in modalità blueprint
è l'host a doverla impostare su `app.secret_key`), perché usa sessioni Quart firmate.

### Stack di deployment

```
[Browser / Client WebSocket]
        │
        ▼
    [ nginx ]          ← reverse proxy (TLS, static files, WebSocket upgrade)
        │
        ▼
 [ ASGI server ]       ← Hypercorn o Uvicorn (processo separato)
        │
        ▼
 [ src.asgi:web_app ]  ← callable ASGI del progetto
```

### 1 — Avvio dell'ASGI server

`src.asgi:web_app` legge la configurazione tramite `MISSIONMANAGER_CONFIG_FILE` (o le singole variabili d'ambiente).

```bash
# Hypercorn (raccomandato per Quart — supporto HTTP/1.1, HTTP/2, WebSocket)
MISSIONMANAGER_SECRET_KEY="cambiare-questa-stringa-lunga-almeno-32-caratteri" \
hypercorn "src.asgi:web_app" \
  --bind 127.0.0.1:8000 \
  --workers 4

# Con file di configurazione esplicito
MISSIONMANAGER_CONFIG_FILE=/etc/missionmanager/config.yaml \
MISSIONMANAGER_SECRET_KEY="cambiare-questa-stringa-lunga-almeno-32-caratteri" \
hypercorn "src.asgi:web_app" \
  --bind 127.0.0.1:8000

# Uvicorn (alternativa)
MISSIONMANAGER_SECRET_KEY="cambiare-questa-stringa-lunga-almeno-32-caratteri" \
uvicorn "src.asgi:web_app" \
  --host 127.0.0.1 --port 8000 --workers 4
```

Se il package viene installato come `missionmanager`, usare `missionmanager.asgi:web_app` al posto di `src.asgi:web_app`.

> **Sviluppo locale su HTTP.** Di default il cookie di sessione è marcato `Secure`, quindi il browser lo invia solo su HTTPS. Servendo la Web App direttamente su `http://127.0.0.1:8000` (senza il reverse proxy TLS) il cookie viene scartato e il primo setup/login fallisce con `{"error":"Token CSRF mancante o non valido"}`. In dev locale avvia con il cookie `Secure` disattivato:
>
> ```bash
> MISSIONMANAGER_SECRET_KEY="cambiare-questa-stringa-lunga-almeno-32-caratteri" \
> MISSIONMANAGER_WEB_SECURE_COOKIES=false \
> hypercorn "src.asgi:web_app" --bind 127.0.0.1:8000
> ```
>
> In produzione la Web App va sempre dietro HTTPS (vedi nginx sotto): lascia `MISSIONMANAGER_WEB_SECURE_COOKIES=true` (default).

### 2 — Configurazione nginx

La Web App usa WebSocket per le notifiche realtime (`RealtimeNotifier`): nginx deve attivare il protocollo di upgrade.

```nginx
# /etc/nginx/conf.d/missionmanager-web.conf

upstream missionmanager_web {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl http2;
    server_name app.example.com;

    # TLS (Let's Encrypt o certificato interno)
    ssl_certificate     /etc/ssl/certs/app.example.com.crt;
    ssl_certificate_key /etc/ssl/private/app.example.com.key;

    # Traffico HTTP normale
    location / {
        proxy_pass         http://missionmanager_web;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

    # WebSocket (RealtimeNotifier — upgrade obbligatorio)
    location /ws {
        proxy_pass         http://missionmanager_web;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host       $host;
    }
}

# Redirect HTTP → HTTPS
server {
    listen 80;
    server_name app.example.com;
    return 301 https://$host$request_uri;
}
```

### 3 — Uso come Blueprint in un'altra applicazione Quart

`create_web_app()` è solo un wrapper: la Web App vera e propria è il `Blueprint` restituito da
`create_web_blueprint()`. Puoi quindi montarla su una **tua** applicazione Quart e affiancarla alle
tue route. L'host costruisce i servizi con `build_system()` e registra il blueprint:

```python
from quart import Quart

from src.config import RealtimeConfigLoader, SecurityConfigLoader, WebConfigLoader
from src.bootstrap.common import build_system
from src.infrastructure.identity.web import WebOperatorIdentityAdapter
from src.frontend.web.app import create_web_blueprint

# Ogni concern ha il suo loader (priorità env > file YAML/TOML > default).
security = SecurityConfigLoader.load()
web = WebConfigLoader.load()
realtime = RealtimeConfigLoader.load()
svcs = build_system()   # semina anche le entry ACL di default (database vuoto)

# L'app host: static_folder=None per non oscurare la route /static del blueprint.
app = Quart(__name__, static_folder=None)

# Obbligatoria: sessioni Quart firmate (CSRF + login).
if not security.secret_key:
    raise RuntimeError("MISSIONMANAGER_SECRET_KEY è obbligatoria per la Web App")
app.secret_key = security.secret_key
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = web.secure_cookies  # False in dev locale su HTTP

identity_provider = WebOperatorIdentityAdapter(person_repo=svcs.person_repo, uow=svcs.uow)

bp = create_web_blueprint(
    mission_svc=svcs.mission,
    assignment_svc=svcs.assignment,
    activity_svc=svcs.activity,
    person_svc=svcs.person,
    badge_svc=svcs.badge,
    acl_svc=svcs.acl,
    auth_policy=svcs.auth_policy,
    identity_provider=identity_provider,
    auth_service=svcs.auth_service,
    auth_backend=security.auth_backend,
    oidc_redirect_uri=security.oidc_redirect_uri,
    theme=web.theme,
    event_publisher=svcs.event_publisher,
    redis_url=realtime.redis_url,
    redis_prefix=realtime.redis_prefix,
    extension_registry=svcs.extension_registry,
)

# Le tue route possono convivere con quelle del blueprint.
@app.route("/health")
async def health():
    return {"status": "ok"}

app.register_blueprint(bp)          # ← montare ALLA RADICE (vedi vincoli sotto)

# bp.notifier  → RealtimeNotifier: bus WebSocket accessibile dall'host
```

`app` è una normale callable ASGI: si serve con Hypercorn/Uvicorn esattamente come `src.asgi:web_app`.

**Vincoli da rispettare** (la factory volutamente non configura l'app host):

- **`app.secret_key` obbligatoria.** Sessione e CSRF usano `quart.session`; senza secret key login e
  primo setup falliscono. La factory non la imposta — è compito dell'host (sopra).
- **Montare alla radice — niente `url_prefix`.** I percorsi pubblici del middleware (`/login`,
  `/auth/`, `/logout`, `/static/`, `/ws`, `/setup`) sono confrontati come **path assoluti**: con un
  prefisso (`register_blueprint(bp, url_prefix="/ui")`) lo skip dell'autenticazione non scatterebbe e
  login/static/setup verrebbero bloccati (redirect loop). Il prefisso **non è attualmente supportato**.
- **`static_folder=None` sull'app host.** Il blueprint serve i suoi asset su `/static`; senza questo,
  la route `/static` di default dell'app oscura quella del blueprint (404 su `app.js`/CSS).
- **Nomi dei template.** Il blueprint inietta `templates/default/` (e quelli del tema) nel
  `jinja_env` **globale** dell'app: evita di avere template host con gli stessi nomi
  (`layout.html`, `mission_detail.html`, …) o si hanno collisioni.
- **Amministrazione ACL.** Passa `acl_svc=svcs.acl` a `create_web_blueprint` per montare la
  pagina `/acl` (profili + entry); senza, l'enforcement del middleware resta attivo ma le entry
  si amministrano solo via REST/CLI. Le entry di default sono seminate da `build_system()`.
- **Lifecycle.** Il dispatcher realtime registra hook `before_serving`/`after_serving` e un
  background task **sull'app host**: ne erediti il ciclo di vita (atteso e corretto).
- **Sviluppo locale su HTTP.** Vale la stessa nota della modalità standalone: imposta
  `app.config["SESSION_COOKIE_SECURE"] = False` (qui via `cfg.web_secure_cookies`, da
  `MISSIONMANAGER_WEB_SECURE_COOKIES=false`) o il cookie di sessione viene scartato.

---

## 7. Deployment — REST API

La REST API è anch'essa esposta come **callable ASGI** in `src.asgi:rest_app`. Stessa architettura della Web App, senza WebSocket.

### Stack di deployment

```
[Client REST / curl / SDK]
        │
        ▼
    [ nginx ]          ← reverse proxy (TLS, rate limiting, CORS)
        │
        ▼
 [ ASGI server ]       ← Hypercorn o Uvicorn (processo separato)
        │
        ▼
 [ src.asgi:rest_app ] ← callable ASGI del progetto
```

### 1 — Avvio dell'ASGI server

```bash
# Hypercorn
hypercorn "src.asgi:rest_app" \
  --bind 127.0.0.1:8001 \
  --workers 4

# Con file di configurazione esplicito
MISSIONMANAGER_CONFIG_FILE=/etc/missionmanager/config.yaml \
hypercorn "src.asgi:rest_app" \
  --bind 127.0.0.1:8001

# Uvicorn
uvicorn "src.asgi:rest_app" \
  --host 127.0.0.1 --port 8001 --workers 4
```

Se il package viene installato come `missionmanager`, usare `missionmanager.asgi:rest_app` al posto di `src.asgi:rest_app`.

### 2 — Configurazione nginx

```nginx
# /etc/nginx/conf.d/missionmanager-rest.conf

upstream missionmanager_rest {
    server 127.0.0.1:8001;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate     /etc/ssl/certs/api.example.com.crt;
    ssl_certificate_key /etc/ssl/private/api.example.com.key;

    location / {
        proxy_pass         http://missionmanager_rest;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }
}

server {
    listen 80;
    server_name api.example.com;
    return 301 https://$host$request_uri;
}
```

**Autenticazione e ACL**: le richieste portano le credenziali dell'operatore tramite Bearer token locale o OIDC. `AuthMiddleware` identifica l'operatore (assente → profilo anonimo implicito), mappa la richiesta su `(Operation, ResourceRef)` e interroga `AuthorizationPolicy.is_allowed` sulle `AclEntry` (DENY > ALLOW > default-deny, ereditarietà gerarchica — [DESIGN §10](design/DESIGN.md#10-sistema-acl-e-autorizzazione)). Esito DENIED: HTTP 401 con `WWW-Authenticate` per l'anonimo, HTTP 403 per l'autenticato (eventuali entry PUBLIC di sola lettura possono concedere accessi anonimi). Gli endpoint `/api/auth/*` sono pubblici per login/logout e flussi OIDC.

**Mappatura errori di dominio:**

| Eccezione | HTTP |
|-----------|------|
| `ValidationError` | 400 |
| `NotFoundError` | 404 |
| `ACLError` | 403 |
| `StatusTransitionError` | 409 |
| `OperationAbortedError` | 422 |

### Endpoint principali

#### Autenticazione

```bash
# Login locale: restituisce un token JWT locale
POST /api/auth/login
{ "username": "<nickname>", "password": "<password>" }

# Logout locale: revoca il token presentato nell'header Authorization
POST /api/auth/logout

# Imposta o aggiorna password locale (richiede operatore autenticato).
# Self-service: ognuno può cambiare la PROPRIA password; cambiare quella di un
# altro operatore richiede EDIT sulla sua risorsa PERSON (di default, il tier
# amministrativo delle entry di bootstrap).
PUT /api/auth/password
{ "person_id": "<person-uuid>", "password": "<password>" }

# Flusso OIDC stateless per client REST/SPA
GET  /api/auth/oidc/url?redirect_uri=<callback-url>
POST /api/auth/oidc/callback
{ "code": "...", "state": "...", "nonce": "...", "code_verifier": "...", "redirect_uri": "..." }
```

#### Blueprint missioni

```bash
# Lista blueprint
GET /api/missions

# Crea blueprint
POST /api/missions
{
  "title": "Operazione Alba",
  "description": "Operazione di ricognizione",
  "objectives": [
    {
      "description": "Ricognizione",
      "activities": [
        { "title": "Pattuglia Nord", "description": "" },
        { "title": "Pattuglia Sud",  "description": "" }
      ]
    },
    {
      "description": "Estrazione",
      "activities": [
        { "title": "Trasporto unità", "description": "" }
      ]
    }
  ]
}

# Dettaglio / elimina blueprint
GET    /api/missions/<uuid>
DELETE /api/missions/<uuid>

# Obiettivi del blueprint (sola lettura: il blueprint è immutabile dopo la creazione)
GET  /api/missions/<uuid>/objectives
```

#### Assegnazioni

```bash
# Lista assegnazioni di una missione (filtro opzionale sullo stato)
GET /api/missions/<mission-uuid>/assignments
GET /api/missions/<mission-uuid>/assignments?status=IN_PROGRESS

# Crea assegnazione (con assegnatario → nasce ASSIGNED)
POST /api/missions/<mission-uuid>/assignments
{ "assignee_type": "PERSON", "assignee_id": "<person-uuid>" }

# Crea assegnazione (senza assegnatario → nasce UNASSIGNED)
POST /api/missions/<mission-uuid>/assignments
{}

# Dettaglio assegnazione
GET /api/assignments/<uuid>

# Obiettivi di un'assegnazione (con attività)
GET /api/assignments/<uuid>/objectives

# Imposta assegnatario su assegnazione UNASSIGNED
POST /api/assignments/<uuid>/assign
{ "assignee_type": "GROUP", "assignee_id": "<group-uuid>" }

# Aggiorna stato assegnazione
PUT /api/assignments/<uuid>/status
{ "status": "IN_PROGRESS" }

# Crea BadgeAward per assegnazione completata
POST /api/assignments/<uuid>/badge
{ "badge_id": "<badge-uuid>" }
```

#### Attività

```bash
# Dettaglio attività
GET /api/activities/<uuid>

# Assegna attività a una persona
POST /api/activities/<uuid>/assign
{ "person_id": "<person-uuid>" }

# Rimuove un assegnatario da un'attività
DELETE /api/activities/<uuid>/assign
{ "person_id": "<person-uuid>" }

# Aggiorna stato attività
PUT /api/activities/<uuid>/status
{ "status": "IN_PROGRESS" }

# Crea BadgeAward per attività completata
POST /api/activities/<uuid>/badge
{ "badge_id": "<badge-uuid>" }

# Attività di un obiettivo
GET /api/objectives/<uuid>/activities
```

#### Badge

```bash
# Lista / Crea badge
GET  /api/badges
POST /api/badges
{ "name": "Veterano", "description": "Completamento con esito positivo", "image_url": null }

# Dettaglio badge
GET /api/badges/<uuid>
```

#### Persone e gruppi

```bash
# Lista / Crea persone (la persona nasce con il profilo ACL meno privilegiato)
GET  /api/persons
POST /api/persons
{ "nicknames": ["Alpha", "α"] }

# Dettaglio / Aggiorna / Elimina persona
GET    /api/persons/<uuid>
PUT    /api/persons/<uuid>
{ "nicknames": ["Alpha II"] }
DELETE /api/persons/<uuid>

# Assegna il profilo ACL (MANAGE_PROFILES su SYSTEM:global)
PUT /api/persons/<uuid>/acl
{ "acl_level": 50, "acl_groups": ["commanders"] }

# Lista / Crea gruppi
GET  /api/groups
POST /api/groups

# Dettaglio / Aggiorna / Elimina gruppo
GET    /api/groups/<uuid>
PUT    /api/groups/<uuid>
{ "name": "Alfa", "zone_type": "GEOGRAPHIC", "zone_description": "Settore nord" }
DELETE /api/groups/<uuid>

# Membri di un gruppo
GET /api/groups/<uuid>/members
POST /api/groups/<uuid>/members
{ "person_id": "<person-uuid>" }
DELETE /api/groups/<uuid>/members
{ "person_id": "<person-uuid>" }

# Badge ricevuti da una persona
GET /api/persons/<uuid>/badges
```

#### Sistema ACL (entry)

La gestione delle `AclEntry` è autoprotetta da `MANAGE_ACL` (sulla risorsa per i
delegati dal seeding, su `SYSTEM:global` per il tier amministrativo).

```bash
# Lista le entry (tutte, o quelle di una risorsa)
GET /api/acl/entries
GET /api/acl/entries?resource_type=MISSION&resource_id=<uuid|*|global>

# Crea una entry (almeno uno tra level e group — INV-1)
POST /api/acl/entries
{ "resource_type": "MISSION", "resource_id": "*",
  "operation": "VIEW", "permission": "ALLOW",
  "group": "viewers" }

# Aggiorna / elimina una entry
PATCH  /api/acl/entries/<uuid>
{ "permission": "DENY" }
DELETE /api/acl/entries/<uuid>
```

---

## 8. Sistema di Plugin

I plugin intercettano **tutte le operazioni mutanti** dei service di dominio (missioni, assignment, attività, badge, persone, gruppi) con hook BEFORE_*/AFTER_*. I plugin `BEFORE_*` possono porre il veto sull'operazione impostando `ctx.abort = True`; i plugin `AFTER_*` ricevono il risultato già persistito e le loro eccezioni vengono catturate senza interrompere il flusso. I sottosistemi di sicurezza (ACL, autenticazione, gestione profili) non espongono hook per progetto (anti-escalation).

```
HookPoint disponibili:
  BEFORE_CREATE_MISSION    / AFTER_CREATE_MISSION
  BEFORE_CREATE_ASSIGNMENT / AFTER_CREATE_ASSIGNMENT
  BEFORE_UPDATE_STATUS     / AFTER_UPDATE_STATUS      payload: entity_type ASSIGNMENT|ACTIVITY
  BEFORE_AWARD_BADGE       / AFTER_AWARD_BADGE
  BEFORE_ASSIGN            / AFTER_ASSIGN             payload: entity_type ASSIGNMENT|ACTIVITY,
                                                      action ASSIGN|UNASSIGN
  BEFORE_DELETE            / AFTER_DELETE             payload: entity_type MISSION|ASSIGNMENT|
                                                      PERSON|GROUP
  BEFORE_CREATE_BADGE      / AFTER_CREATE_BADGE
  BEFORE_CREATE_PERSON     / AFTER_CREATE_PERSON
  BEFORE_UPDATE_PERSON     / AFTER_UPDATE_PERSON
  BEFORE_CREATE_GROUP      / AFTER_CREATE_GROUP
  BEFORE_UPDATE_GROUP      / AFTER_UPDATE_GROUP
  BEFORE_MANAGE_MEMBERS    / AFTER_MANAGE_MEMBERS     payload: group_id, person_id, action ADD|REMOVE
```

Un plugin è qualsiasi oggetto Python che soddisfa il protocollo `MissionHook` (duck typing):

```python
from src.domain.plugins import HookContext, HookPoint, PluginManifest, PluginTrustLevel

class ExternalSyncHook:
    @property
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            id="external-sync",
            name="External Sync",
            version="1.0",
            description="Sincronizza aggiornamenti verso sistemi esterni",
            hooks=[HookPoint.AFTER_UPDATE_STATUS, HookPoint.AFTER_AWARD_BADGE],
            trust_level=PluginTrustLevel.TRUSTED,  # default: SANDBOXED
            priority=10,                            # default: 0; più alto = eseguito prima
        )

    def execute(self, context: HookContext) -> None:
        # propagare lo stato aggiornato a sistemi operativi esterni
        ...
```

Un plugin installabile è un bundle `<plugin_id>/manifest.json + plugin.py` in cui `plugin.py` espone una classe `Plugin`. I plugin vengono caricati dai path in `plugins.scan_paths` (`MISSIONMANAGER_PLUGINS_SCAN_PATHS`) **solo se approvati** nel trust registry JSON (`plugins.trust_registry_path` / `MISSIONMANAGER_PLUGINS_TRUST_REGISTRY`), autoritativo per trust level e checksum SHA-256 di manifest e codice:

```json
{
  "external-sync": {
    "trust_level": "TRUSTED",
    "manifest_checksum": "sha256:…",
    "code_checksum": "sha256:…"
  }
}
```

Esempi funzionanti in `implementation/src/infrastructure/plugins/examples/` (con relativo `trusted_plugins.json`).

---

## 9. Sistema di Estensioni

Le estensioni aggiungono **nuove operazioni** al sistema, visibili come nuovi endpoint REST, route Web App o comandi CLI. Si differenziano dai plugin perché non si agganciano a operazioni esistenti ma introducono funzionalità proprie.

Un'estensione installabile è un bundle `<ext_id>/manifest.json + extension.py` in cui `extension.py` espone una classe `Extension`. Le route dichiarate devono vivere nel namespace `/extensions/<ext_id>/…` e usano la sintassi dei path Quart (`<param>`); i nomi dei comandi CLI non possono collidere con i comandi core né con quelli di altre estensioni:

```json
{
  "id": "report",
  "name": "Report",
  "version": "1.0.0",
  "description": "Genera report operativi per missione",
  "code_checksum": "sha256:…",
  "provides_routes": [
    {"path": "/extensions/report/missions/<mission_id>/report", "method": "GET",
     "description": "Report missione"}
  ],
  "provides_commands": [
    {"name": "report", "description": "Genera report operativo"}
  ]
}
```

```python
# extension.py
from src.domain.extensions import ExtensionRequest, ExtensionResult

class Extension:
    def __init__(self, manifest=None, assignment_svc=None, badge_svc=None, **_):
        self.manifest = manifest
        self._assignment_svc = assignment_svc
        self._badge_svc = badge_svc

    def execute(self, request: ExtensionRequest) -> ExtensionResult:
        # request.params contiene query string, body JSON e parametri di path;
        # request.operator_id è l'operatore autenticato (None se anonimo).
        report_data = ...
        return ExtensionResult(data=report_data, status_code=200)
```

Le estensioni vengono scoperte da `extensions.scan_paths` (`MISSIONMANAGER_EXTENSIONS_SCAN_PATHS`) e caricate da `ExtensionLoader` **solo se approvate** nel registro JSON degli installati (`extensions.installed_registry_path` / `MISSIONMANAGER_EXTENSIONS_INSTALLED_REGISTRY`, stesso formato a checksum del trust registry dei plugin, senza `trust_level`). Il loader inietta automaticamente nel costruttore i service richiesti per nome: `mission_svc`, `assignment_svc`, `activity_svc`, `badge_svc`, `person_svc`, `acl_svc`, `event_publisher`. I frontend leggono i manifest al bootstrap e registrano dinamicamente route e comandi dichiarati.

Le route REST sono esposte sotto `/api` (es. `/api/extensions/report/…`) e quelle Web alla radice; l'ACL le governa con le entry di ambito sistema: `VIEW` su `SYSTEM:global` per le letture, `EXECUTE` su `SYSTEM:global` per le mutazioni e per i comandi CLI. Esempi funzionanti in `implementation/src/infrastructure/extensions/examples/` (con relativo `installed_extensions.json`).

---

## 10. Documentazione di riferimento

| Documento | Contenuto |
|-----------|-----------|
| [design/DESIGN.md](design/DESIGN.md) | Architettura completa: modello del dominio, regole di business, layer, ACL, flussi operativi, plugin, estensioni |
| [implementation/IMPLEMENTATION.md](implementation/IMPLEMENTATION.md) | Scelte implementative: struttura Python, adapter SQLAlchemy/OIDC, bootstrap, configurazione, diagrammi di classe e sequenza |
| [implementation/diagrams/](implementation/diagrams/) | Diagrammi PlantUML (classi, sequenza, attività) dell'implementazione |
| [design/diagrams/](design/diagrams/) | Diagrammi PlantUML dell'architettura (overview, use case, dominio) |

---

## 11. Licenza

MissionManager è distribuito con licenza **Creative Commons
Attribution-ShareAlike 4.0 International** (`CC-BY-SA-4.0`). Il file canonico è
[LICENSE.md](LICENSE.md); ogni file del repository contiene un riferimento alla
licenza nel formato più adatto al tipo di file.
