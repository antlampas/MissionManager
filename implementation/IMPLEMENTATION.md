<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

# MissionManager — Guida all'Implementazione

Questo documento descrive le scelte implementative del sistema, a partire dall'architettura
a cinque layer definita in `../design/DESIGN.md`. Presuppone quella lettura: il modello del
dominio, le regole di business, i contratti del Layer 2 e i flussi operativi chiave sono
documentati lì e non vengono ripetuti qui se non per chiarire una scelta implementativa.

## Indice

1. [Struttura dell'implementazione](#1-struttura-dellimplementazione)
2. [Implementazioni](#2-implementazioni)
   - 2.1 [Layer 1 — Domain (nucleo)](#21-layer-1--domain-nucleo)
     - 2.1.1 [Entità di dominio](#211-entità-di-dominio)
     - 2.1.2 [Value Objects](#212-value-objects)
     - 2.1.3 [Status — enum comportamentale](#213-status--enum-comportamentale)
     - 2.1.4 [Entità di dominio — Person, Group, Zone](#214-entità-di-dominio--person-group-zone)
     - 2.1.5 [Eccezioni di dominio](#215-eccezioni-di-dominio)
   - 2.2 [Layer 2 — Ports (contratti)](#22-layer-2--ports-contratti)
     - 2.2.1 [Repository interfaces](#221-repository-interfaces)
     - 2.2.2 [PersonRepository e GroupRepository](#222-personrepository-e-grouprepository)
     - 2.2.3 [OperatorIdentityProvider](#223-operatoridentityprovider)
     - 2.2.4 [MissionHook e tipi correlati](#224-missionhook-e-tipi-correlati)
     - 2.2.5 [MissionExtension e tipi correlati](#225-missionextension-e-tipi-correlati)
     - 2.2.6 [CredentialRepository e LocalCredential](#226-credentialrepository-e-localcredential)
   - 2.3 [Layer 3 — Adapters (astratti)](#23-layer-3--adapters-astratti)
     - 2.3.1 [Ruolo e collocazione](#231-ruolo-e-collocazione)
     - 2.3.2 [RepositoryAdapter](#232-repositoryadapter)
     - 2.3.3 [PersonRepositoryAdapter e GroupRepositoryAdapter](#233-personrepositoryadapter-e-grouprepositoryadapter)
     - 2.3.4 [OperatorIdentityAdapter](#234-operatoridentityadapter)
     - 2.3.5 [MissionHookAdapter](#235-missionhookadapter)
   - 2.4 [Layer 4 — Services](#24-layer-4--services)
     - 2.4.1 [Pattern generale di esecuzione](#241-pattern-generale-di-esecuzione)
     - 2.4.2 [Sistema ACL: AuthorizationPolicy e AclService](#242-sistema-acl-authorizationpolicy-e-aclservice)
     - 2.4.3 [MissionService](#243-missionservice)
     - 2.4.4 [AssignmentService — verifica AssignmentPolicy](#244-assignmentservice--verifica-assignmentpolicy)
     - 2.4.5 [AssignmentService — replicazione del blueprint](#245-assignmentservice--replicazione-del-blueprint)
     - 2.4.6 [AssignmentService — assign()](#246-assignmentservice--assign)
     - 2.4.7 [ActivityService — auto-cascade dello stato](#247-activityservice--auto-cascade-dello-stato)
     - 2.4.8 [BadgeService — propagazione badge](#248-badgeservice--propagazione-badge)
     - 2.4.9 [DTO — contratto verso i Frontend](#249-dto--contratto-verso-i-frontend)
     - 2.4.10 [PersonService](#2410-personservice)
     - 2.4.11 [PluginRegistry](#2411-pluginregistry)
     - 2.4.12 [ExtensionRegistry](#2412-extensionregistry)
     - 2.4.13 [ExtensionLoader](#2413-extensionloader)
     - 2.4.14 [Bootstrap completo](#2414-bootstrap-completo)
     - 2.4.15 [Autenticazione locale: LocalAuthAdapter](#2415-autenticazione-locale-localauthadapter)
   - 2.5 [Layer 5 — Frontends](#25-layer-5--frontends)
     - 2.5.1 [REST API (Quart)](#251-rest-api-quart)
     - 2.5.2 [Web App asincrona (Quart)](#252-web-app-asincrona-quart)
     - 2.5.3 [Web App come Blueprint riusabile](#253-web-app-come-blueprint-riusabile)
     - 2.5.4 [CLI (Click)](#254-cli-click)
3. [Configurazione](#3-configurazione)
4. [Diagrammi di riferimento](#4-diagrammi-di-riferimento)

---

## 1. Struttura dell'implementazione

```
implementation/
  IMPLEMENTATION.md                  ← questo documento
  src/
    domain/
      entities.py                    ← Mission, MissionAssignment, Objective, Activity,
                                        Badge, BadgeAward, Person, Group, Zone
      value_objects.py               ← AssignmentPolicy (con factory methods)
      acl.py                         ← nucleo ACL: AclEntry (INV-1..5, matches), Profile,
                                        SubjectRef, ResourceRef, Operation, Permission,
                                        JoinOp, ANON_SENTINEL, PUBLIC_GROUP, SYSTEM_RESOURCE
      enums.py                       ← Status (comportamentale), AssigneeType, ZoneType,
                                        ResourceType (incl. SYSTEM)
      exceptions.py                  ← re-export da shared/errors.py per compatibilità
      events.py                      ← DomainEvent e sottoclassi (MissionCreated,
                                        MissionDeleted, AssignmentCreated,
                                        AssignmentStatusChanged, ActivityAssigned,
                                        ActivityStatusChanged, BadgeAwarded),
                                        EventPublisherPort (Protocol)
      auth.py                        ← CredentialRepository (Protocol)
      policies.py                    ← AssignmentStatusPolicy, BadgeAwardPolicy,
                                        ActivityAssignmentPolicy (policy objects di dominio)
      repositories.py                ← BaseRepository[T], MissionRepository,
                                        MissionAssignmentRepository, ObjectiveRepository,
                                        ActivityRepository, BadgeRepository, BadgeAwardRepository,
                                        PersonRepository, GroupRepository, AclEntryRepository,
                                        ProfileProvider, ResourceHierarchyProvider
      identity.py                    ← OperatorIdentityProvider
      plugins.py                     ← MissionHook, HookContext, PluginManifest, HookPoint,
                                        PluginTrustLevel
      extensions.py                  ← MissionExtension, ExtensionManifest, RouteSpec,
                                        CommandSpec, ExtensionRequest, ExtensionResult
    shared/
      errors.py                      ← MissionManagerError, ValidationError, NotFoundError,
                                        ACLError, StatusTransitionError, OperationAbortedError,
                                        ForbiddenError, AuthorizationError, AuthenticationError,
                                        RateLimitExceededError, ExtensionLoadError,
                                        ExtensionConflictError
      types.py                       ← tipi condivisi trasversali
      utils.py                       ← utility trasversali
    infrastructure/
      base.py                        ← RepositoryAdapter[T] (abstract base)
      person_repository.py           ← PersonRepositoryAdapter (abstract)
      group_repository.py            ← GroupRepositoryAdapter (abstract)
      identity/base.py               ← OperatorIdentityAdapter (abstract)
      identity/cli.py                ← identità CLI
      identity/rest.py               ← identità REST Bearer token locale/OIDC
      identity/web.py                ← identità Web da sessione Quart
      hook.py                        ← MissionHookAdapter (abstract)
      acl.py                         ← PersonProfileProvider e
                                        MissionResourceHierarchyProvider (adapter ACL)
      event_publisher.py             ← transactional outbox e dispatcher consumer
      repositories/                  ← repository SQLAlchemy, mapper ORM, session.py,
                                        acl_entry_repository.py (mm_acl_entries),
                                        external_identity_repository.py e modelli outbox
      oidc/                          ← repository Person/Group via Authentik/Keycloak
      auth/                          ← adapter MissionManager verso il package `auth`
                                        + OidcAuthClient HTTP/OIDC
      plugins/                       ← PluginLoader e PluginTrustRegistry
      extensions/                    ← ExtensionLoader e InstalledManifestRegistry
      security/                      ← AuditLogger e RateLimitPolicy
    application/
      services/
        mission_service.py           ← MissionService
        assignment_service.py        ← AssignmentService
        activity_service.py          ← ActivityService
        badge_service.py             ← BadgeService
        person_service.py            ← PersonService
        acl_service.py               ← adapter verso `acl.application.ACLService`
                                        + SeedingPolicy MissionManager
        auth_service.py              ← AuthService
        dto.py                       ← MissionDTO, AssignmentDTO, ObjectiveDTO,
                                        ActivityDTO, BadgeDTO, BadgeAwardDTO,
                                        PersonDTO, GroupDTO, AclEntryDTO
      plugin_registry.py             ← PluginRegistry
      extension_registry.py          ← ExtensionRegistry
      auth_acl.py                    ← modello ACL registrabile in `auth`
      authorization.py               ← facciata AuthorizationPolicy verso
                                        `auth.application.AuthorizationService`
    frontend/
      _http.py                       ← helper HTTP condivisi (operator_id, parse_json_body)
      _utils.py                      ← validazione condivisa dei frontend (require_field)
      api/
        app.py                       ← RestApp (Quart bootstrap)
        middleware.py                ← AuthMiddleware
        error_handler.py             ← ErrorHandler
        routers/
          missions.py                ← MissionRouter, MissionObjectiveRouter
          assignments.py             ← AssignmentRouter, AssignmentBadgeRouter
          objectives.py              ← ObjectiveRouter
          activities.py              ← ActivityRouter, ObjectiveActivitiesRouter
          badges.py                  ← BadgeRouter, PersonBadgesRouter
          persons.py                 ← PersonRouter, GroupRouter, GroupMembersRouter
          acl.py                     ← AclEntriesRouter, AclEntryRouter, PersonAclRouter
          auth.py                    ← register_auth_routes (login/logout locale e OIDC)
      web/
        app.py                       ← create_web_blueprint (factory del blueprint Web)
        middleware.py                ← ACLMiddleware
        notifier.py                  ← RealtimeNotifier
        handlers/
          missions.py                ← MissionRouteHandler
          assignments.py             ← AssignmentRouteHandler
          objectives.py              ← ObjectiveRouteHandler
          activities.py              ← ActivityRouteHandler
          acl.py                     ← AclRouteHandler (pagina /acl: profili + entry)
          auth.py                    ← login/setup primo avvio/logout locale, callback OIDC
      cli/
        app.py                       ← CLIApp (Click bootstrap)
        formatter.py                 ← OutputFormatter
        commands/
          missions.py                ← MissionCommands
          assignments.py             ← AssignmentCommands
          activities.py              ← ActivityCommands
          badges.py                  ← BadgeCommands
          persons.py                 ← PersonCommands (incl. person set-acl)
          acl.py                     ← AclCommands (acl list/add/remove)
    bootstrap/
      common.py                      ← composition root condiviso
      cli.py                         ← create_cli_app()
      rest.py                        ← create_rest_app()
      web.py                         ← create_web_app()
    config.py                        ← loader modulari per concern (*ConfigLoader)
    asgi.py                          ← resolver lazy di rest_app/web_app: non inizializza
                                       l'altra applicazione
                                       (asgi_rest.py / asgi_web.py: una sola app ciascuno)
    __main__.py                      ← entrypoint CLI del package
    test/                            ← suite pytest (conftest.py + test_*.py)
```

La struttura segue il modello a cinque layer dell'architettura:

- `domain/` è il nucleo invariante: entità, value objects, enum, eccezioni (re-export da
  `shared/`), domain events (`events.py`), policy objects (`policies.py`), contratto
  `CredentialRepository` (`auth.py`) e contratti astratti del Layer 2 (`repositories.py`,
  `identity.py`, `plugins.py`, `extensions.py`) sotto forma di `Protocol` o ABC.
  Non importa da nessun altro layer applicativo.
- `shared/` è un layer trasversale che definisce la gerarchia completa delle eccezioni
  (`errors.py`), i tipi condivisi (`types.py`) e le utility generiche (`utils.py`).
  `domain/exceptions.py` ri-esporta da `shared/errors.py` per compatibilità con i layer
  superiori che importano da `domain`.
- `infrastructure/` contiene gli adapter concreti o astratti del Layer 3: repository
  SQLAlchemy, backend OIDC, identità per i frontend, autenticazione, loader plugin,
  loader estensioni, audit e rate limit.
- `application/` ospita tutta la logica applicativa: service (incluso `AclService`),
  registry di coordinamento, la decisione ACL pura (`AuthorizationPolicy`) e i DTO.
- `frontend/` contiene le tre implementazioni di interfaccia utente: Quart per la REST API
  JSON asincrona (route sotto `/api`), Quart per la Web App asincrona con notifiche realtime
  (route dalla root), Click per la CLI. Gli helper condivisi tra i due frontend Quart
  (`_http.py`: lettura dell'operatore e parsing del body JSON) e la validazione comune
  (`_utils.py`: `require_field`) evitano duplicazione negli handler/router.

---

## 2. Implementazioni

### 2.1 Layer 1 — Domain (nucleo)

Il Layer 1 è completamente **indipendente da framework, database e layer infrastrutturali**.
Tutti gli altri layer dipendono dai contratti definiti qui; il Domain non dipende da nulla.

Scelte implementative Python:

- **Entità** come `@dataclass` mutabili: hanno identità (campo `id`) e il loro stato può
  essere modificato dai service prima della persistenza.
- **Value objects** come `@dataclass(frozen=True)`: immutabili per costruzione. L'uguaglianza
  è strutturale (per valore), non per identità dell'oggetto.
- **`Status`** come enum comportamentale: espone `can_transition_to()` e `is_terminal()`,
  rendendo la macchina a stati auto-contenuta nel dominio.
- **Porte** come `typing.Protocol` con `@runtime_checkable` nel Layer 2: tipizzazione
  strutturale — qualunque classe che implementi i metodi richiesti soddisfa il contratto
  senza ereditarietà esplicita. Questo mantiene il dominio libero da catene ABC.

#### 2.1.1 Entità di dominio

Le entità sono `@dataclass` mutabili definite in `domain/entities.py`. Ognuna espone
`validate()` per verificare le invarianti di dominio prima della persistenza:

| Entità | File | Note implementative |
|---|---|---|
| `Mission` | `domain/entities.py` | Blueprint della missione; `validate()` verifica ≥1 obiettivo (e ≥1 attività valida per obiettivo via `Objective.validate()`). **Immutabile dopo la creazione**: obiettivi/attività si definiscono solo nel costruttore (`MissionService.create`); non esistono metodi per aggiungerli o modificarli a posteriori |
| `MissionAssignment` | `domain/entities.py` | `assignee_type` e `assignee_id` sono `None` finché `status == UNASSIGNED`; `update_status()` chiama `Status.can_transition_to()` prima di mutare; `award_badge()` verifica `status == COMPLETED` |
| `Objective` | `domain/entities.py` | `compute_outcome()` calcola l'esito da `Activity.status` delle attività figlie; `validate()` richiede ≥1 attività, verifica `activity.objective_id` e delega ad `Activity.validate()` |
| `Activity` | `domain/entities.py` | `assignees: list[UUID]` accumula gli assegnatari; richiede titolo non vuoto; `update_status()` chiama `Status.can_transition_to()` e muta lo stato. L'auto-cascade verso il `MissionAssignment` padre **non** è gestita dall'entità (nessun callback): è orchestrata da `ActivityService.update_status()` |
| `Badge` | `domain/entities.py` | Definizione riutilizzabile; non muta dopo la creazione |
| `BadgeAward` | `domain/entities.py` | `target_type` (`ASSIGNMENT` \| `ACTIVITY`), `target_id`, `recipients: list[UUID]` con i destinatari propagati al momento della creazione |

```python
@dataclass
class Mission:
    id: UUID
    title: str
    description: str
    assignment_policy: AssignmentPolicy
    objectives: list[Objective] = field(default_factory=list)

    def validate(self) -> None:
        if not self.title:
            raise ValidationError("title è obbligatorio")
        if not self.objectives:
            raise ValidationError("Una missione deve avere almeno un obiettivo")
        for obj in self.objectives:
            obj.validate()   # verifica ≥1 activity per obiettivo

    # Nessun add_objective: il blueprint è immutabile dopo la creazione.
    # Obiettivi e attività si definiscono solo qui, nel costruttore.
```

#### 2.1.2 Value Objects

I value objects sono `@dataclass(frozen=True)` definiti in `domain/value_objects.py`:

##### AssignmentPolicy

```python
@dataclass(frozen=True)
class AssignmentPolicy:
    max_total:      Optional[int] = None
    max_concurrent: Optional[int] = None

    def __post_init__(self) -> None:
        if self.max_total is not None and self.max_total < 1:
            raise ValidationError("max_total deve essere ≥ 1")
        if self.max_concurrent is not None and self.max_concurrent < 1:
            raise ValidationError("max_concurrent deve essere ≥ 1")
        if (self.max_total is not None and self.max_concurrent is not None
                and self.max_total < self.max_concurrent):
            raise ValidationError("max_total deve essere ≥ max_concurrent")

    @staticmethod
    def unlimited() -> 'AssignmentPolicy':
        return AssignmentPolicy()

    @staticmethod
    def once() -> 'AssignmentPolicy':
        return AssignmentPolicy(max_total=1)

    @staticmethod
    def once_active() -> 'AssignmentPolicy':
        return AssignmentPolicy(max_concurrent=1)
```

`AssignmentPolicy.unlimited()` è il default su ogni `Mission` appena creata.
La validazione in `__post_init__` garantisce che l'oggetto sia sempre in uno stato
coerente, indipendentemente da chi lo costruisce.

##### Profile e AclEntry (facciata ACL — `domain/acl.py`)

Il nucleo riusabile del sistema ACL è il package top-level `acl`, derivato da
`antlampas/ACL`. Il modulo `domain/acl.py` è una facciata di integrazione:
mantiene i nomi storici usati dal dominio MissionManager (`Operation`,
`ResourceRef`, `Profile`, `AclEntry`) e li normalizza verso `acl.domain`.
Matching, invarianti strutturali e decisione non sono più implementati qui:
sono delegati al package esterno tramite adapter sottili.

```python
ANON_SENTINEL: int = 2**31 - 1      # profilo anonimo e "soglia universale"
PUBLIC_GROUP:  str = "public"       # gruppo universale, implicito in ogni profilo
TYPE_ROOT_ID:  str = "*"            # id della radice di tipo (es. MISSION:*)
SYSTEM_RESOURCE = ResourceRef(ResourceType.SYSTEM, "global")

@dataclass(frozen=True)
class Profile:
    level:  int = ANON_SENTINEL                       # più basso = più privilegiato
    groups: frozenset[str] = frozenset()              # include sempre "public"

    @staticmethod
    def anonymous() -> "Profile": ...                 # (ANON_SENTINEL, {"public"})
    def stored_groups(self) -> list[str]: ...         # gruppi espliciti, senza "public"

@dataclass(frozen=True)
class AclEntry:
    id: UUID
    subject: SubjectRef            # USER(id) | PUBLIC
    resource: ResourceRef          # (tipo, id | "*" | "global")
    operation: Operation           # catalogo aperto con proprietà read_only
    permission: Permission         # ALLOW | DENY
    level: Optional[int] = None    # soglia: soddisfatta se profile.level <= level
    group: Optional[str] = None    # soddisfatto se group in profile.groups
    profile_join: JoinOp = JoinOp.OR
    subject_join: JoinOp = JoinOp.AND

    def validate(self) -> None: ...                   # INV-1..INV-5
    def matches(self, principal_id, profile) -> bool: ...  # §5.1 del modello
```

`AclEntry.validate()` applica le invarianti strutturali prima di ogni persistenza:
INV-1 (almeno uno tra livello e gruppo), INV-2 adattata (nessuna `ALLOW` su operazione
mutante soddisfacibile dal profilo anonimo — implementata proprio come
`matches(None, Profile.anonymous())`), INV-3 (livello ≥ 0, gruppo non vuoto), INV-4
(join nei valori ammessi, garantita dai tipi enum), INV-5 (PUBLIC + `subject_join=OR`
rifiutata). `matches()` è la funzione pura di match: `subjectMatch` combinato con la
parte di profilo secondo `profile_join`/`subject_join`.

`Profile` non ha identità propria ed è parte integrante di ogni `Person`; il
costruttore normalizza i gruppi aggiungendo sempre `PUBLIC_GROUP`, mentre il mapper
di persistenza salva i soli gruppi espliciti (`stored_groups()`).

#### 2.1.3 Status — enum comportamentale

`Status` è un enum che incapsula la macchina a stati delle entità operative. Invece di
disperdere la logica delle transizioni consentite nei service come strutture `if/elif`,
la macchina a stati è auto-contenuta nell'enum stesso.

```python
_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "UNASSIGNED":  {"ASSIGNED"},
    "ASSIGNED":    {"IN_PROGRESS", "FAILED"},
    "IN_PROGRESS": {"COMPLETED", "FAILED"},
    "COMPLETED":   set(),
    "FAILED":      set(),
}


class Status(Enum):
    UNASSIGNED  = "UNASSIGNED"
    ASSIGNED    = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED   = "COMPLETED"
    FAILED      = "FAILED"

    def can_transition_to(self, target: 'Status') -> bool:
        return target.value in _STATUS_TRANSITIONS.get(self.value, set())

    def is_terminal(self) -> bool:
        return self in (Status.COMPLETED, Status.FAILED)
```

La mappa delle transizioni è un dict a livello di modulo (`_STATUS_TRANSITIONS`), non un membro
dell'enum: definirla come attributo di classe la trasformerebbe in un valore dell'enumerazione.

`can_transition_to()` è chiamato da `MissionAssignment.update_status()` e da
`Activity.update_status()` prima di qualsiasi scrittura; se restituisce `False`,
viene sollevata immediatamente `StatusTransitionError`.

`AssignmentService.update_status()` usa `MissionAssignment.compute_outcome()` prima
di consentire `COMPLETED`: tutte le attività devono essere `COMPLETED`. Se almeno una
attività fallisce, `ActivityService.update_status()` propaga automaticamente `FAILED`
all'assignment padre non terminale.

#### 2.1.4 Entità di dominio — Person, Group, Zone

`Person`, `Group` e `Zone` sono **entità di dominio** di MissionManager al pari di `Mission` e
`Badge`. Sono definite come `@dataclass` mutabili in `domain/entities.py`, gestite da
`PersonService` attraverso i contratti `PersonRepository` e `GroupRepository`, e
persistite tramite gli adapter del Layer 3. La scelta del meccanismo di persistenza
(database locale o servizio esterno OIDC) è un dettaglio del Layer 3 che non modifica
alcun contratto architetturale.

```python
@dataclass
class Person:
    id:          UUID
    nicknames:   list[str]
    acl:         Profile = field(default_factory=Profile)   # default: minimo privilegio

    def primary_nickname(self) -> str:
        return self.nicknames[0] if self.nicknames else ""

    def validate(self) -> None:
        if not self.nicknames:
            raise ValidationError("Person richiede almeno un nickname")

@dataclass
class Group:
    id:   UUID
    zone: Optional['Zone'] = None

    def validate(self) -> None:
        pass  # gruppo valido anche senza zona

@dataclass
class Zone:
    id:          UUID
    type:        ZoneType
    name:        str
    description: Optional[str] = None

    def validate(self) -> None:
        if not self.name:
            raise ValidationError("Zone richiede un nome")
```

`Profile` è il value object ACL associato a ogni `Person` (§2.1.2): l'entità lo
trasporta ma non lo interpreta; la valutazione avviene in `AuthorizationPolicy`
contro le `AclEntry` persistite, al confine del sistema.

#### 2.1.5 Eccezioni di dominio

La gerarchia completa di eccezioni è definita in **`shared/errors.py`**. `domain/exceptions.py`
ri-esporta le classi principali per compatibilità con i layer superiori che dipendono da
`domain`. `MissionManagerError` è la classe base:

| Classe | HTTP | CLI | Quando |
|---|---|---|---|
| `MissionManagerError` | base | base | Classe base di tutte le eccezioni applicative |
| `ValidationError` | 400 | exit 1 | Input non valido: campi vuoti, lista vuota, range errato |
| `NotFoundError` | 404 | exit 1 | Risorsa non trovata (mission, assignment, badge, persona) |
| `ACLError` | 403 | exit 1 | Operatore non ha il profilo ACL richiesto |
| `StatusTransitionError` | 409 | exit 1 | Transizione di stato non consentita dalla macchina a stati |
| `OperationAbortedError` | 422 | exit 1 | Un plugin ha impostato `ctx.abort = True` |
| `AuthenticationError` | 401 | exit 1 | Identità non verificabile (token mancante/invalido) |
| `ForbiddenError` | 403 | exit 1 | Azione non consentita (distinzione semantica da `ACLError`) |
| `RateLimitExceededError` | 429 | exit 1 | Troppe richieste in un intervallo di tempo |
| `ExtensionLoadError` | — | — | Errore durante il caricamento di un'estensione |
| `ExtensionConflictError` | — | — | Conflitto di nome nel registro estensioni |

`StatusTransitionError` porta il valore corrente e quello richiesto per messaggi
diagnostici precisi. `OperationAbortedError` porta `abort_reason` opzionale.

`RateLimitPolicy` è invocata dal middleware REST per ogni operazione mutante,
comprese assegnazione/rimozione, directory persone e gruppi, password e route di
estensione non classificate. `RateLimitExceededError` viene serializzata come HTTP 429
con limite e finestra nel corpo JSON.

---

### 2.2 Layer 2 — Ports (contratti)

Il Layer 2 definisce i **contratti astratti** che isolano i service dai meccanismi concreti
di persistenza, identità, comunicazione con il servizio esterno, plugin ed estensioni.
Gli adapter del Layer 3 implementano questi contratti; i service li ricevono tramite
dependency injection al momento della costruzione.

Tutti i contratti sono dichiarati come `typing.Protocol` con `@runtime_checkable`. La
tipizzazione strutturale di Python (duck typing verificato) garantisce che qualunque
classe che implementi i metodi richiesti con le firme corrette soddisfi il contratto
senza necessità di ereditarietà esplicita da classi base.

#### 2.2.1 Repository interfaces

`BaseRepository[T]` è il contratto CRUD generico, parametrizzato sul tipo dell'entità:

```python
@runtime_checkable
class BaseRepository(Protocol[T]):
    def get(self, id: UUID) -> T: ...
    def list(self, filters: dict) -> list[T]: ...
    def save(self, entity: T) -> T: ...
    def delete(self, id: UUID) -> bool: ...
    def exists(self, id: UUID) -> bool: ...
```

Ogni repository specializzato estende il contratto aggiungendo le query semantiche
proprie. Le firme complete sono nel diagramma `diagrams/class/class_ports.puml`:

| Repository | Query aggiuntive |
|---|---|
| `MissionRepository` | `get_by_title(title: str) → Optional[Mission]` |
| `MissionAssignmentRepository` | `get_by_mission`, `get_by_assignee`, `get_by_status`, `count_by_mission`, `count_active_by_mission` |
| `ObjectiveRepository` | `get_by_assignment(assignment_id) → list[Objective]` |
| `ActivityRepository` | `get_by_objective(oid) → list[Activity]`, `get_by_person(person_id) → list[Activity]` |
| `BadgeRepository` | Nessuna query aggiuntiva (CRUD sulle definizioni) |
| `BadgeAwardRepository` | `get_by_person`, `get_by_assignment`, `get_by_activity`, `exists_for_target` |
| `AclEntryRepository` | `get`, `list_for(risorsa, operazione)`, `list_by_resource`, `list_all`, `save`, `delete`, `delete_by_resource`, `is_empty` |

`count_by_mission()` restituisce il totale storico di tutti i `MissionAssignment` della
missione, indipendentemente dallo stato. `count_active_by_mission()` conta solo quelli
effettivamente operativi (`ASSIGNED`, `IN_PROGRESS`): `UNASSIGNED` è una bozza e non
consuma capacità concorrente. Questi due metodi
sono usati esclusivamente da `AssignmentService` per la verifica di `AssignmentPolicy`.

#### 2.2.2 PersonRepository e GroupRepository

`PersonRepository` e `GroupRepository` seguono il medesimo pattern di `BaseRepository[T]`
degli altri repository del sistema, con le query semantiche proprie delle entità `Person`
e `Group`. Nel codice corrente sono dichiarati in `domain/repositories.py`.

```python
@runtime_checkable
class PersonRepository(BaseRepository[Person], Protocol):
    def get_by_group(self, group_id: UUID) -> list[Person]: ...
    def get_by_nickname(self, nickname: str) -> Optional[Person]: ...

@runtime_checkable
class GroupRepository(BaseRepository[Group], Protocol):
    def add_member(self, group_id: UUID, person_id: UUID) -> None: ...
    def remove_member(self, group_id: UUID, person_id: UUID) -> None: ...
```

I service li usano per gli scopi seguenti:

- **Validazione esistenza** (`AssignmentService`, `ActivityService`): `exists(id)` verifica
  che una `Person` o un `Group` esista nel repository prima di creare un `MissionAssignment`
  o assegnare un'attività. Se non trovato: `NotFoundError`.
- **Risoluzione membri** (`ActivityService`, `BadgeService`): `get_by_group(group_id)` restituisce
  le `Person` associate al gruppo, usata per verificare il perimetro degli assegnatari
  di un'attività e per calcolare i destinatari di un `BadgeAward` propagato a un gruppo.
- **Gestione membership** (`PersonService`): `add_group_member()` e `remove_group_member()`
  delegano a `GroupRepository.add_member()` / `remove_member()`. Il backend locale aggiorna
  la tabella N-N; il backend OIDC usa gli endpoint di membership del provider.
- **Profilo operatore** (`OperatorIdentityAdapter`, `PersonProfileProvider`):
  `get(operator_id)` materializza il profilo completo (incluso il `Profile` ACL)
  dell'operatore autenticato o del principale da autorizzare.
- **Gestione ciclo di vita** (`PersonService`): `save()` / `delete()` persistono le
  modifiche al ciclo di vita di `Person` e `Group`.

#### 2.2.3 OperatorIdentityProvider

```python
@runtime_checkable
class OperatorIdentityProvider(Protocol):
    def get_current_operator(self) -> Person: ...
```

`OperatorIdentityProvider` è una porta del Layer 2 usata **esclusivamente dai middleware
dei frontend**, mai dai service stessi. I service ricevono i dati dell'operatore solo se
necessari all'operazione (es. `operator_id` nel `HookContext`), passati come parametri
espliciti dal frontend dopo l'autenticazione.

L'adapter è specifico per ciascun frontend:

| Frontend | Adapter | Come stabilisce l'identità |
|---|---|---|
| REST API | `RestOperatorIdentityAdapter` | Valida Bearer token JWT locali o OIDC, poi chiama `PersonRepository.get()` |
| Web App | `WebOperatorIdentityAdapter` | Legge la sessione Quart/cookie, poi chiama `PersonRepository.get()` |
| CLI | `CliOperatorIdentityAdapter` | Legge l'identità da `MISSIONMANAGER_OPERATOR_ID`, poi chiama `PersonRepository.get()` |

In tutti i casi l'adapter chiama `PersonRepository.get(operator_id)` per materializzare
il profilo completo con il `Profile` ACL. Il tipo di eccezione sollevata quando l'identità
non può essere stabilita dipende dal frontend:

- `RestOperatorIdentityAdapter` e `WebOperatorIdentityAdapter` sollevano `AuthenticationError`
  (token/sessione mancante o non valido). I middleware **non** la trasformano più in un
  errore immediato: il richiedente prosegue come **anonimo** (principal `None` → profilo
  anonimo implicito, DESIGN §10.3) e riceve 401/redirect solo se la decisione ACL è DENIED.
- `CliOperatorIdentityAdapter` restituisce `None` in modalità `anonymous` (profilo anonimo)
  e solleva `ACLError` in modalità `user` se l'`operator_id` non è impostato o non
  corrisponde ad alcuna `Person`.

Distinte da `OperatorIdentityProvider` (chi sta chiamando) sono le porte di risoluzione
del sistema ACL, usate da `AuthorizationPolicy`:

```python
@runtime_checkable
class ProfileProvider(Protocol):
    def profile_of(self, principal_id: Optional[UUID]) -> Profile: ...

@runtime_checkable
class ResourceHierarchyProvider(Protocol):
    def parents_of(self, resource: ResourceRef) -> list[ResourceRef]: ...
```

Gli adapter concreti sono in `infrastructure/acl.py`: `PersonProfileProvider` (delega a
`PersonRepository.get`, anonimo per `None`/persona inesistente) e
`MissionResourceHierarchyProvider` (catena `ACTIVITY → OBJECTIVE → ASSIGNMENT|MISSION`;
ogni risorsa concreta risale alla radice del proprio tipo `TYPE:*`, con l'albero
operativo radicato in `MISSION:*`; `SYSTEM:global` e le radici non hanno padri).

In modalità OIDC, `RestOperatorIdentityAdapter` verifica il JWT tramite il JWKS dell'identity
provider (Authentik o Keycloak) ed estrae l'identificatore (`sub` o `preferred_username`)
per recuperare la `Person` corrispondente tramite `PersonRepository.get()`.

#### 2.2.4 MissionHook e tipi correlati

`MissionHook` è la porta del Layer 2 per il sistema di plugin:

```python
@runtime_checkable
class MissionHook(Protocol):
    @property
    def manifest(self) -> PluginManifest: ...
    def execute(self, context: HookContext) -> None: ...
```

```python
@dataclass(frozen=True)
class PluginManifest:
    id:          str
    name:        str
    version:     str
    description: str
    hooks:       list[HookPoint]
    trust_level: PluginTrustLevel = PluginTrustLevel.SANDBOXED
    priority:    int = 0
    code_checksum: str = ""
```

`trust_level` può essere `TRUSTED` o `SANDBOXED` (enum `PluginTrustLevel` in `domain/plugins.py`).
Il livello effettivo è autorizzato al bootstrap da `PluginLoader` tramite `PluginTrustRegistry`,
che verifica `manifest_checksum` e `code_checksum` prima dell'import. Se il plugin non è nel
registro, il codice non viene importato.
`priority` determina l'ordine di esecuzione (valori maggiori vengono eseguiti per primi).

```python
@dataclass
class HookContext:
    hook_point:   HookPoint
    operator_id:  UUID
    payload:      dict
    result:       Any   = None
    abort:        bool  = False
    abort_reason: Optional[str] = None
```

`HookContext` è l'unico oggetto condiviso tra il service e tutti i plugin nell'iterazione
di `fire()`. È mutabile: i plugin possono aggiornare `result` (BEFORE_* per arricchire
dati pre-creazione; AFTER_* per aggiungere side-effect), oppure impostare `abort=True`
per annullare l'operazione (solo BEFORE_*).

`HookPoint` è un enum del Layer 2 con 24 costanti (12 operazioni × BEFORE/AFTER), che
copre tutte le operazioni mutanti dei service di dominio. Gli hook generici
(`UPDATE_STATUS`, `ASSIGN`, `DELETE`) coprono più tipi di entità e portano `entity_type`
nel payload; i sottosistemi di sicurezza (ACL, autenticazione, profili) non espongono hook
per progetto (anti-escalation):

```python
class HookPoint(Enum):
    BEFORE_CREATE_MISSION    = "BEFORE_CREATE_MISSION"
    AFTER_CREATE_MISSION     = "AFTER_CREATE_MISSION"
    BEFORE_CREATE_ASSIGNMENT = "BEFORE_CREATE_ASSIGNMENT"
    AFTER_CREATE_ASSIGNMENT  = "AFTER_CREATE_ASSIGNMENT"
    BEFORE_UPDATE_STATUS     = "BEFORE_UPDATE_STATUS"    # entity_type: ASSIGNMENT|ACTIVITY
    AFTER_UPDATE_STATUS      = "AFTER_UPDATE_STATUS"
    BEFORE_AWARD_BADGE       = "BEFORE_AWARD_BADGE"
    AFTER_AWARD_BADGE        = "AFTER_AWARD_BADGE"
    BEFORE_ASSIGN            = "BEFORE_ASSIGN"           # entity_type: ASSIGNMENT|ACTIVITY,
    AFTER_ASSIGN             = "AFTER_ASSIGN"            #   action: ASSIGN|UNASSIGN
    BEFORE_DELETE            = "BEFORE_DELETE"           # entity_type: MISSION|ASSIGNMENT|
    AFTER_DELETE             = "AFTER_DELETE"            #   PERSON|GROUP
    BEFORE_CREATE_BADGE      = "BEFORE_CREATE_BADGE"
    AFTER_CREATE_BADGE       = "AFTER_CREATE_BADGE"
    BEFORE_CREATE_PERSON     = "BEFORE_CREATE_PERSON"
    AFTER_CREATE_PERSON      = "AFTER_CREATE_PERSON"
    BEFORE_UPDATE_PERSON     = "BEFORE_UPDATE_PERSON"
    AFTER_UPDATE_PERSON      = "AFTER_UPDATE_PERSON"
    BEFORE_CREATE_GROUP      = "BEFORE_CREATE_GROUP"
    AFTER_CREATE_GROUP       = "AFTER_CREATE_GROUP"
    BEFORE_UPDATE_GROUP      = "BEFORE_UPDATE_GROUP"
    AFTER_UPDATE_GROUP       = "AFTER_UPDATE_GROUP"
    BEFORE_MANAGE_MEMBERS    = "BEFORE_MANAGE_MEMBERS"   # action: ADD|REMOVE
    AFTER_MANAGE_MEMBERS     = "AFTER_MANAGE_MEMBERS"
```

Nei flussi anonimi ammessi (creazione del primo amministratore) gli hook vengono eseguiti
con `operator_id = None` nel contesto.

Oltre ai membri dell'enum, il campo `hooks` del manifest può elencare i nomi degli **hook
point custom dichiarati dalle estensioni** (DESIGN §15.7), nel formato
`BEFORE_EXT:<ext_id>:<evento>` / `AFTER_EXT:<ext_id>:<evento>`; la validazione vive in
`application/extension_hooks.py` (`is_extension_hook_name`) e ogni altro nome viene
rifiutato da `PluginLoader`. `PluginRegistry` indicizza indifferentemente membri enum e
nomi stringa (`dict[HookPoint | str, list[MissionHook]]`); i service core scatenano sempre
membri dell'enum, quindi una stringa arbitraria non può intercettare i flussi core.

#### 2.2.5 MissionExtension e tipi correlati

`MissionExtension` è un Protocol strutturale per il sistema di estensioni:

```python
class MissionExtension(Protocol):
    manifest: ExtensionManifest
    def execute(self, request: ExtensionRequest) -> ExtensionResult: ...
```

```python
@dataclass(frozen=True)
class ExtensionManifest:
    id:                 str
    name:               str
    version:            str
    description:        str
    code_checksum:      str
    provides_routes:    list[RouteSpec]
    provides_commands:  list[CommandSpec]

@dataclass(frozen=True)
class RouteSpec:
    path:        str
    method:      str
    description: str

@dataclass(frozen=True)
class CommandSpec:
    name:        str
    description: str

@dataclass
class ExtensionRequest:
    operator_id: UUID | None = None
    params:      dict = field(default_factory=dict)
    body:        dict = field(default_factory=dict)
    subject:     Any = None

@dataclass
class ExtensionResult:
    data:        Any
    status_code: int
    message:     Optional[str] = None
```

`MissionExtension` è un `typing.Protocol`: il core richiede strutturalmente un attributo
`manifest` e un metodo `execute(request)`, mentre il costruttore resta responsabilità del bundle.
`ExtensionLoader` ispeziona la firma della classe `Extension` e inietta solo `manifest` e i service
applicativi accettati dal costruttore; questo mantiene le estensioni debolmente accoppiate al core.

#### 2.2.6 CredentialRepository e LocalCredential

`CredentialRepository` (`domain/auth.py`) è la porta delle **credenziali locali**, separata
dall'anagrafica `Person`: una `Person` può esistere senza credenziali (tipico del backend OIDC,
dove la porta non è usata). Il contratto è ridotto e tipizzato su un value object di dominio,
`LocalCredential`, che porta — oltre all'hash bcrypt — lo **stato di hardening** del login:

```python
@dataclass
class LocalCredential:
    person_id: UUID
    hashed_password: str
    failed_attempts: int = 0            # tentativi falliti consecutivi
    locked_until: Optional[datetime] = None   # blocco temporizzato (None = sbloccato)
    must_change_password: bool = False  # cambio forzato al primo accesso

@runtime_checkable
class CredentialRepository(Protocol):
    def get(self, person_id: UUID) -> Optional[LocalCredential]: ...
    def save(self, credential: LocalCredential) -> None: ...
    def delete(self, person_id: UUID) -> bool: ...
```

L'adapter `SqlAlchemyCredentialRepository` mappa il value object sulla tabella `mm_credentials`
(colonne `hashed_password`, `failed_attempts`, `locked_until`, `must_change_password`,
`created_at`, `changed_at`). `changed_at` è aggiornato **solo quando l'hash cambia**, non sui
salvataggi di solo stato di lockout, così traccia l'ultimo cambio *password*. Lo schema è creato
con `Base.metadata.create_all` (nessun Alembic): le tre colonne di hardening valgono su database
nuovi; su un DB preesistente vanno aggiunte con una migrazione manuale.

---

### 2.3 Layer 3 — Adapters (astratti)

#### 2.3.1 Ruolo e collocazione

Il Layer 3 implementa i contratti del Layer 2 con classi base astratte tecnologicamente
neutre e adapter concreti sotto `infrastructure/`. Il dettaglio concreto (quale database,
quale ORM, quale client HTTP per il servizio esterno) è responsabilità delle
implementazioni concrete che estendono queste classi base.

I service non dipendono mai direttamente dagli adapter: ricevono i contratti del Layer 2
tramite dependency injection al bootstrap. Questo rende i service verificabili con
implementazioni in memoria (`InMemoryMissionRepository`, `InMemoryPersonRepository`, ecc.)
senza toccare il database o il servizio esterno reale.

#### 2.3.2 RepositoryAdapter

```python
class RepositoryAdapter(ABC, Generic[T]):
    """Base astratta per tutti gli adapter di repository.
    Le implementazioni concrete estendono questa classe
    e iniettano il meccanismo di persistenza nel costruttore."""

    @abstractmethod
    def get(self, id: UUID) -> T: ...
    @abstractmethod
    def list(self, filters: dict) -> list[T]: ...
    @abstractmethod
    def save(self, entity: T) -> T: ...
    @abstractmethod
    def delete(self, id: UUID) -> bool: ...
    @abstractmethod
    def exists(self, id: UUID) -> bool: ...
```

Nel codice corrente i repository concreti di Mission, MissionAssignment, Objective, Activity,
Badge e BadgeAward estendono **direttamente** `RepositoryAdapter[T]` (es.
`SqlAlchemyMissionRepository(RepositoryAdapter[Mission])`) e aggiungono i metodi semantici
propri (es. `get_by_title()`) implementandoli tramite il meccanismo di persistenza scelto.
Solo `Person` e `Group` hanno una classe base astratta intermedia dedicata
(`PersonRepositoryAdapter`, `GroupRepositoryAdapter`, vedi §2.3.3), perché il loro contratto è
condiviso tra due famiglie di implementazioni concrete (SQLAlchemy e OIDC).

#### 2.3.3 PersonRepositoryAdapter e GroupRepositoryAdapter

```python
class PersonRepositoryAdapter(RepositoryAdapter[Person], ABC):
    """Base astratta per la persistenza di Person.
    Le implementazioni concrete scelgono il backend."""

    @abstractmethod
    def get_by_group(self, group_id: UUID) -> list[Person]: ...

class GroupRepositoryAdapter(RepositoryAdapter[Group], ABC):
    """Base astratta per la persistenza di Group."""
    @abstractmethod
    def add_member(self, group_id: UUID, person_id: UUID) -> None: ...

    @abstractmethod
    def remove_member(self, group_id: UUID, person_id: UUID) -> None: ...
```

**Due famiglie di implementazioni concrete, selezionabili tramite configurazione:**

**Backend locale (SQLAlchemy — PostgreSQL o MySQL):**

```python
class SqlAlchemyPersonRepository(PersonRepositoryAdapter):
    """Implementazione SQLAlchemy. Riceve una Session nel costruttore.
    Supporta PostgreSQL (postgresql+psycopg2://) e MySQL (mysql+pymysql://)
    attraverso il dialetto configurato in DATABASE_URL."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, id: UUID) -> Person: ...
    def get_by_group(self, group_id: UUID) -> list[Person]: ...
    # ... implementa tutti i metodi tramite ORM SQLAlchemy ...
```

**Backend OIDC (Authentik / Keycloak):**

```python
class OidcPersonRepository(PersonRepositoryAdapter):
    """Implementazione che dialoga con un identity provider OIDC.
    Authentik: /api/v3/core/users/  e  /api/v3/core/groups/
    Keycloak:  /admin/realms/{realm}/users/  e  .../groups/
    get_by_group() risolve i membri del gruppo tramite le API di gruppo
    dell'identity provider.
    save() e delete() usano le API admin dell'OIDC provider per creare,
    modificare o eliminare gli utenti — abilitando PersonService.add/remove()
    in modalità OIDC."""

    def __init__(self, oidc_url: str, admin_token: str,
                 provider: str = "authentik") -> None:
        self._base     = oidc_url.rstrip("/")
        self._token    = admin_token
        self._provider = provider          # "authentik" | "keycloak"

    def get(self, id: UUID) -> Person: ...
    def get_by_group(self, group_id: UUID) -> list[Person]: ...
    # ... chiama le API REST dell'OIDC provider ...
```

La scelta del backend è determinata dalla variabile `PERSON_BACKEND` nella configurazione
(`local` o `oidc`). Il resto del sistema non subisce alcuna modifica: i service dipendono
esclusivamente dai contratti `PersonRepository` e `GroupRepository`.

#### 2.3.4 OperatorIdentityAdapter

`OperatorIdentityAdapter` riceve `PersonRepository` nel costruttore e chiama
`person_repo.get(operator_id)` per materializzare il profilo completo dell'operatore
con il `Profile` ACL. Le tre implementazioni concrete (`RestOperatorIdentityAdapter`,
`WebOperatorIdentityAdapter`, `CliOperatorIdentityAdapter`) differiscono solo nel modo
in cui estraggono l'`operator_id` dal contesto della richiesta (JWT, sessione, env var).

In modalità OIDC, `RestOperatorIdentityAdapter` valida il JWT tramite il JWKS endpoint
dell'identity provider prima di chiamare `PersonRepository.get()`.

---

#### 2.3.5 MissionHookAdapter

```python
class MissionHookAdapter(ABC):
    """Base astratta per i plugin hook concreti."""

    @property
    @abstractmethod
    def manifest(self) -> PluginManifest: ...

    @abstractmethod
    def execute(self, context: HookContext) -> None: ...
```

Le implementazioni concrete (es. `ExternalSyncHook` che propaga gli aggiornamenti di
stato verso sistemi operativi) estendono `MissionHookAdapter` e vengono registrate nel
`PluginRegistry` al bootstrap.

---

### 2.4 Layer 4 — Services

I service applicativi sono il cuore del sistema: orchestrano i casi d'uso coordinando
repository, porte esterne, plugin ed estensioni. Non contengono logica di dominio (che
rimane nel Layer 1) né dettagli infrastrutturali (che rimangono nel Layer 3). Il loro
ruolo è **coordinare**.

I service sono singleton: un'istanza per processo, costruita al bootstrap e condivisa
tra tutte le richieste. Questo è possibile perché l'identità dell'operatore corrente
non è una dipendenza del costruttore ma un parametro esplicito fornito dal frontend dopo
la verifica ACL — oppure è irrilevante per i service che non hanno bisogno dell'identità
(tutti i service di MissionManager non ricevono `OperatorIdentityProvider` come dipendenza:
l'ACL viene verificata nel middleware frontend, non nei service).

#### 2.4.1 Pattern generale di esecuzione

Ogni metodo pubblico di un service MissionManager segue questo schema, documentato in
`diagrams/activity/activity_service_pattern.puml`:

| Step | Operazione | Eccezione se fallisce |
|---|---|---|
| 1 | Validazione input di dominio | `ValidationError` (HTTP 400) |
| 2 | Verifica `AssignmentPolicy` (solo `AssignmentService.create()`) | `ValidationError` (HTTP 400) |
| 3 | Verifica esistenza nel repository / servizio esterno | `NotFoundError` (HTTP 404) |
| 4 | `plugin_registry.fire(BEFORE_*, context)` (se plugin_registry presente) | `OperationAbortedError` (HTTP 422) se `ctx.abort` |
| 5 | Operazione principale (repository) | eccezione specifica |
| 6 | `plugin_registry.fire(AFTER_*, context)` (se plugin_registry presente) | — |
| 7 | Ritorno DTO al Frontend | — |

**Enforcement al confine.** In MissionManager l'ACL non è verificata nei service: il
controllo avviene nel middleware dei frontend (`AuthMiddleware` per REST, `ACLMiddleware`
per Web App, `@require_acl` nei comandi CLI) tramite `AuthorizationPolicy.is_allowed()`
prima che la richiesta raggiunga i service. I service ricevono solo dati già autorizzati;
il loro unico aggancio al sistema ACL è la notifica ad `AclService` di
creazione/eliminazione delle risorse (seeding e cascata, nella stessa transazione).

**`plugin_registry` è opzionale.** I service accettano `plugin_registry: Optional[PluginRegistry] = None`
nel costruttore. Se assente (test, deployment senza plugin), `fire()` non viene mai
chiamato e il comportamento è identico a prima dell'introduzione del sistema di plugin.

#### 2.4.2 Sistema ACL: AuthorizationPolicy e AclService

**`AuthorizationPolicy`** (`application/authorization.py`) è una facciata MissionManager
verso `auth.application.AuthorizationService` del package `antlampas/Auth`: conserva la firma
storica `is_allowed(principal_id, operation, resource) → bool`, ma registra il package
`antlampas/ACL` come modello access-control attivo tramite `ACLAccessControlModel`
(`application/auth_acl.py`). La facciata traduce `UUID|None`, `Operation` e `ResourceRef`
locali nell'identità, nel catalogo operazioni e nelle resource canoniche richieste da Auth;
Auth costruisce il contesto e invoca il modello ACL registrato.

```python
class AuthorizationPolicy:
    def __init__(self, entry_repo: AclEntryRepository,
                 profile_provider: ProfileProvider,
                 hierarchy_provider: ResourceHierarchyProvider,
                 uow=None): ...

    def is_allowed(self, principal_id, operation, resource) -> bool:
        identity = identity_from_principal(principal_id)
        return self._authz.is_allowed(identity, operation.value, resource)
```

La precedenza resta quella del modello ACL: `DENY > ALLOW > DENIED`, incluso il deny
ereditato dai padri. Le entry proprie esauriscono la decisione della risorsa corrente;
se non esistono entry proprie, il modello ACL risale la gerarchia tramite
`ResourceHierarchyProvider` e protegge dai cicli. `AuthorizationPolicy` resta condivisa
tra Web, REST e CLI e viene costruita una volta al bootstrap; `AclService` continua a usare
`acl.application.ACLService` per amministrazione, seeding e cascata delle entry.

**`AclService`** (`application/services/acl_service.py`) è l'adapter applicativo sopra
`acl.application.ACLService`: mantiene le firme REST/Web/CLI esistenti e traduce gli errori
del package esterno in eccezioni MissionManager (`ForbiddenError`, `NotFoundError`,
`ValidationError`).

- CRUD (`list_entries`, `list_all_entries`, `create_entry`, `update_entry`,
  `delete_entry`) con validazione e grant constraints del package `acl`;
- **autoprotezione**: ogni mutazione richiede `MANAGE_ACL` sulla risorsa interessata
  *oppure* `MANAGE_ACL` su `SYSTEM:global` (il tier amministrativo è la chiave mastra,
  dato che `MANAGE_ACL` non eredita);
- **seeding automatico** (`on_resource_created`): delega alla `SeedingPolicy` del package
  `acl`, costruita dalla configurazione MissionManager, nella stessa
  transazione della creazione. Il default di MissionManager semina il solo `MANAGE_ACL`
  al creatore (`ALLOW MANAGE_ACL USER(creatore)` con soglia universale) per `MISSION`,
  `ASSIGNMENT` e `BADGE` — controllo revocabile senza privatizzare la risorsa;
- **cascata** (`on_resource_deleted`): elimina le entry della risorsa rimossa; la cancellazione di una missione propaga la cascata anche agli assignment figli, e la rimozione di una persona elimina le entry con soggetto `USER(id)` (`on_subject_deleted`);
- **bootstrap** (`ensure_bootstrap_entries`): su repository vuoto semina le entry-soglia
  di default (`ALLOW <op> PUBLIC level≤L`) su `SYSTEM:global` e sulle radici di tipo,
  con le tre soglie di configurazione (lettura=100, scrittura=50, amministrazione=0).
  Le entry sono oggetti `acl.domain.ACLEntry` persistiti nell'attuale tabella
  `mm_acl_entries`.

`SeedingPolicy` è un dataclass congelato (`enabled`, `operations_by_type`) costruito al
bootstrap da `AclConfig.seeding_enabled`.

#### 2.4.3 MissionService

Gestisce le operazioni sul blueprint della missione. Non gestisce assegnazioni né stato.

```
create(title, desc, objectives) → MissionDTO:
  1. Valida title (1–255 caratteri), desc (0–4096), len(objectives) ≥ 1,
     ogni objective ha len(activities) ≥ 1
  2. HookContext(BEFORE_CREATE_MISSION, payload={title, desc, objectives})
  3. fire(BEFORE_CREATE_MISSION, ctx) → OperationAbortedError se ctx.abort
  4. Costruisce Mission con Objective e Activity instances
  5. mission_repo.save(mission)
  6. fire(AFTER_CREATE_MISSION, ctx con result=mission)
  7. Restituisce MissionDTO

get(id) → MissionDTO:
  1. mission_repo.get(id) → NotFoundError se assente
  2. Restituisce MissionDTO

list(filters) → List[MissionDTO]:
  1. mission_repo.list(filters) con filtro opzionale su titolo
  2. Restituisce List[MissionDTO]

# Nessun add_objective: il blueprint è immutabile dopo la creazione. Obiettivi e
# attività si definiscono solo in create(); non esiste alcuna operazione di
# aggiunta/modifica successiva (DESIGN §2.1).

delete(mission_id) → None:
  1. mission_repo.get(mission_id) → NotFoundError se assente
  2. mission_repo.delete(mission_id)
```

#### 2.4.4 AssignmentService — verifica AssignmentPolicy

La verifica di `AssignmentPolicy` avviene in `AssignmentService.create()` **prima** del
hook `BEFORE_CREATE_ASSIGNMENT`. Questo garantisce che un plugin non possa essere invocato
per una missione la cui policy non consente ulteriori assignment.

```
verifica_policy(mission):
  policy = mission.assignment_policy

  # Controlla il limite storico (max_total)
  if policy.max_total is not None:
    total = assignment_repo.count_by_mission(mission.id)
    if total >= policy.max_total:
      raise ValidationError(
        f"Questa missione ha già raggiunto il limite di {policy.max_total} assegnazioni"
      )

  # Controlla il limite sugli assignment attivi (max_concurrent)
  if policy.max_concurrent is not None:
    active = assignment_repo.count_active_by_mission(mission.id)
    if active >= policy.max_concurrent:
      raise ValidationError(
        f"Questa missione ha già {active} assegnazioni attive "
        f"(limite: {policy.max_concurrent})"
      )
```

`count_active_by_mission()` conta gli assignment in stato `ASSIGNED` o `IN_PROGRESS`.
Le bozze `UNASSIGNED` non contribuiscono al contatore; il controllo viene ripetuto anche
in `assign()`, così una serie di bozze non può aggirare `max_concurrent`.

#### 2.4.5 AssignmentService — replicazione del blueprint

Quando `AssignmentService.create()` crea un `MissionAssignment`, replica il blueprint
della `Mission`: vengono create nuove istanze di `Objective` e `Activity` con ID propri,
indipendenti dal blueprint originale e dagli altri assignment della stessa missione.

```
replicate_blueprint(mission, assignment_id) → list[Objective]:
  new_objectives = []
  for blueprint_obj in mission.objectives:
    new_obj = Objective(
      id          = uuid4(),
      description = blueprint_obj.description,
      assignment_id = assignment_id,
      activities  = []
    )
    for blueprint_act in blueprint_obj.activities:
      new_act = Activity(
        id          = uuid4(),
        title       = blueprint_act.title,
        description = blueprint_act.description,
        status      = Status.UNASSIGNED,
        assignees   = [],
        objective_id = new_obj.id
      )
      new_obj.activities.append(new_act)
    new_objectives.append(new_obj)
  return new_objectives
  # Gli obiettivi/attività non vengono salvati singolarmente qui: l'intero
  # aggregato viene persistito da create() con un'unica assignment_repo.save(assignment),
  # che propaga la scrittura in cascata a obiettivi e attività.
```

Questo design — deep clone di obiettivi e attività — garantisce che ogni assignment
abbia un ciclo di vita completamente indipendente dal blueprint e dagli altri assignment
della stessa missione. (Il blueprint è comunque immutabile dopo la creazione, quindi non
può divergere dalle copie già istanziate.)

**Salvataggio atomico.** I repository eseguono solo `flush()`; una
`SqlAlchemyUnitOfWork` per caso d'uso esegue il singolo commit o il rollback. Assignment,
obiettivi e attività vengono quindi confermati o annullati insieme.

#### 2.4.6 AssignmentService — assign()

```
assign(assignment_id, assignee_type, assignee_id) → AssignmentDTO:
  1. assignment_repo.get(assignment_id) → NotFoundError se assente
  2. Verifica assignment.status == UNASSIGNED
     → ValidationError se già assegnato
  3. Valida il soggetto:
     if assignee_type == PERSON:
       person_repo.exists(assignee_id)
       → NotFoundError se non esiste
     elif assignee_type == GROUP:
       group_repo.exists(assignee_id)
       → NotFoundError se non esiste
  4. assignment.assign_to(assignee_type, assignee_id)
     → MissionAssignment.update_status(ASSIGNED)
  5. assignment_repo.save(assignment)
  6. Restituisce AssignmentDTO con status=ASSIGNED
```

#### 2.4.7 ActivityService — auto-cascade dello stato

L'auto-cascade è la caratteristica più delicata di `ActivityService.update_status()`.
Quando un'attività viene portata a `IN_PROGRESS`, il `MissionAssignment` padre deve
essere anch'esso portato automaticamente a `IN_PROGRESS` se si trova ancora in stato
`ASSIGNED`.

```
update_status(activity_id, new_status) → ActivityDTO:
  1. activity_repo.get(activity_id) → NotFoundError se assente
  2. objective = objective_repo.get(activity.objective_id)   # fetch anticipato
     if objective.assignment_id is None:
       → ValidationError (attività del blueprint, non di un'assegnazione)
  3. activity.status.can_transition_to(new_status)
     → StatusTransitionError se non consentita
  4. Se new_status == IN_PROGRESS: verifica len(activity.assignees) ≥ 1
     → ValidationError se nessun assegnatario
  5. HookContext(BEFORE_UPDATE_STATUS, payload={entity_id, "ACTIVITY", new_status})
  6. fire(BEFORE_UPDATE_STATUS, ctx)
  7. activity.update_status(new_status)
  8. activity_repo.save(activity)
  9. AUTO-CASCADE:
     if new_status == IN_PROGRESS:
       assignment = assignment_repo.get(objective.assignment_id)   # objective già recuperato
     if assignment.status == Status.ASSIGNED:
       assignment.update_status(Status.IN_PROGRESS)
       assignment_repo.save(assignment)
     elif new_status == Status.FAILED and not assignment.status.is_terminal():
       assignment.update_status(Status.FAILED)
       assignment_repo.save(assignment)
  10. fire(AFTER_UPDATE_STATUS, ctx con result=activity)
  11. Restituisce ActivityDTO
```

`unassign()` è consentito solo prima di `IN_PROGRESS`; se rimuove l'ultimo assegnatario,
riporta l'attività da `ASSIGNED` a `UNASSIGNED`. Assegnazioni duplicate sono rifiutate.

**Atomicità.** Le scritture di attività e assignment padre sono nella stessa
`SqlAlchemyUnitOfWork`: se una fallisce viene eseguito rollback e nessuna modifica persiste.
Quando un'attività passa a `FAILED`, anche l'assignment padre non terminale passa
automaticamente a `FAILED`.

**`assign_to()` analogamente.** `ActivityService.assign_to()` porta automaticamente
l'attività da `UNASSIGNED` ad `ASSIGNED` quando viene aggiunto il primo assegnatario:

```
assign_to(activity_id, person_id) → ActivityDTO:
  1. person_repo.exists(person_id)  → NotFoundError se persona sconosciuta
  2. activity_repo.get(activity_id) → NotFoundError se assente
  3. objective = objective_repo.get(activity.objective_id)
  4. Se objective.assignment_id is None:
       → ValidationError (attività appartiene al blueprint, non a un'assegnazione)
  5. assignment = assignment_repo.get(objective.assignment_id)
  6. Verifica il perimetro dell'assegnatario:
     if assignment.assignee_type == GROUP:
       members = [p.id for p in person_repo.get_by_group(assignment.assignee_id)]
       → ValidationError se person_id non è membro
     elif assignment.assignee_type == PERSON:
       → ValidationError se person_id != assignment.assignee_id
  7. activity.assignees.append(person_id)
  8. Se activity.status == UNASSIGNED:
       activity.update_status(Status.ASSIGNED)
  9. activity_repo.save(activity)
  10. Pubblica ActivityAssigned(activity_id, person_id, occurred_at)
  11. Restituisce ActivityDTO
```

#### 2.4.8 BadgeService — propagazione badge

La propagazione badge dipende dal tipo di target. `BadgeService.award_to_assignment()`
e `award_to_activity()` seguono la stessa struttura, con la lista destinatari calcolata
in modo diverso:

```
award_to_assignment(badge_id, assignment_id) → BadgeAwardDTO:
  1. badge_repo.get(badge_id)     → NotFoundError se assente
  2. assignment_repo.get(assignment_id) → NotFoundError se assente
  3. Verifica assignment.status == COMPLETED
     → ValidationError se non completato
  4. Verifica NOT badge_award_repo.exists_for_target("ASSIGNMENT", assignment_id)
     → ValidationError se BadgeAward già esistente per questo target
  5. HookContext(BEFORE_AWARD_BADGE, payload={badge_id, "ASSIGNMENT", assignment_id})
  6. fire(BEFORE_AWARD_BADGE, ctx)

  7. Raccolta destinatari:
     if assignment.assignee_type == GROUP:
       recipients = [p.id for p in person_repo.get_by_group(assignment.assignee_id)]
     elif assignment.assignee_type == PERSON:
       recipients = [assignment.assignee_id]
     else:
       recipients = []   # UNASSIGNED (caso degenere)

  8. Crea BadgeAward(
       badge_id     = badge_id,
       target_type  = "ASSIGNMENT",
       target_id    = assignment_id,
       recipients   = recipients,
       awarded_at   = now()
     )
  9.  badge_award_repo.save(badge_award)
  10. assignment.award_badge(badge_award)   # imposta assignment.badge_award in memoria
  11. assignment_repo.save(assignment)      # persiste la FK badge_award_id
  12. fire(AFTER_AWARD_BADGE, ctx con result=badge_award)
  13. Pubblica BadgeAwarded(badge_award_id, badge_id, "ASSIGNMENT", assignment_id, recipients)
  14. Restituisce BadgeAwardDTO

award_to_activity(badge_id, activity_id) → BadgeAwardDTO:
  # Analogo, con:
  #   target_type  = "ACTIVITY"
  #   recipients   = activity.assignees
  #   activity.badge_award = award   (Activity non ha award_badge(); FK settata direttamente)
  #   activity_repo.save(activity)
  #   Pubblica BadgeAwarded(... "ACTIVITY" ...)
```

**Idempotenza del controllo.** `exists_for_target(type, id)` verifica che non esista
già un `BadgeAward` per lo stesso target; ogni target può ricevere **al massimo un**
`BadgeAward`. Lo stesso `Badge` può però essere assegnato a target diversi senza limiti.

**Snapshot dei destinatari.** I `recipients` vengono fissati al momento della creazione
del `BadgeAward` e salvati nel record. Se i membri di un gruppo cambiano dopo la
propagazione, il `BadgeAward` riflette la composizione del gruppo al momento del conferimento.

#### 2.4.9 DTO — contratto verso i Frontend

I service non restituiscono mai entità di dominio ai frontend. Ogni risposta è
serializzata in DTO prima di attraversare il confine Service→Frontend:

```python
@dataclass
class MissionDTO:
    id:                str
    title:             str
    description:       str
    assignment_policy: dict   # {max_total, max_concurrent} o {unlimited: True}
    objectives:        list[ObjectiveDTO]

@dataclass
class AssignmentDTO:
    id:            str
    mission_id:    str
    assignee_type: Optional[str]
    assignee_id:   Optional[str]
    status:        str
    outcome:       Optional[str]
    objectives:    list[ObjectiveDTO]
    badge_award:   Optional[BadgeAwardDTO]

@dataclass
class ObjectiveDTO:
    id:          str
    description: str
    outcome:     Optional[str]
    activities:  list[ActivityDTO]

@dataclass
class ActivityDTO:
    id:          str
    title:       str
    description: str
    status:      str
    assignees:   list[str]
    badge_award: Optional[BadgeAwardDTO]

@dataclass
class BadgeDTO:
    id:          str
    name:        str
    description: str
    image_url:   Optional[str]

@dataclass
class BadgeAwardDTO:
    id:               str
    badge:            BadgeDTO
    target_type:      str
    target_id:        str
    recipients:       list[str]
    recipients_count: int
    awarded_at:       str

@dataclass
class PersonDTO:
    id:               str
    nicknames:        list[str]
    primary_nickname: str
    acl_level:        int
    acl_groups:       list[str]    # gruppi espliciti, senza il "public" implicito

@dataclass
class AclEntryDTO:
    id:            str
    subject_type:  str             # USER | PUBLIC
    subject_id:    Optional[str]
    resource_type: str
    resource_id:   str             # UUID, "*" (radice di tipo) o "global"
    operation:     str
    permission:    str             # ALLOW | DENY
    level:         Optional[int]
    group:         Optional[str]
    profile_join:  str
    subject_join:  str
```

**Regole di serializzazione:**

- Tutti i campi usano tipi primitivi Python (`str`, `int`, `Optional[str]`); nessun
  value object di dominio attraversa il confine Service→Frontend.
- `outcome` in `AssignmentDTO` e `ObjectiveDTO` è `None` finché non tutte le attività
  figlio hanno raggiunto uno stato terminale; viene popolato on-demand chiamando
  `compute_outcome()` sull'entità di dominio prima della conversione a DTO.
- `BadgeAwardDTO.badge` è un `BadgeDTO` embedded (denormalizzato), non un ID separato,
  per evitare che il frontend debba eseguire una chiamata aggiuntiva per il dettaglio
  del badge.

#### 2.4.10 PersonService

`PersonService` gestisce il ciclo di vita di `Person` e `Group` nel dominio. Dipende da
`PersonRepository`, `GroupRepository` e opzionalmente da `PluginRegistry`.

```
add(nicknames) → PersonDTO:
  1. Valida almeno un nickname non vuoto
  2. person = Person(id=uuid4(), nicknames=nicknames, acl=Profile())
     (profilo di default: livello ANON_SENTINEL, nessun gruppo esplicito —
      la creazione NON accetta un profilo iniziale: anti-escalation, DESIGN §10.11)
  3. person.validate()
  4. person_repo.save(person)
  5. Restituisce PersonDTO

update(id, nicknames?) → PersonDTO:
  1. person_repo.get(id) → NotFoundError se assente
  2. Aggiorna i nicknames se forniti
  3. person.validate(); person_repo.save(person)
  4. Restituisce PersonDTO aggiornato

set_acl_profile(id, acl_level?, acl_groups?) → PersonDTO:
  1. person_repo.get(id) → NotFoundError se assente
  2. Ricostruisce Profile con i campi forniti (None = conserva il valore corrente)
  3. person_repo.save(person)
  (operazione riservata: al confine è protetta da MANAGE_PROFILES su SYSTEM:global)

remove_acl_group(id, group) → PersonDTO:
  1. Toglie la persona dal singolo gruppo ACL (il gruppo universale "public" resta)

remove(id) → None:
  1. person_repo.get(id) → NotFoundError se assente
  2. person_repo.delete(id)
  (non invalida retroattivamente assignment esistenti)

get(id) → PersonDTO:
  1. person_repo.get(id) → NotFoundError se assente
  2. Restituisce PersonDTO

list(filters) → list[PersonDTO]:
  1. person_repo.list(filters)
  2. Restituisce list[PersonDTO]

list_by_group(group_id) → list[PersonDTO]:
  1. person_repo.get_by_group(group_id)
  2. Restituisce list[PersonDTO]

add_group(name?, zone_type?, zone_description?) → GroupDTO:
  1. Se name e zone_type sono entrambi forniti:
       zone = Zone(uuid4(), ZoneType(zone_type), name, zone_description); zone.validate()
     altrimenti zone = None
  2. group = Group(id=uuid4(), zone=zone)
  3. group_repo.save(group)
  4. Restituisce GroupDTO

remove_group(group_id) → None:
  1. group_repo.get(group_id) → NotFoundError se assente
  2. group_repo.delete(group_id)

get_group(group_id) → GroupDTO:
  1. group_repo.get(group_id) → NotFoundError se assente
  2. Restituisce GroupDTO

list_groups() → list[GroupDTO]:
  1. group_repo.list({})
  2. Restituisce list[GroupDTO]

add_group_member(group_id, person_id) → None:
  1. group_repo.exists(group_id) / person_repo.exists(person_id)
     → NotFoundError se gruppo o persona non esistono
  2. group_repo.add_member(group_id, person_id)
     → ValidationError se la membership è duplicata

remove_group_member(group_id, person_id) → None:
  1. group_repo.remove_member(group_id, person_id)
```

`PersonService` è un singleton al pari degli altri service, costruito al bootstrap e
condiviso tra tutte le richieste. In modalità OIDC, `save()` e `delete()` sul
`PersonRepository` concreto chiamano le API admin dell'identity provider.

---

#### 2.4.11 PluginRegistry

`PluginRegistry` mantiene una mappa `HookPoint → list[MissionHook]` e implementa `fire()`:

```
fire(point: HookPoint, context: HookContext) → void:
  1. Recupera la lista dei plugin registrati per point (ordinata per priority DESC).
     Se vuota: ritorna immediatamente senza effetti.
  2. Per ogni plugin:
     a. Se SANDBOXED: passa ScopedHookContext e ignora tutte le mutazioni prodotte.
     b. Se TRUSTED: chiama plugin.execute(context) direttamente.
     c. Se TRUSTED e context.abort == True: interrompe il ciclo.
  3. Se context.abort == True (da un plugin TRUSTED):
     lancia OperationAbortedError(context.abort_reason).

register(hook: MissionHook) → void:
  Per ogni HookPoint in hook.manifest.hooks:
    aggiunge hook alla lista corrispondente.
    Riordina la lista per priority DESC.

unregister(plugin_id: str) → void:
  Rimuove il plugin (per id) da tutte le liste.

list_plugins() → list[PluginManifest]:
  Restituisce tutti i manifest dei plugin registrati (senza duplicati).
```

**Ordine di esecuzione.** I plugin vengono invocati in ordine di `priority` DESC (valore
maggiore = eseguito prima). A parità di priority l'ordine di registrazione è preservato.

**Semantica TRUSTED vs SANDBOXED.** Solo i plugin `TRUSTED` possono abortire un'operazione
(`ctx.abort = True`) e modificare il `HookContext` condiviso. I plugin `SANDBOXED` ricevono
uno `ScopedHookContext` con copia best-effort del payload/result e senza contenuti sensibili
(`content`, `raw_content`, `file_bytes`); tutte le loro mutazioni vengono ignorate, incluso
`abort=True`.

**Semantica AFTER_*.** Gli hook AFTER_* non possono abortire l'operazione: se un hook
lancia un'eccezione durante `fire(AFTER_*, ...)`, l'eccezione viene catturata e loggata,
ma non propagata al chiamante (l'operazione è già completata e persistita).

#### 2.4.12 ExtensionRegistry

`ExtensionRegistry` mantiene le estensioni indicizzate per `manifest.id` e fornisce:

```
register(extension: MissionExtension) → void:
  Se manifest.id già presente: ExtensionConflictError (id duplicato)
  Verifica che ogni route inizi con /extensions/{id}/ e non collida per metodo+path.
  Aggiunge extension al registro.

get(ext_id: str) → Optional[MissionExtension]

list() → list[ExtensionManifest]:
  Restituisce i manifest di tutte le estensioni registrate.
  I frontend chiamano list() una volta al bootstrap per
  decidere quali route/comandi aggiuntivi montare.

execute(ext_id: str, request: ExtensionRequest) → ExtensionResult:
  1. extension = get(ext_id) → NotFoundError se assente
  2. extension.execute(request)
  3. Restituisce ExtensionResult

unregister(ext_id: str) → void
```

#### 2.4.13 ExtensionLoader

`ExtensionLoader` è nel **Layer 3** (`infrastructure/extensions/loader.py`). Riceve i service
applicativi al costruttore (iniettati dal bootstrap) e li passa alle estensioni che istanzia.
Ogni `MissionExtension` concreta riceve nel costruttore i service di cui ha bisogno,
dichiarandoli per nome. Il bootstrap inietta: `mission_svc`, `assignment_svc`,
`activity_svc`, `badge_svc`, `person_svc`, `acl_svc`, `event_publisher` — un'estensione
può quindi orchestrare i flussi esistenti, pubblicare eventi di dominio propri e
consultare/gestire ACL (l'`AclService` resta autoprotetto da `MANAGE_ACL`).

Il loader inietta inoltre `hook_emitter`: un `ExtensionHookEmitter`
(`application/extension_hooks.py`, porta `HookEmitter` in `domain/extensions.py`) legato
all'id verificato del bundle, con cui l'estensione scatena i propri hook point custom
`BEFORE_EXT:<ext_id>:<evento>` / `AFTER_EXT:<ext_id>:<evento>` (DESIGN §15.7).
`fire_before` propaga `OperationAbortedError` se un plugin TRUSTED pone il veto; il
namespace è vincolato all'id dell'estensione e il charset di id/evento esclude `:`.

Il loader lavora con `InstalledManifestRegistry` (`infrastructure/extensions/installed_registry.py`):
carica solo bundle `<scan_dir>/<id>/manifest.json + extension.py`. Prima dell'import legge
`manifest.json`, verifica che l'id sia approvato e confronta sia `manifest_checksum` sia
`code_checksum` con l'entry registrata. In caso di fallimento logga un ERROR e salta quella
sola estensione, senza interrompere il caricamento delle altre né propagare l'eccezione. Se
nessun registro è configurato o il registro è vuoto, non viene caricata alcuna estensione.

> **Nota.** `ExtensionLoadError` (in `shared/errors.py`) fa parte della gerarchia di eccezioni
> ma nel codice corrente **non è mai sollevata**: il percorso di integrità usa
> `ExtensionIntegrityError` e gli errori di istanziazione vengono loggati e ignorati per
> singola estensione. `ExtensionLoadError` è quindi riservata a usi futuri.

```python
class ExtensionLoader:
    def __init__(self, scan_paths: list[str], installed_registry: InstalledManifestRegistry,
                 **services):
        self._scan_paths        = scan_paths
        self._installed         = installed_registry
        self._services          = services   # {mission_svc, assignment_svc, ...}

    def load_all(self) -> list[MissionExtension]:
        extensions = []
        for bundle in self._bundle_dirs():
            manifest = self._read_and_verify_manifest(bundle)
            module = self._import_verified_code(bundle, manifest)
            ext = module.Extension(manifest=manifest, **self._services)
            extensions.append(ext)
        return extensions
```

I service vengono passati come keyword arguments al costruttore di ogni estensione.
Le estensioni dichiarano nel loro `__init__` solo i service di cui hanno effettivamente
bisogno (es. `def __init__(self, mission_svc=None, assignment_svc=None, **_kwargs)`),
ignorando il resto tramite `**_kwargs`.

Gli esempi inclusi nel codice sono bundle completi in `infrastructure/extensions/examples/`
(`mission-stats`, `badge-export`, `assignment-timeline`) e in `infrastructure/plugins/examples/`
(`status-validator`, `badge-notifier`, `notify-on-create`), ciascuno con `manifest.json`,
file Python eseguibile e registry JSON di esempio.

#### 2.4.14 Bootstrap completo

Il bootstrap avviene nel punto di ingresso di ciascun frontend. L'ordine è fisso:
prima si costruiscono i repository (adapter Layer 3), poi i service (Layer 4), poi i
plugin registry e i loader di estensioni, infine il frontend.

```python
# ---- Adapter Layer 3: repository mission/badge (SQLAlchemy) ----
engine          = create_engine(config.database_url)   # postgresql:// o mysql://
session_factory = sessionmaker(bind=engine)
sessions        = SqlAlchemySessionProvider(session_factory)
uow             = SqlAlchemyUnitOfWork(sessions)

mission_repo         = SqlAlchemyMissionRepository(sessions)
assignment_repo      = SqlAlchemyMissionAssignmentRepository(sessions)
objective_repo       = SqlAlchemyObjectiveRepository(sessions)
activity_repo        = SqlAlchemyActivityRepository(sessions)
badge_repo           = SqlAlchemyBadgeRepository(sessions)
badge_award_repo     = SqlAlchemyBadgeAwardRepository(sessions)

# ---- Adapter Layer 3: repository persone e gruppi ----
# Selezionati dalla configurazione: PERSON_BACKEND=local|oidc
if config.person_backend == "local":
    person_repo = SqlAlchemyPersonRepository(sessions)
    group_repo  = SqlAlchemyGroupRepository(sessions)
elif config.person_backend == "oidc":
    person_repo = OidcPersonRepository(
        oidc_url    = config.oidc_url,        # es. https://auth.internal/api/v3
        admin_token = config.oidc_admin_token  # dalla variabile d'ambiente
    )
    group_repo  = OidcGroupRepository(oidc_url=config.oidc_url,
                                      admin_token=config.oidc_admin_token)

# ---- Sistema Auth/ACL (DESIGN §10): ACL come modello Auth + service ACL ----
acl_entry_repo     = SqlAlchemyAclEntryRepository(sessions)
profile_provider   = PersonProfileProvider(person_repo)
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
    seeding_policy=SeedingPolicy(enabled=config.acl_seeding_enabled),
    uow=uow,
)
# Il sistema nasce senza entry e nega tutto: semina le soglie di default
# (una sola volta, su repository vuoto) su SYSTEM:global e radici di tipo.
acl_svc.ensure_bootstrap_entries(
    read_threshold=config.acl_read_threshold,     # default 100
    write_threshold=config.acl_write_threshold,   # default 50
    admin_threshold=config.acl_admin_threshold,   # default 0
)

# ---- EventPublisher e cross-cutting ----
event_publisher  = EventPublisher(sessions, uow)  # transactional outbox
rate_limit       = InMemoryRateLimitPolicy() # infrastructure/security/rate_limit.py
audit_logger     = AuditLogger()             # infrastructure/security/audit_logger.py

# ---- Layer 3: Plugin ----
trust_registry   = PluginTrustRegistry(config.plugin_trust_registry_path)
plugin_registry  = PluginRegistry(trust_registry)
if config.plugins_scan_paths:
    PluginLoader(config.plugins_scan_paths, trust_registry).load_into(plugin_registry)

# ---- Layer 4: Servizi applicativi ----
# plugin_registry, event_publisher e uow vengono iniettati nei costruttori
activity_svc = ActivityService(
    activity_repo=activity_repo,
    objective_repo=objective_repo,
    assignment_repo=assignment_repo,
    person_repo=person_repo,
    group_repo=group_repo,
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
    acl_service=acl_svc,            # seeding + cascata (nessun check ACL)
    plugin_registry=plugin_registry,
    event_publisher=event_publisher,
    uow=uow,
)

mission_svc = MissionService(
    mission_repo=mission_repo,
    acl_service=acl_svc,
    plugin_registry=plugin_registry,
    event_publisher=event_publisher,
    uow=uow,
)

badge_svc = BadgeService(
    badge_repo=badge_repo,
    badge_award_repo=badge_award_repo,
    assignment_repo=assignment_repo,
    activity_repo=activity_repo,
    person_repo=person_repo,
    acl_service=acl_svc,
    plugin_registry=plugin_registry,
    event_publisher=event_publisher,
    uow=uow,
)

person_svc = PersonService(
    person_repo=person_repo,
    group_repo=group_repo,
    uow=uow,
)

# ---- Layer 3: Estensioni ----
installed_registry = InstalledManifestRegistry(config.extension_registry_path)
extension_loader   = ExtensionLoader(
    scan_paths         = config.extensions_scan_paths,
    installed_registry = installed_registry,
    mission_svc        = mission_svc,
    assignment_svc     = assignment_svc,
    activity_svc       = activity_svc,
    badge_svc          = badge_svc,
    person_svc         = person_svc,
)
extensions         = extension_loader.load_all()
extension_registry = ExtensionRegistry()
for ext in extensions:
    extension_registry.register(ext)

# ---- Layer 5: Frontend-specifico ----
# (vedi sezione 2.5)
```

**`BootstrappedSystem`.** Il bootstrap restituisce un dataclass `BootstrappedSystem` con
tutti i componenti assemblati: `mission`, `assignment`, `activity`, `badge`, `person`,
`acl`, `person_repo`, `acl_entry_repo`, `auth_policy`, `auth_service`, `plugin_registry`,
`extension_registry`, `event_publisher`, `rate_limit_policy`, `audit_logger`, `session`,
`uow`.

**`build_system_for_cli()`.** Variante di `build_system()` usata dal bootstrap CLI:
sostituisce `rate_limit_policy` e `audit_logger` con versioni NoOp (`NoOpRateLimitPolicy`,
`NoOpAuditLogger`) poiché la CLI locale non ha bisogno di rate limiting né audit strutturato.

**Transactional outbox.** `EventPublisher.publish()` non esegue handler nel mezzo della
transazione: salva `DomainEvent` in `mm_outbox_events` insieme alla modifica di business.
Ogni consumer registra una consegna idempotente in `mm_outbox_deliveries`. Il consumer
`audit` viene scaricato dopo le richieste REST/CLI; la Web App esegue anche un worker
periodico per il consumer `realtime`, così può ricevere eventi prodotti da processi REST
separati senza condividere memoria.

#### 2.4.15 Autenticazione locale: LocalAuthAdapter

`LocalAuthAdapter` (`infrastructure/auth/local.py`) è l'adapter MissionManager verso il
package top-level `auth`, derivato da `antlampas/Auth`. Espone ancora l'API storica
(`authenticate`, `set_password`, `verify_token`, `revoke_token`) ma delega a
`auth.application.AuthenticationService`, `auth.application.TokenService`,
`auth.infrastructure.security.password.BcryptPasswordHasher` e
`auth.infrastructure.security.token.HmacTokenSigner`.

- **Verifica anti user-enumeration** — gestita dal core `auth`, che usa un hash dummy quando
  account o credenziali non esistono.
- **Password policy** — `PasswordPolicy` locale è solo una facciata verso
  `auth.domain.policies.PasswordPolicy`; l'hashing concreto è `BcryptPasswordHasher`.
- **Account lockout** — `auth.application.AuthenticationService` aggiorna i fallimenti tramite
  la porta `CredentialRepository.record_failure`; l'adapter conserva il messaggio utente
  MissionManager quando l'account risulta bloccato.
- **must_change_password** — impostato da `set_password(..., must_change=True)` (password fissata da
  un amministratore per un altro operatore); azzerato dal cambio self-service.

**Persistenza del conteggio fuori dal rollback (scelta chiave).** L'unità di lavoro
(`uow.transaction()`) fa **rollback su ogni eccezione**; poiché il login fallito registra
l'incremento dei tentativi *e poi solleva* `AuthenticationError`, l'incremento verrebbe annullato
insieme all'eccezione e il lockout non si accumulerebbe mai. Per questo `AuthService.login_local`
**non** è `@transactional`: l'adapter riceve il proprio `uow` e il port
`_CredentialRepositoryAdapter.record_failure()` registra il fallimento in una
**transazione propria che committa** prima che il core `auth` sollevi l'errore. Il reset
dei contatori al login riuscito avviene anch'esso in una transazione propria. È l'unico
caso del sistema in cui un caso d'uso mutante non è avvolto dal `@transactional` del
service, ed è documentato come tale.

**OidcAuthClient.** In modalità OIDC il flusso Authorization Code + PKCE è gestito da
`OidcAuthClient` (PyJWT + `PyJWKClient`). Sono attivi: `leeway=30 s` nella validazione di id/access
token (tolleranza al clock-skew tra app e IdP) e una policy **TLS `verify`** configurabile
(`True` | `False` per lo sviluppo | path a un CA bundle per IdP self-signed), propagata a
discovery, token endpoint e recupero JWKS (via `ssl_context` per `PyJWKClient`).

---

### 2.5 Layer 5 — Frontends

I tre frontend condividono gli stessi service applicativi. L'unica logica presente in
questo layer riguarda la deserializzazione dell'input, il controllo ACL, la serializzazione
dell'output e la mappatura degli errori.

#### 2.5.1 REST API (Quart)

Il frontend REST è costruito con **Quart** in modalità asincrona, come il frontend Web App.
Tutte le route sono `async/await`. Le route sono registrate su un `Blueprint` con prefisso
`/api`, che le separa nettamente dalle route della Web App (che partono dalla root `/`).
Ogni router estende `quart.views.MethodView` e incapsula le route di un'entità.

**Bootstrap (`bootstrap/rest.py` + `frontend/api/app.py`):**

```python
def create_rest_app(config_file=None):
    security = SecurityConfigLoader.load(config_file)
    _validate_rest_oidc_config(security)
    svcs = build_system(config_file)
    identity_provider = RestOperatorIdentityAdapter(...)
    app = RestApp(
        mission_svc=svcs.mission,
        assignment_svc=svcs.assignment,
        activity_svc=svcs.activity,
        badge_svc=svcs.badge,
        person_svc=svcs.person,
        acl_svc=svcs.acl,
        extension_registry=svcs.extension_registry,
        auth_policy=svcs.auth_policy,
        identity_provider=identity_provider,
        auth_service=svcs.auth_service,
    )
    return app.app, svcs
```

`RestApp` registra un `Blueprint` con prefisso `/api`. Le route concrete nel codice
corrente includono:

```python
api.add_url_rule("/missions", methods=["GET", "POST"])
api.add_url_rule("/missions/<uuid:id>", methods=["GET", "DELETE"])
api.add_url_rule("/missions/<uuid:id>/objectives", methods=["GET"])  # blueprint immutabile: niente POST
api.add_url_rule("/missions/<uuid:mission_id>/assignments", methods=["GET", "POST"])

api.add_url_rule("/assignments/<uuid:id>", methods=["GET"])
api.add_url_rule("/assignments/<uuid:id>/assign", methods=["POST"])
api.add_url_rule("/assignments/<uuid:id>/status", methods=["PUT"])
api.add_url_rule("/assignments/<uuid:id>/badge", methods=["POST"])
api.add_url_rule("/assignments/<uuid:id>/objectives", methods=["GET"])

api.add_url_rule("/activities/<uuid:id>", methods=["GET"])
api.add_url_rule("/activities/<uuid:id>/status", methods=["PUT"])
api.add_url_rule("/activities/<uuid:id>/assign", methods=["POST", "DELETE"])
api.add_url_rule("/activities/<uuid:id>/badge", methods=["POST"])

api.add_url_rule("/objectives/<uuid:id>/activities", methods=["GET"])

api.add_url_rule("/badges", methods=["GET", "POST"])
api.add_url_rule("/badges/<uuid:id>", methods=["GET"])

api.add_url_rule("/persons", methods=["GET", "POST"])
api.add_url_rule("/persons/<uuid:id>", methods=["GET", "PUT", "DELETE"])
api.add_url_rule("/persons/<uuid:id>/badges", methods=["GET"])
api.add_url_rule("/persons/<uuid:id>/acl", methods=["PUT"])         # profilo (MANAGE_PROFILES)
api.add_url_rule("/groups", methods=["GET", "POST"])
api.add_url_rule("/groups/<uuid:id>", methods=["GET", "DELETE"])
api.add_url_rule("/groups/<uuid:id>/members", methods=["GET"])

api.add_url_rule("/acl/entries", methods=["GET", "POST"])           # gestione AclEntry
api.add_url_rule("/acl/entries/<entry_id>", methods=["PATCH", "DELETE"])
```

La REST API espone la lettura membri (`GET /groups/<id>/members`); la modifica della membership
dei `Group` di dominio è disponibile nella Web App (`POST`/`DELETE /groups/<id>/members`) e passa
comunque dallo stesso `PersonService.add_group_member()` / `remove_group_member()`.

Le route `/api/auth/*` sono registrate dal router `frontend/api/routers/auth.py`. Tra queste,
`PUT /api/auth/password` è autorizzata **nel router** (il middleware richiede la sola
autenticazione): ognuno può cambiare la propria password (self-service); cambiare quella di
*un altro* operatore richiede `EDIT` sulla sua risorsa `PERSON`, deciso da
`AuthorizationPolicy.is_allowed` — mai leggendo il profilo direttamente. È l'unico confronto
«operatore corrente vs. risorsa» del sistema (DESIGN §10.10). Il cambio *per conto di altri*
passa `must_change=True` a `AuthService.set_password` (cambio forzato al primo accesso, [§2.4.15](#2415-autenticazione-locale-localauthadapter)); il self-service passa `must_change=False`.
La risposta di `POST /api/auth/login` include `must_change_password: <bool>` (da
`AuthService.password_change_required`) così lo SPA può forzare il cambio; l'endpoint di login
**non** blocca l'accesso.

**`AuthMiddleware` (prima di ogni richiesta):**

Il middleware è la tabella di enforcement del confine REST (DESIGN §10.10): la mappa
`_ROUTE_OPERATIONS` associa ogni `(rule Quart, metodo)` a una coppia
`(Operation, ResourceRef)` — risorsa concreta dai view-args, radice di tipo per le
collezioni, `SYSTEM:global` per le creazioni (l'assegnazione si crea sulla missione:
`CREATE_ASSIGNMENT MISSION:<id>`). Le route non mappate (estensioni) ricadono su
`VIEW SYSTEM` (letture) / `EXECUTE SYSTEM` (mutazioni).

```python
_ROUTE_OPERATIONS = {
    ("/api/missions", "GET"):             (Operation.LIST, "MISSION", None),
    ("/api/missions", "POST"):            (Operation.CREATE_MISSION, "SYSTEM", None),
    ("/api/missions/<uuid:id>", "GET"):   (Operation.VIEW, "MISSION", "id"),
    ("/api/missions/<uuid:id>", "DELETE"):(Operation.DELETE, "MISSION", "id"),
    ("/api/missions/<uuid:mission_id>/assignments", "POST"):
                                          (Operation.CREATE_ASSIGNMENT, "MISSION", "mission_id"),
    # ... (una riga per ogni route; vedi frontend/api/middleware.py)
}

class AuthMiddleware:
    def __init__(self, app, identity_provider, auth_policy, rate_limit_policy=None):
        @app.before_request
        async def check_acl():
            if any(request.path.startswith(p) for p in _PUBLIC_PREFIXES):
                return None
            try:
                operator = await asyncio.to_thread(identity_provider.get_current_operator)
            except AuthenticationError:
                operator = None            # profilo anonimo implicito (DESIGN §10.3)
            g.operator = operator

            if any(request.path.startswith(p) for p in _SERVICE_ENFORCED_PREFIXES):
                # /api/acl/* e /api/auth/password: autorizzati da service/router;
                # qui è richiesta la sola autenticazione
                if operator is None:
                    return jsonify({'error': 'Autenticazione richiesta'}), 401, _WWW
                return None

            operation, resource = _resolve_check(request.url_rule.rule,
                                                 request.method, request.view_args)
            allowed = await asyncio.to_thread(
                auth_policy.is_allowed,
                operator.id if operator else None, operation, resource)
            if not allowed:
                if operator is None:
                    return jsonify({'error': 'Autenticazione richiesta'}), 401, _WWW
                return jsonify({'error': 'Accesso negato dalle ACL'}), 403
```

**`ErrorHandler` — mappatura eccezioni → HTTP:**

| Eccezione | HTTP | Corpo risposta |
|---|---|---|
| `ValidationError` | 400 | `{"error": message, "field": ...}` |
| `KeyError` | 400 | `{"error": "Campo obbligatorio mancante nel body: ..."}` |
| `NotFoundError` | 404 | `{"error": message, "resource_type": ..., "resource_id": ...}` |
| `AuthenticationError` | 401 | `{"error": message}` + header `WWW-Authenticate: Bearer` |
| `AuthorizationError` | 403 | `{"error": message}` |
| `ACLError` | 403 | `{"error": message}` |
| `StatusTransitionError` | 409 | `{"error": message, "current": ..., "requested": ...}` |
| `OperationAbortedError` | 422 | `{"error": message}` |
| `MissionManagerError` (base) / `Exception` | 500 | `{"error": ...}` |

**Lettura della richiesta.** I router non duplicano il boilerplate di parsing: usano gli
helper condivisi `parse_json_body()` (body JSON, o `{}` se assente/non valido) e
`operator_id()` (UUID dell'operatore da `g.operator`) da `frontend/_http.py`, e
`require_field(data, "campo")` da `frontend/_utils.py` per i campi obbligatori (solleva
`ValidationError` → 400). Un body assente o un campo mancante produce così un 400 di
dominio uniforme.

**Esempio handler:**

```python
from quart.views import MethodView

from ..._http import operator_id, parse_json_body
from ..._utils import require_field

class MissionRouter(MethodView):
    def __init__(self, svc: MissionService, **kwargs):
        self._svc = svc

    async def get(self, id: UUID = None):
        if id is not None:
            return jsonify(asdict(self._svc.get(str(id)))), 200
        return jsonify([asdict(m) for m in self._svc.list(dict(request.args))]), 200

    async def post(self):
        data = await parse_json_body()
        dto = self._svc.create(
            title=require_field(data, 'title'),
            desc=data.get('description', ''),
            objectives=data.get('objectives', []),
            operator_id=operator_id(),
        )
        return jsonify(asdict(dto)), 201

    async def delete(self, id: UUID):
        self._svc.delete(str(id))
        return '', 204
```

#### 2.5.2 Web App asincrona (Quart)

Il frontend Web App è costruito con **Quart** (equivalente asincrono di Flask). Tutte le
route sono `async/await` per supportare alta concorrenza su I/O senza threading.

**Caratteristica distintiva: `RealtimeNotifier`.** Mantiene un set di connessioni WebSocket
aperte e notifica in broadcast tutti i client connessi quando lo stato di un `MissionAssignment`
o di un'`Activity` cambia. Questo permette a dashboard operative di ricevere aggiornamenti
push senza polling.

```python
class RealtimeNotifier:
    def __init__(self):
        self._connected: set[Connection] = set()

    async def connect(self, conn: Connection) -> None:
        self._connected.add(conn)

    async def disconnect(self, conn: Connection) -> None:
        self._connected.discard(conn)

    async def broadcast(self, event: str, data: dict) -> None:
        for conn in list(self._connected):
            try:
                await conn.send_json({'event': event, 'data': data})
            except Exception:
                self._connected.discard(conn)

    async def on_assignment_status_change(self, assignment_id: UUID, new_status: str):
        await self.broadcast('assignment_status', {
            'assignment_id': str(assignment_id),
            'status': new_status
        })

    async def on_activity_status_change(self, activity_id: UUID, new_status: str):
        await self.broadcast('activity_status', {
            'activity_id': str(activity_id),
            'status': new_status
        })
```

I handler chiamano `RealtimeNotifier` dopo ogni operazione di aggiornamento stato,
come post-processing al di fuori del flusso dei service:

```python
class AssignmentRouteHandler:
    async def update_assignment_status(self, id: UUID):
        data = await parse_json_body()
        dto = self._assignment_svc.update_status(str(id), require_field(data, 'status'))
        await self._notifier.on_assignment_status_change(id, dto.status)
        return jsonify(asdict(dto)), 200
```

**`ACLMiddleware`** è l'equivalente Web di `AuthMiddleware`: la mappa statica
`_WEB_ENDPOINT_ACL` (in `frontend/web/app.py`) associa ogni endpoint Quart a una coppia
`(Operation, tipo risorsa, view-arg)`; i **form di creazione** sono mappati
sull'operazione a cui conducono, così chi non può creare non vede il form.

```python
_WEB_ENDPOINT_ACL = {
    "mission_web.list_missions":   (Operation.LIST, "MISSION", None),
    "mission_web.create_mission":  (Operation.CREATE_MISSION, "SYSTEM", None),
    "mission_web.get_mission":     (Operation.VIEW, "MISSION", "id"),
    "mission_web.acl_management":  (Operation.MANAGE_ACL, "SYSTEM", None),
    "mission_web.set_acl_profile": (Operation.MANAGE_PROFILES, "SYSTEM", None),
    "mission_web.create_acl_entry":  SERVICE_ENFORCED,   # autoprotetta da AclService
    # ... (vedi frontend/web/app.py)
}

class ACLMiddleware:
    def __init__(self, app, identity_provider, auth_policy, endpoint_acl=None, ...):
        @app.before_request
        async def check_acl():
            if any(request.path.startswith(p) for p in public_prefixes):
                return None
            try:
                operator = await asyncio.to_thread(identity_provider.get_current_operator)
            except AuthenticationError:
                operator = None            # profilo anonimo implicito
            g.operator = operator

            check = _resolve_check(request.endpoint, request.view_args)
            if check is SERVICE_ENFORCED:
                return None if operator else _deny(None)
            operation, resource = check
            allowed = await asyncio.to_thread(
                auth_policy.is_allowed,
                operator.id if operator else None, operation, resource)
            if not allowed:
                return _deny(operator)   # redirect /login | 401 | 403
```

Esiti DENIED: redirect a `/login` (anonimo su pagine GET), 401 JSON (anonimo su
mutazioni), 403 JSON (autenticato). Le eventuali entry `PUBLIC` di sola lettura
consentono la navigazione anonima delle pagine corrispondenti.

**Route e comportamenti specifici della Web App.**

- *Primo avvio*: finché non esiste un amministratore (`AuthService.admin_exists`), `/login`
  redirige a `/setup`; `setup_post` invoca `AuthService.create_initial_admin` (ACL **livello 0**,
  il tier amministrativo nella convenzione «più basso = più privilegiato»).
  Il rilevamento dell'admin dipende dal backend: in modalità **locale** basta che esista una
  qualsiasi Person (il database parte vuoto); in modalità **OIDC** deve esistere nell'IdP una
  Person con `acl_level ≤ 0`, perché l'IdP contiene di norma anche utenti non amministratori.
  La creazione è **atomica** lato locale (rollback dell'unità di lavoro se l'impostazione della
  password fallisce, es. password troppo corta, così da non lasciare un account orfano); in
  modalità OIDC creazione utente e password sono delegate all'admin API dell'IdP, e in caso di
  errore dopo la creazione l'utente appena creato viene rimosso dall'IdP come compensazione.
- *Cambio password forzato*: dopo un login riuscito, `login_post` interroga
  `AuthService.password_change_required` e, se `True`, redirige a `/change-password` (portando
  `next`) invece della destinazione richiesta. Le route `change_password_get`/`change_password_post`
  (`frontend/web/handlers/auth.py`, template `change_password.html`) sono **self-service**:
  l'autenticazione è verificata dall'handler leggendo l'operatore dalla sessione, non dal
  middleware ACL — per questo `/change-password` è tra i `_DEFAULT_PUBLIC_PREFIXES` del
  middleware. Il `POST` è comunque soggetto alla validazione CSRF globale (campo `csrf_token`) e
  chiama `AuthService.set_password(..., must_change=False)`, che azzera il flag. In modalità OIDC
  il flag è sempre `False` (nessuna credenziale locale).
- *Creazione da interfaccia*: `GET /missions/new` rende il form; `POST /missions/new` riceve
  JSON (inviato via `fetch` da `static/<tema>/app.js`) e delega al service, restituendo il DTO
  creato. Il form di creazione è l'**unico** punto in cui si definiscono obiettivi e attività: il
  blueprint è immutabile dopo la creazione, quindi non esistono più route/handler/form di aggiunta
  obiettivi (`add_objective` rimosso da tutti i frontend e dal service). La pagina di dettaglio
  della missione mostra **solo il blueprint** in sola lettura, senza form di assegnazione né di
  modifica.
- *Pagina dedicata alle assegnazioni* (scorporata dalla missione): l'assegnazione a persone o
  gruppi vive su route dedicate, gestite da `AssignmentRouteHandler` (a cui è iniettato anche
  `MissionService`):
    - `GET /assignments` (`list_assignments`) — elenco delle **missioni effettivamente
      assegnate** (solo quelle con almeno un `MissionAssignment`); ogni voce di assegnazione
      linka al proprio dettaglio. Costruito iterando le missioni e raccogliendone gli assignment
      via `AssignmentService.list()`.
    - `GET /assignments/new` (`new_assignment_form`) — modulo di creazione (scelta missione +
      assegnatario opzionale); il pulsante «Assegna» della pagina missione vi rimanda con
      `?mission=<id>` per preselezionare la missione.
    - `POST /assignments` (`create_assignment`) — crea l'assegnazione ricevendo `mission_id` nel
      body JSON (la Web App diverge qui dalla REST, che usa `POST /missions/<id>/assignments`);
      `mission_id` mancante → 400 di campo obbligatorio (nessun 500).
  La pagina di dettaglio dell'assignment (`GET /assignments/<id>`) consente inoltre di
  **assegnare ogni attività** a persone *inline*, riusando `POST/DELETE /activities/<id>/assign`:
  i candidati ammessi per attività sono calcolati dal **layer applicativo** —
  `AssignmentService.list_activity_candidates()` applica il perimetro dell'assignment (DESIGN §2.4
  — i membri del gruppo assegnato, o la persona nominale) escludendo chi è già assegnato — mentre
  l'handler si limita a passarli al template. La regola di perimetro non è quindi duplicata nel
  frontend; l'enforcement effettivo resta in `ActivityService.assign_to`.
- *Amministrazione ACL* (`AclRouteHandler`, montato se è disponibile `AclService`): la pagina
  unica `GET /acl` (`acl_management`, gated da `MANAGE_ACL` su `SYSTEM:global`) ha due sezioni.
  **Profili**: assegna livello e gruppi ACL delle persone — `POST /acl/profile`
  (`set_acl_profile`) e `DELETE /acl/profile/groups` (`remove_acl_profile_group`), entrambi
  gated da `MANAGE_PROFILES` su `SYSTEM:global` e delegati a `PersonService.set_acl_profile`
  / `remove_acl_group`; i gruppi ACL restano **derivati** dall'anagrafica (i valori distinti
  di `Profile.groups`), distinti dai `Group` di dominio gestiti sotto `/groups`.
  **Regole (entry)**: elenca tutte le `AclEntry` (incluse le soglie di bootstrap su
  `SYSTEM:global` e radici di tipo) e permette di crearne (`POST /acl/entries` →
  `create_acl_entry`) ed eliminarne (`DELETE /acl/entries/<id>` → `delete_acl_entry`);
  queste route sono `SERVICE_ENFORCED` — l'autorizzazione (MANAGE_ACL sulla risorsa o su
  SYSTEM) è l'autoprotezione di `AclService`, così un creatore delegato dal seeding può
  gestire la propria risorsa. Errori di validazione (INV-1..5) → 400.
- *Mappatura errori*: il blueprint registra error handler che traducono le eccezioni di
  dominio in JSON (`ValidationError`→400, `NotFoundError`→404, `StatusTransitionError`→409,
  `OperationAbortedError`→422), così i form ricevono un messaggio d'errore strutturato.
- *Asset statici*: il blueprint serve `static/<tema>/` sotto `/static`; l'app Quart viene
  creata con `static_folder=None` affinché la route statica di default dell'app non oscuri
  quella del blueprint. Gli asset sono serviti con `Cache-Control: max-age` lungo, quindi gli
  URL di `app.js` e del CSS del tema portano un token di **cache-busting** `?v=<mtime>` (vedi
  `_asset_version()`, iniettato nel contesto template): una modifica a uno di questi file ne
  cambia l'URL e ne forza il re-fetch, evitando che il browser continui a eseguire una versione
  obsoleta di `app.js` dalla cache (gli asset invariati restano comunque in cache).

#### 2.5.3 Web App come Blueprint riusabile

La Web App **non** è un'app Quart monolitica: `create_web_blueprint()` (in
`frontend/web/app.py`) è una **factory che restituisce un `Blueprint` Quart**, montabile su
qualunque applicazione Quart. `bootstrap/web.py:create_web_app()` è solo il *wrapper standalone*
che crea l'app Quart, vi imposta la `secret_key`/sessione e vi registra il blueprint. Sono quindi
supportate due modalità d'uso:

1. **Standalone** — `src.asgi:web_app` (oppure `create_web_app()`): app preconfigurata, pronta per
   l'ASGI server. È il caso d'uso documentato in README §6.
2. **Montata** — l'host crea il proprio `Quart`, costruisce i servizi (`build_system()`) e registra
   il blueprint con `app.register_blueprint(create_web_blueprint(...))`, affiancandolo alle proprie
   route. Vedi README §6.3 per il codice completo.

**Perché la coabitazione è sicura.** Tutti gli hook del frontend sono registrati **sul blueprint**,
non sull'app host, quindi non intercettano le route dell'applicazione ospitante:

- `ACLMiddleware` viene costruito con `ACLMiddleware(bp, …)`: il suo `@app.before_request` è in
  realtà un `bp.before_request` (il parametro `app` riceve il blueprint), perciò il controllo ACL
  gira **solo** sugli endpoint del blueprint.
- Stesso scope per la validazione CSRF (`@bp.before_request`), gli error handler dominio→JSON
  (`@bp.errorhandler`), i security header (`@bp.after_request`) e il context processor dei template.
- Il blueprint espone `bp.notifier` (il `RealtimeNotifier`) come attributo pubblico per l'accesso
  esterno al bus WebSocket.

**Responsabilità dell'host (vincoli da rispettare).** La factory volutamente *non* configura l'app:

- **Secret key e cookie di sessione.** Sessione e CSRF usano `quart.session`: l'host **deve**
  impostare `app.secret_key` (e, per coerenza, `SESSION_COOKIE_HTTPONLY/SAMESITE/SECURE`). La
  factory non lo fa — lo fa solo `create_web_app()` per la modalità standalone.
- **Montaggio alla radice.** Il blueprint va registrato senza `url_prefix`. I percorsi pubblici del
  middleware (`/login`, `/auth/`, `/logout`, `/static/`, `/ws`, `/setup`) sono confrontati come
  **path assoluti** con `request.path` (`middleware.py:_DEFAULT_PUBLIC_PREFIXES`); con un prefisso
  diventerebbero `/<prefix>/login` ecc. e lo skip dell'autenticazione non scatterebbe (login/static/
  setup verrebbero gated → redirect loop). `register_blueprint(bp, url_prefix=...)` **non è quindi
  attualmente supportato**.
- **Route `/static`.** Il blueprint registra la propria static a `static_url_path="/static"`:
  l'app host va creata con `static_folder=None` (o con una static su path diverso), altrimenti la
  regola `/static` di default dell'app oscura quella del blueprint.
- **Template namespace.** Il loader inietta `templates/<tema>/` + `templates/default/` nel
  `jinja_env` **globale** dell'app host (non in uno scope del blueprint): se l'host possiede template
  con gli stessi nomi (`layout.html`, `mission_detail.html`, …) si hanno collisioni.
- **Amministrazione ACL (opzionale).** Se si passa `acl_svc` la factory monta la pagina
  `/acl` (profili + entry); senza, la pagina non esiste ma l'enforcement del middleware
  resta attivo (le entry si amministrano via REST o CLI). Le entry di default sono seminate
  da `build_system()` (`ensure_bootstrap_entries`), non dalla factory.
- **Lifecycle.** Il dispatcher dell'outbox/WebSocket registra hook `before_serving`/`after_serving`
  e un background task **sull'app host** (`state.app`): l'host ne eredita il ciclo di vita.

#### 2.5.4 CLI (Click)

Il frontend CLI è costruito con **Click**. `create_cli_app()` carica la configurazione,
chiama `build_system_for_cli()` (variante con rate-limit e audit NoOp, vedi §2.4.14) e
costruisce un `CliOperatorIdentityAdapter`; `CLIApp` aggrega tutti i sottogruppi di comandi.

```python
def create_cli_app(config_file=None) -> CLIApp:
    cli_config = CliConfigLoader.load(config_file)
    svcs = build_system_for_cli(config_file)
    identity_adapter = CliOperatorIdentityAdapter(
        person_repo=svcs.person_repo,
        operator_id=UUID(cli_config.operator_id) if cli_config.operator_id else None,
        identity_mode=cli_config.identity_mode,
    )
    return CLIApp(
        mission_svc=svcs.mission,
        assignment_svc=svcs.assignment,
        activity_svc=svcs.activity,
        badge_svc=svcs.badge,
        person_svc=svcs.person,
        acl_svc=svcs.acl,
        extension_registry=svcs.extension_registry,
        auth_policy=svcs.auth_policy,
        operator_provider=identity_adapter,
    )

cli.add_command(mission_commands)
cli.add_command(assignment_commands)
cli.add_command(activity_commands)
cli.add_command(badge_commands)
cli.add_command(person_commands)
cli.add_command(acl_commands)
```

**Verifica ACL nei comandi.** Il decorator `require_acl(operation, resource_type?,
resource_param?)` è applicato a tutti i comandi core e mappa il comando su
`(Operation, ResourceRef)` come i middleware degli altri frontend: risorsa concreta
dall'argomento Click indicato (`mission get <mission_id>` → `VIEW MISSION:<id>`), radice
di tipo per gli elenchi (`mission list` → `LIST MISSION:*`), `SYSTEM:global` per le
creazioni (`mission create` → `CREATE_MISSION`). `person set-acl` è gated da
`MANAGE_PROFILES`; i comandi dinamici delle estensioni da `EXECUTE`. In modalità anonima
l'operatore è `None` e vale il profilo anonimo implicito. I comandi `acl *` non portano il
decorator: l'autorizzazione (MANAGE_ACL) è l'autoprotezione di `AclService`. Fa eccezione
`create-superuser`, che non porta il decorator (bootstrap del primo amministratore,
analogo del `/setup` web) e delega la salvaguardia a `AuthService.admin_exists`.

`require_acl` vive in `frontend/cli/_utils.py` (modulo foglia), non in `app.py`: i moduli
dei comandi lo importano da lì, evitando l'import circolare `app` → `commands.*` → `app`.

```python
# frontend/cli/_utils.py
def require_acl(operation, resource_type=None, resource_param=None):
    def decorator(f):
        @wraps(f)
        @click.pass_context
        def wrapper(ctx, *args, **kwargs):
            if resource_type is None:
                resource = SYSTEM_RESOURCE
            elif resource_param is None:
                resource = ResourceRef.type_root(resource_type)
            else:
                resource = ResourceRef(resource_type, UUID(str(kwargs[resource_param])))
            operator = ctx.obj.get("operator")
            auth_policy = ctx.obj["auth_policy"]
            if not auth_policy.is_allowed(
                operator.id if operator else None, operation, resource
            ):
                OutputFormatter.error(f"Accesso negato dalle ACL (operazione {operation.value})")
                raise SystemExit(1)
            return ctx.invoke(f, *args, **kwargs)
        return wrapper
    return decorator
```

**`OutputFormatter`** centralizza la presentazione su stdout:

```python
class OutputFormatter:
    @staticmethod
    def mission_table(missions: list[MissionDTO]) -> str:
        # Tabella ASCII con colonne id, title, obiettivi, assignments
        ...

    @staticmethod
    def assignment_detail(dto: AssignmentDTO) -> str:
        # Dettaglio con status, objectives, badge award
        ...

    @staticmethod
    def badge_award(dto: BadgeAwardDTO) -> str:
        # Visualizzazione badge: nome, target, data, destinatari
        ...

    @staticmethod
    def json_output(data: Any) -> str:
        return json.dumps(data, indent=2, default=str)

    @staticmethod
    def success(msg: str) -> None:
        click.echo(f"✓ {msg}")

    @staticmethod
    def error(msg: str) -> None:
        click.echo(f"✗ {msg}", err=True)
```

**Registrazione dinamica di comandi da estensioni:**

```python
for manifest in services.extensions.list():
    for cmd_spec in manifest.provides_commands:
        @cli.command(name=cmd_spec.name)
        @click.pass_context
        @require_acl(Operation.EXECUTE)
        def ext_command(ctx, _ext_id=manifest.id, **kwargs):
            svc     = ctx.obj['services']
            operator = ctx.obj['operator']
            result  = svc.extensions.execute(
                _ext_id,
                ExtensionRequest(operator_id=operator.id, params=dict(kwargs), body=dict(kwargs))
            )
            OutputFormatter.json_output(result.data)
```

---

## 3. Configurazione

### 3.1 File di configurazione

Il sistema legge la configurazione da un file YAML o TOML. Il path del file è passato
all'avvio oppure risolto dalla variabile d'ambiente `MISSIONMANAGER_CONFIG_FILE`.

**Esempio `config.yaml`:**

```yaml
# Persistenza — database principale (missioni, badge) — SQLAlchemy ORM.
# Supporta PostgreSQL e MySQL tramite il dialetto nella URL.
database:
  url: postgresql+psycopg2://user:pass@localhost/missionmanager
  # oppure: mysql+pymysql://user:pass@localhost/missionmanager
  pool_size: 5
  max_overflow: 10

# Web App e autenticazione locale richiedono MISSIONMANAGER_SECRET_KEY
# (>= 32 caratteri, letta solo da variabile d'ambiente).
web:
  theme: default
  secure_cookies: true

# Sicurezza — umbrella: backend persone, autenticazione, OIDC, identità CLI.
security:
  # Opzione 1: database locale (SQLAlchemy, stesso engine del database principale)
  persons:
    backend: local              # local | oidc
    # Opzione 2: OIDC — Authentik o Keycloak
    # oidc_url: https://auth.internal          # Authentik: /api/v3; Keycloak: /realms/{realm}
    # provider: authentik                       # authentik | keycloak
    # realm: master                             # solo per Keycloak
    # jwks_url: https://auth.internal/application/o/missionmanager/jwks/  # validazione JWT REST/Web
    # audience: missionmanager
    # admin_token: variabile d'ambiente MISSIONMANAGER_OIDC_ADMIN_TOKEN
    # verify_tls: true            # false o ca_bundle per IdP con certificato self-signed
    # ca_bundle: /path/to/ca.pem

  # Autenticazione: local (password + JWT locale) o oidc.
  # auth.backend=oidc senza token admin abilita login OIDC con persone locali.
  # auth.backend=oidc + OIDC_URL + OIDC_ADMIN_TOKEN seleziona il backend persone
  # OIDC e usa l'admin API dell'IdP per persone/gruppi, salvo opt-out esplicito.
  auth:
    backend: local
    token_ttl: 3600
    # Hardening backend locale (login timing-safe + password policy + lockout):
    max_failed_attempts: 5        # <=0 disabilita il lockout
    lockout_duration_seconds: 300
    password:
      min_length: 12              # default restrittivo; riduci esplicitamente se serve
      require_uppercase: true
      require_digit: true
      require_special: true
    # Per backend: oidc:
    # oidc_client_id: missionmanager
    # oidc_client_secret: ...
    # oidc_redirect_uri: https://app.example.com/auth/callback

  # Identità operatore (CLI)
  cli:
    identity_mode: user          # anonymous | user
    # operator_id: preferire MISSIONMANAGER_OPERATOR_ID negli ambienti reali.

# Sistema ACL — soglie di bootstrap e seeding (DESIGN §10.8)
# Convenzione: livello più basso = più privilegiato; una soglia L è
# soddisfatta da chi ha livello <= L. Usate SOLO per seminare le entry di
# default al primo avvio (repository vuoto); poi si amministrano come entry.
acl:
  read_threshold:  100   # lettura (VIEW/LIST)
  write_threshold: 50    # mutazioni operative (Gestore)
  admin_threshold: 0     # identità, profili e MANAGE_ACL (Amministratore)
  seeding_enabled: true  # entry MANAGE_ACL del creatore alla creazione risorse

# Plugin
plugins:
  scan_paths:
    - /var/lib/missionmanager/plugins
  # trust_registry_path: /etc/missionmanager/plugin_trust.json

# Estensioni
extensions:
  scan_paths:
    - /var/lib/missionmanager/extensions
  # installed_registry_path: /etc/missionmanager/extensions.json
```

### 3.2 Variabili d'ambiente

Le variabili d'ambiente hanno priorità sul file di configurazione:

| Variabile | Effetto |
|---|---|
| `MISSIONMANAGER_CONFIG_FILE` | Path del file di configurazione |
| `MISSIONMANAGER_OPERATOR_ID` | UUID dell'operatore per la CLI |
| `MISSIONMANAGER_CLI_IDENTITY_MODE` | `anonymous` \| `user` |
| `MISSIONMANAGER_DATABASE_URL` | SQLAlchemy URL (postgresql+psycopg2:// o mysql+pymysql://) |
| `MISSIONMANAGER_PERSON_BACKEND` | `local` \| `oidc` |
| `MISSIONMANAGER_OIDC_URL` | URL base dell'identity provider OIDC (Authentik/Keycloak) |
| `MISSIONMANAGER_OIDC_ADMIN_TOKEN` | Token admin OIDC per operazioni di write su Person/Group; con `auth_backend=oidc` e `OIDC_URL` abilita il backend persone OIDC salvo opt-out esplicito |
| `MISSIONMANAGER_OIDC_JWKS_URL` | URL JWKS per la validazione dei JWT (REST/Web) |
| `MISSIONMANAGER_AUTH_BACKEND` | `local` \| `oidc` |
| `MISSIONMANAGER_LOCAL_TOKEN_TTL` | Durata in secondi dei JWT locali |
| `MISSIONMANAGER_OIDC_CLIENT_ID` | Client ID OIDC per Authorization Code + PKCE |
| `MISSIONMANAGER_OIDC_CLIENT_SECRET` | Client secret OIDC opzionale |
| `MISSIONMANAGER_OIDC_REDIRECT_URI` | Redirect URI OIDC |
| `MISSIONMANAGER_SECRET_KEY` | Chiave segreta per JWT locali e sessioni Web |
| `MISSIONMANAGER_PLUGINS_SCAN_PATHS` | Percorsi plugin separati da `:` |
| `MISSIONMANAGER_PLUGINS_TRUST_REGISTRY` | Registro JSON dei trust level plugin |
| `MISSIONMANAGER_EXTENSIONS_SCAN_PATHS` | Percorsi estensioni separati da `:` |
| `MISSIONMANAGER_EXTENSIONS_INSTALLED_REGISTRY` | Registro JSON delle estensioni approvate e dei checksum |
| `MISSIONMANAGER_ACL_READ_THRESHOLD` | Soglia di bootstrap per le entry di lettura (default 100) |
| `MISSIONMANAGER_ACL_WRITE_THRESHOLD` | Soglia di bootstrap per le entry delle mutazioni operative (default 50) |
| `MISSIONMANAGER_ACL_ADMIN_THRESHOLD` | Soglia di bootstrap per identità, profili e MANAGE_ACL (default 0) |
| `MISSIONMANAGER_ACL_SEEDING_ENABLED` | Abilita il seeding automatico del creatore (default `true`) |
| `MISSIONMANAGER_OIDC_ISSUER` | URL issuer OIDC per validazione JWT (REST/Web) |
| `MISSIONMANAGER_OIDC_AUDIENCE` | Audience attesa nel JWT OIDC |
| `MISSIONMANAGER_OIDC_PROVIDER` | `authentik` \| `keycloak` |
| `MISSIONMANAGER_OIDC_REALM` | Realm Keycloak (obbligatorio con `security.persons.backend=oidc`) |
| `MISSIONMANAGER_OIDC_VERIFY_TLS` | Verifica TLS verso l'IdP OIDC (default `true`; `false` solo per sviluppo) |
| `MISSIONMANAGER_OIDC_CA_BUNDLE` | Path a un CA bundle custom per IdP con certificato self-signed (ha precedenza su `verify_tls`) |
| `MISSIONMANAGER_PASSWORD_MIN_LENGTH` | Lunghezza minima password locale (default `8`) |
| `MISSIONMANAGER_PASSWORD_REQUIRE_UPPERCASE` | Richiede una maiuscola nella password locale (default `false`) |
| `MISSIONMANAGER_PASSWORD_REQUIRE_DIGIT` | Richiede una cifra nella password locale (default `false`) |
| `MISSIONMANAGER_PASSWORD_REQUIRE_SPECIAL` | Richiede un carattere speciale nella password locale (default `false`) |
| `MISSIONMANAGER_MAX_FAILED_ATTEMPTS` | Tentativi di login falliti prima del blocco account (default `5`; `<=0` disabilita) |
| `MISSIONMANAGER_LOCKOUT_DURATION_SECONDS` | Durata del blocco account dopo troppi fallimenti (default `300`) |
| `MISSIONMANAGER_REST_DEV_MODE` | `true` abilita il solo fallback di sviluppo `X-Operator-Id` se non è configurato un auth backend |
| `MISSIONMANAGER_WEB_THEME` | Nome del tema CSS della Web App (default: `default`) |
| `MISSIONMANAGER_WEB_SECURE_COOKIES` | Marca il cookie di sessione Web App come `Secure` (HTTPS-only). Default `true`; impostare a `false` per servire la Web App in locale su HTTP, altrimenti il browser scarta il cookie e login/setup falliscono con errore CSRF |
| `MISSIONMANAGER_REDIS_URL` | URL Redis opzionale per distribuire le notifiche realtime WebSocket tra processi |
| `MISSIONMANAGER_REDIS_PREFIX` | Prefisso Redis per canali/chiavi realtime (default: `missionmanager`) |

**Priorità:** variabili d'ambiente > file di configurazione > default.

### 3.3 Identità operatore CLI

```
CliConfig
  identity_mode    : str        # "anonymous" | "user"
  operator_id      : str | None # obbligatorio se identity_mode == "user"; parsato a UUID al bootstrap
```

Se `identity_mode == "user"` ma `operator_id` non è impostato: errore di configurazione
al bootstrap. Se `operator_id` è valorizzato ma l'ID non esiste nel `PersonRepository`:
`PersonRepository.get()` solleva `NotFoundError` e il CLI termina con exit 1.

Nel codice corrente `operator_id` può arrivare sia dal file di configurazione (`security.cli.operator_id`)
sia dalla variabile d'ambiente `MISSIONMANAGER_OPERATOR_ID`; per ambienti reali è preferibile
la variabile d'ambiente, così l'identificatore operativo non resta nel file versionato.

### 3.4 Backend per persone e gruppi

Il sistema supporta due backend intercambiabili, selezionati dalla chiave `security.persons.backend`
(o dalla variabile d'ambiente `MISSIONMANAGER_PERSON_BACKEND`):

**`local`**: `SqlAlchemy{Person,Group}Repository` persistono `Person` e `Group` nelle stesse
tabelle del database operativo (PostgreSQL o MySQL). `PersonService.add/update/remove()` agiscono
direttamente sul database. Con `security.auth.backend=local`, `LocalAuthAdapter` usa il
package `auth` per password bcrypt e token HMAC/JWT HS256 firmati con
`MISSIONMANAGER_SECRET_KEY`, adattando `Person`/`CredentialRow` ai concetti `Account` e
`LocalCredential` del core esterno.

**`oidc`**: `Oidc{Person,Group}Repository` delegano le operazioni alle API dell'identity
provider configurato:

- **Authentik** (`provider: authentik`): API REST sotto `/api/v3/core/users/` e
  `/api/v3/core/groups/`. `PersonService.add()` crea l'utente tramite POST all'API admin;
  `get_by_group()` usa l'endpoint dei membri del gruppo.
- **Keycloak** (`provider: keycloak`): API REST sotto `/admin/realms/{realm}/users/` e
  `/admin/realms/{realm}/groups/`. La stessa logica si applica con endpoint adattati.

In modalità OIDC, `RestOperatorIdentityAdapter` valida il JWT Bearer token presentato
nella richiesta HTTP tramite il JWKS endpoint dell'identity provider (`jwks_url`). Per
`security.auth.backend=oidc` la REST API richiede **sia** `oidc_jwks_url` (verifica della firma)
**sia** `oidc_audience` (verifica del claim `aud`): in mancanza, il bootstrap REST fallisce
con un messaggio esplicito invece di restituire 401 opachi a runtime. L'`iss` è verificato
quando `oidc_issuer` è impostato (obbligatorio per `security.auth.backend=oidc`). Per Keycloak
`security.persons.realm` (o `MISSIONMANAGER_OIDC_REALM`) è obbligatorio; il bootstrap costruisce
l'endpoint `/admin/realms/{realm}`. La gestione utenti è **non ibrida**: `security.persons.backend` e
`security.auth.backend` possono divergere solo nel caso `persons=local` e `auth=oidc`:
è il profilo in cui OIDC autentica, mentre persone e gruppi restano locali e il login non
richiede admin API dell'IdP. Quando `auth=oidc` e sono presenti `OIDC_URL` e
`OIDC_ADMIN_TOKEN`, il loader seleziona automaticamente `persons=oidc` per la modalità
OIDC completa (gestione utenti/gruppi sull'IdP), salvo `MISSIONMANAGER_PERSON_BACKEND=local`
impostato esplicitamente. La combinazione inversa (`persons=oidc`, `auth=local`) viene
rifiutata durante il caricamento della configurazione (`SecurityConfigLoader`).

**Mappatura del subject (`sub` ↔ id admin).** I binding in `mm_external_identities` sono
sempre indicizzati in base al *path-id* usato dall'admin API (`pk` per Authentik, `id` per Keycloak).
Il claim `sub` del token coincide con quel path-id solo in alcune configurazioni: Keycloak usa
l'UUID utente sia come `sub` sia come id admin; Authentik invece, a seconda del *Subject mode*
del provider, può emettere un `sub` diverso (uuid utente, username, …). Per evitare binding
incoerenti tra login e letture, `security.persons.subject_field` (env `MISSIONMANAGER_OIDC_SUBJECT_FIELD`)
indica a quale campo utente corrisponde il `sub`: se impostato e diverso dal path-id,
`OidcPersonRepository.resolve_external_subject` traduce il `sub` nel path-id interrogando l'IdP
(`GET /users/?<field>=<sub>`). Se non impostato, si assume `sub == path-id` (Keycloak, oppure
Authentik con Subject mode "Based on the User's ID").

Il `Profile` ACL è ricavato dall'utente OIDC: un attributo `acl_level` (intero, più
basso = più privilegiato) e/o `acl_groups` (lista di stringhe, o stringa CSV). Sono usati
due percorsi complementari:
- **Claim del token (REST, ottimizzazione):** se il token validato porta
  `acl_level`/`acl_groups`, `RestOperatorIdentityAdapter` costruisce l'operatore
  direttamente dai claim, **senza** interrogare l'admin API a ogni richiesta. Richiede un
  mapper lato IdP che includa il profilo nel token.
- **Admin API (fallback e Web App):** in assenza di claim, l'operatore è materializzato con
  `OidcPersonRepository.get`, che legge gli attributi utente. Per ridurre i round-trip, `get`
  ha una **cache in-memory a TTL breve** (`security.persons.cache_ttl`, default 30s; ≤ 0 disabilita),
  invalidata su `save`/`delete`. La configurazione del mapping attributi è responsabilità del
  sistemista lato IdP; un utente OIDC senza attributi riceve il profilo meno privilegiato
  (*deny-by-default*, evento loggato a livello INFO per diagnosi).

**Flusso OIDC stateless.** Sia la Web App sia la SPA/REST usano `AuthService.begin_oidc_flow`
(PKCE), che restituisce `{ url, state, nonce, code_verifier }` **senza** mantenere stato nel
processo. La Web App conserva `state`/`nonce`/`code_verifier` nella **sessione Quart firmata** e
li rimanda a `complete_oidc_flow` al callback; la SPA li conserva lato client. Questo elimina lo
stato in-memory condiviso e rende il login OIDC corretto con deployment **multi-worker** e dopo
i riavvii di processo. L'ID token è validato verificando firma, `aud == client_id`, `nonce`
(anti-replay) e `iss` (issuer della discovery). Il logout OIDC è solo lato client (pulizia
sessione / scarto token): gli access token sono JWT stateless e restano validi fino a scadenza,
salvo usare il revocation/end-session endpoint dell'IdP.

**Primo avvio in modalità OIDC.** Il flusso di bootstrap dell'amministratore è equivalente
a quello locale ma delegato all'IdP. `AuthService.admin_exists` interroga l'IdP e considera
inizializzato il sistema se esiste almeno una Person con `acl_level ≤ 0` (il tier
amministrativo; l'IdP contiene di norma anche utenti non amministratori, quindi non basta
"esiste un utente"). In assenza di un amministratore, `AuthService.create_initial_admin`
crea l'utente tramite la admin API dell'IdP (POST utenti con `acl_level=0`) e ne imposta la password
(`OidcPersonRepository.set_password`: `set_password/` su Authentik, `reset-password` su
Keycloak). I due entry point sono `/setup` (Web) e `person create-superuser` (CLI). Se
l'impostazione della password fallisce, l'utente appena creato viene rimosso dall'IdP per
compensazione.

---

## 4. Diagrammi di riferimento

I diagrammi di implementazione si trovano in `diagrams/` (questa directory).
I diagrammi architetturali generali si trovano in `../design/diagrams/`.

### Diagrammi di classe — Implementazione

| File | Contenuto |
|---|---|
| `diagrams/class/class_domain.puml` | Entità di dominio con campi Python, value objects (`AssignmentPolicy`, `Profile`), `Status` come enum comportamentale, `Person`/`Group`/`Zone` come entità di dominio, gerarchie di relazione |
| `diagrams/class/class_acl.puml` | Sistema ACL completo: `AclEntry` (INV-1..5, `matches`), `Profile`, `SubjectRef`/`ResourceRef`, `Operation`/`Permission`/`JoinOp`, porte (`AclEntryRepository`, `ProfileProvider`, `ResourceHierarchyProvider`), `AuthorizationPolicy`, `AclService`+`SeedingPolicy`, adapter concreti |
| `diagrams/class/class_exceptions.puml` | Gerarchia delle eccezioni da `MissionManagerError`: `ValidationError`, `NotFoundError`, `ACLError`, `StatusTransitionError`, `OperationAbortedError` con codici HTTP e codici di uscita CLI |
| `diagrams/class/class_ports.puml` | Tutti i contratti del Layer 2 come `typing.Protocol`: `BaseRepository[T]`, tutti i `*Repository` con query semantiche complete (inclusi `PersonRepository`, `GroupRepository`, `AclEntryRepository`), `CredentialRepository` + `LocalCredential`, `ProfileProvider`, `ResourceHierarchyProvider`, `OperatorIdentityProvider`, `MissionHook`, `MissionExtension` |
| `diagrams/class/class_auth.puml` | Sottosistema di autenticazione: `AuthService` (orchestrazione locale/OIDC), `LocalAuthAdapter` + `PasswordPolicy`, `OidcAuthClient` (leeway + TLS verify), porta `CredentialRepository` + `LocalCredential` + `SqlAlchemyCredentialRepository`; nota sulle quattro proprietà di sicurezza (timing-safe, policy, lockout, must_change) e sul login non `@transactional` |
| `diagrams/class/class_adapters.puml` | Classi base astratte del Layer 3: `RepositoryAdapter[T]`, `PersonRepositoryAdapter`/`GroupRepositoryAdapter` (con nota su backend SQLAlchemy vs OIDC), `OperatorIdentityAdapter`, `MissionHookAdapter` |
| `diagrams/class/class_services.puml` | Tutti i service con dipendenze complete (inclusi `PersonService` e `AclService`) + `AuthorizationPolicy` + `PluginRegistry` + DTOs completi (inclusi `PersonDTO`, `GroupDTO`, `AclEntryDTO`); note su `plugin_registry` opzionale e auto-cascade |
| `diagrams/class/class_extension_system.puml` | `ExtensionRegistry`, `ExtensionLoader`, `InstalledManifestRegistry`, bundle verificati e esempi `mission-stats`, `badge-export`, `assignment-timeline` |
| `diagrams/class/class_event_outbox.puml` | `SqlAlchemyUnitOfWork`, transactional outbox, consumer `audit` e `realtime` idempotenti |
| `diagrams/class/class_frontend_rest.puml` | `RestApp`, `AuthMiddleware` (mappa route → Operation/ResourceRef), `ErrorHandler`, tutti i Router (Quart MethodView, route sotto `/api`), inclusi `PersonRouter` e i router ACL; note sulla registrazione dinamica route estensioni |
| `diagrams/class/class_frontend_web_cli.puml` | `create_web_blueprint` (factory del blueprint Web), `ACLMiddleware` (mappa endpoint → Operation/ResourceRef), `RealtimeNotifier`, tutti i RouteHandler (Quart, incluso `AclRouteHandler`); `CLIApp`, `OutputFormatter`, tutti i Command groups (Click) inclusi `PersonCommands` e `AclCommands`; decorator `require_acl` |

### Diagrammi di attività — Services

| File | Contenuto |
|---|---|
| `diagrams/activity/activity_service_pattern.puml` | Pattern generale dei service MissionManager: validazione → verifica policy/esistenza → plugin BEFORE → operazione → plugin AFTER → DTO; l'ACL vive nel middleware, non nei service |
| `diagrams/activity/activity_acl_evaluation.puml` | `AuthorizationPolicy.is_allowed()`: adapter MissionManager → `auth.application.AuthorizationService` → modello ACL registrato, risoluzione profilo (anonimo implicito), entry proprie → match → precedenza DENY>ALLOW>DENIED, deny ereditato dai padri, MANAGE_ACL non ereditabile |
| `diagrams/activity/activity_create_mission.puml` | `MissionService.create()`: validazione struttura (≥1 obiettivo, ≥1 attività per obiettivo), costruzione `Mission` con cloni `Objective`+`Activity`, hook BEFORE/AFTER, `MissionDTO` |
| `diagrams/activity/activity_create_assignment.puml` | `AssignmentService.create()`: verifica `AssignmentPolicy` (`max_total`, `max_concurrent`), validazione assegnatario via `PersonRepository.exists()` / `GroupRepository.exists()`, replicazione blueprint, stato iniziale `ASSIGNED`/`UNASSIGNED` |
| `diagrams/activity/activity_update_status.puml` | `ActivityService.update_status()`: `can_transition_to()`, verifica ≥1 assegnatario per `IN_PROGRESS`, auto-cascade al `MissionAssignment` padre (`IN_PROGRESS` all'avvio, `FAILED` al fallimento); atomicità delle scritture e dell'outbox |
| `diagrams/activity/activity_award_badge.puml` | `BadgeService.award_to_assignment()` / `award_to_activity()`: verifica `COMPLETED`, verifica unicità (`exists_for_target`), calcolo destinatari per tipo (`GROUP`→`PersonRepository.get_by_group()`, `PERSON`→diretto, `ACTIVITY`→`assignees`), snapshot recipients |
| `diagrams/activity/activity_status_machine.puml` | `Status.can_transition_to()` e `is_terminal()`: grafo delle transizioni consentite, implementazione come `_TRANSITIONS` dict nell'enum, pattern di uso nei service |
| `diagrams/activity/activity_plugin_fire.puml` | `PluginRegistry.fire()`: trust effettivo via `PluginTrustRegistry`, ordine per priority DESC, `ScopedHookContext` per sandbox, abort propagato solo da plugin TRUSTED, eccezioni AFTER_* loggate |
| `diagrams/activity/activity_extension_loader.puml` | `ExtensionLoader.load_all()`: discovery dei bundle `id/manifest.json + extension.py`, verifica `manifest_checksum` e `code_checksum`, costruzione con service iniettati, dispatch `ExtensionRegistry.execute()` |

### Diagrammi di sequenza — Flussi chiave

| File | Contenuto |
|---|---|
| `diagrams/sequence/sequence_create_assignment.puml` | Sequenza completa di `AssignmentService.create()`: `MissionRepository.get()`, verifica `AssignmentPolicy`, `PersonRepository.exists()` / `GroupRepository.exists()`, `PluginRegistry.fire(BEFORE_CREATE_ASSIGNMENT)`, replicazione blueprint, `MissionAssignmentRepository.save()`, `fire(AFTER_CREATE_ASSIGNMENT)`, `AssignmentDTO` |
| `diagrams/sequence/sequence_update_status.puml` | Sequenza di `ActivityService.update_status()` con auto-cascade: `ActivityRepository.get()`, `can_transition_to()`, `fire(BEFORE_UPDATE_STATUS)`, `ActivityRepository.save()`, fetch `ObjectiveRepository` + `MissionAssignmentRepository`, aggiornamento condizionale assignment padre, `fire(AFTER_UPDATE_STATUS)` |
| `diagrams/sequence/sequence_award_badge.puml` | Sequenza di `BadgeService.award_to_assignment()` con propagazione gruppo: `BadgeRepository.get()`, `MissionAssignmentRepository.get()`, verifica `COMPLETED`, `exists_for_target()`, `fire(BEFORE_AWARD_BADGE)`, `PersonRepository.get_by_group()`, costruzione `BadgeAward` con recipients, `BadgeAwardRepository.save()`, `fire(AFTER_AWARD_BADGE)` |
| `diagrams/sequence/sequence_plugin_fire.puml` | Dettaglio di `PluginRegistry.fire()`: tre scenari — hook BEFORE con abort (`ExternalSyncHook` imposta `abort=True`), BEFORE senza abort, AFTER con eccezione catturata e non propagata |
| `diagrams/sequence/sequence_extension_execute.puml` | `ExtensionRegistry.execute()` con lookup per `manifest.id`, costruzione `ExtensionRequest` con `operator_id`, chiamata `extension.execute(request)`, estensione con service iniettati nel costruttore, `ExtensionResult` restituito al frontend |
| `diagrams/sequence/sequence_bootstrap_rest.puml` | Bootstrap completo REST API: adapter Layer 3 (SQLAlchemy + Person/Group backend selezionato) → service Layer 4 (incluso `PersonService`) → `PluginRegistry` → `ExtensionLoader` → `ExtensionRegistry` → `RestApp` → `AuthMiddleware`; registrazione dinamica route e `PersonRouter` |
| `diagrams/sequence/sequence_bootstrap_cli.puml` | Bootstrap CLI: `ConcretePersonRepository` (local/OIDC) → sistema ACL → tutti i service → `CliOperatorIdentityAdapter` (usa `PersonRepository.get()`) → `CLIApp` con `PersonCommands`, `AclCommands` e `require_acl`; verifica `operator_id` al bootstrap |
| `diagrams/sequence/sequence_acl_decision.puml` | Enforcement al confine: middleware → facciata `AuthorizationPolicy` → `auth.application.AuthorizationService` → modello ACL registrato → `ProfileProvider` → `AclEntryRepository.entries_for` → `ResourceHierarchyProvider.parents_of` → esito 401/403/redirect o prosecuzione |
| `diagrams/sequence/sequence_local_login.puml` | Login locale in `LocalAuthAdapter`: adapter `Person`/`CredentialRow` → `auth.application.AuthenticationService`, fallimenti in transazione propria, lockout, emissione token tramite `auth.application.TokenService`, e `password_change_required` per il cambio forzato (`must_change_password`) |

Per la documentazione architetturale completa — dominio, regole di business, layer,
ACL, flussi operativi, plugin, estensioni — vedere `../design/DESIGN.md`.
