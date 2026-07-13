<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

# Mission Manager — Documentazione Architetturale

Questo documento descrive l'architettura di MissionManager: il modello del dominio, le regole di business, l'organizzazione a strati, i flussi operativi chiave e i meccanismi di estendibilità.

## Indice

1. [Panoramica del sistema](#1-panoramica-del-sistema)
2. [Modello del dominio: Missioni, Attività e Badge](#2-modello-del-dominio-missioni-attività-e-badge)
   - 2.1 [Mission (Blueprint di missione)](#21-mission-blueprint-di-missione)
   - 2.2 [AssignmentPolicy (Policy di assegnazione)](#22-assignmentpolicy-policy-di-assegnazione)
   - 2.3 [MissionAssignment (Esecuzione di una missione)](#23-missionassignment-esecuzione-di-una-missione)
   - 2.4 [Objective (Obiettivo)](#24-objective-obiettivo)
   - 2.5 [Activity (Attività)](#25-activity-attività)
   - 2.6 [Badge (Definizione di riconoscimento)](#26-badge-definizione-di-riconoscimento)
   - 2.7 [BadgeAward (Assegnazione di riconoscimento)](#27-badgeaward-assegnazione-di-riconoscimento)
   - 2.8 [Status — macchina a stati](#28-status--macchina-a-stati)
   - 2.9 [Esiti derivati](#29-esiti-derivati)
3. [Persone, Gruppi e Zone nel dominio](#3-persone-gruppi-e-zone-nel-dominio)
   - 3.1 [Person (Persona)](#31-person-persona)
   - 3.2 [Profile (Profilo di controllo accessi)](#32-profile-profilo-di-controllo-accessi)
   - 3.3 [Group (Gruppo)](#33-group-gruppo)
   - 3.4 [Zone (Zona)](#34-zone-zona)
4. [Regole di business e attori](#4-regole-di-business-e-attori)
   - 4.1 [Regole di business fondamentali](#41-regole-di-business-fondamentali)
   - 4.2 [Attori e ruoli](#42-attori-e-ruoli)
5. [Architettura a strati](#5-architettura-a-strati)
   - 5.1 [I cinque layer](#51-i-cinque-layer)
   - 5.2 [Direzione delle dipendenze](#52-direzione-delle-dipendenze)
6. [Livello Domain](#6-livello-domain)
   - 6.1 [Categorie di oggetti del dominio](#61-categorie-di-oggetti-del-dominio)
   - 6.2 [Entità](#62-entità)
   - 6.3 [Value Object](#63-value-object)
   - 6.4 [Enumerazioni](#64-enumerazioni)
   - 6.5 [Policy di dominio](#65-policy-di-dominio)
   - 6.6 [Eventi di dominio](#66-eventi-di-dominio)
   - 6.7 [Eccezioni di dominio](#67-eccezioni-di-dominio)
   - 6.8 [Principi invarianti del livello](#68-principi-invarianti-del-livello)
7. [Livello Repository e Porte](#7-livello-repository-e-porte)
   - 7.1 [Repository locali (contratti)](#71-repository-locali-contratti)
   - 7.2 [PersonRepository e GroupRepository](#72-personrepository-e-grouprepository)
   - 7.3 [OperatorIdentityProvider](#73-operatoridentityprovider)
   - 7.4 [Adapter](#74-adapter)
8. [Livello Service](#8-livello-service)
   - 8.1 [MissionService](#81-missionservice)
   - 8.2 [AssignmentService](#82-assignmentservice)
   - 8.3 [ActivityService](#83-activityservice)
   - 8.4 [BadgeService](#84-badgeservice)
   - 8.5 [PersonService](#85-personservice)
   - 8.6 [DTO (Data Transfer Objects)](#86-dto-data-transfer-objects)
9. [Livello Frontend](#9-livello-frontend)
   - 9.1 [REST API JSON](#91-rest-api-json)
   - 9.2 [Web App asincrona](#92-web-app-asincrona)
   - 9.3 [Interfaccia a riga di comando (CLI)](#93-interfaccia-a-riga-di-comando-cli)
   - 9.4 [Autenticazione e verifica delle credenziali](#94-autenticazione-e-verifica-delle-credenziali)
10. [Sistema ACL e autorizzazione](#10-sistema-acl-e-autorizzazione)
    - 10.1 [Principi e decisioni](#101-principi-e-decisioni)
    - 10.2 [Modello concettuale](#102-modello-concettuale)
    - 10.3 [Profilo del richiedente e profilo anonimo](#103-profilo-del-richiedente-e-profilo-anonimo)
    - 10.4 [Invarianti strutturali](#104-invarianti-strutturali)
    - 10.5 [Semantica di valutazione](#105-semantica-di-valutazione)
    - 10.6 [Gerarchia delle risorse e ambiti](#106-gerarchia-delle-risorse-e-ambiti)
    - 10.7 [Seeding automatico (assenza di ownership)](#107-seeding-automatico-assenza-di-ownership)
    - 10.8 [Bootstrap e soglie di default](#108-bootstrap-e-soglie-di-default)
    - 10.9 [Architettura: porte, policy, service](#109-architettura-porte-policy-service)
    - 10.10 [Enforcement al confine per frontend](#1010-enforcement-al-confine-per-frontend)
    - 10.11 [Gestione delle ACL e prevenzione dell'escalation](#1011-gestione-delle-acl-e-prevenzione-dellescalation)
    - 10.12 [Riepilogo autorizzazioni per operazione](#1012-riepilogo-autorizzazioni-per-operazione)
    - 10.13 [ACLError e mappatura](#1013-aclerror-e-mappatura)
11. [Flussi operativi chiave](#11-flussi-operativi-chiave)
    - 11.1 [Creazione di una missione (blueprint)](#111-creazione-di-una-missione-blueprint)
    - 11.2 [Creazione di un MissionAssignment](#112-creazione-di-un-missionassignment)
    - 11.3 [Aggiornamento di stato](#113-aggiornamento-di-stato)
    - 11.4 [Creazione di un BadgeAward al completamento](#114-creazione-di-un-badgeaward-al-completamento)
12. [Scelte architetturali](#12-scelte-architetturali)
    - 12.1 [Repository Pattern con interfacce esplicite](#121-repository-pattern-con-interfacce-esplicite)
    - 12.2 [Tre frontend intercambiabili](#122-tre-frontend-intercambiabili)
    - 12.3 [ACL al confine del sistema, non nelle entità di dominio](#123-acl-al-confine-del-sistema-non-nelle-entità-di-dominio)
    - 12.4 [Status come enum comportamentale](#124-status-come-enum-comportamentale)
    - 12.5 [Profile come Value Object del dominio](#125-profile-come-value-object-del-dominio)
    - 12.6 [AssignmentService compone ActivityService](#126-assignmentservice-compone-activityservice)
    - 12.7 [RealtimeNotifier nel frontend web, non nei servizi](#127-realtimenotifier-nel-frontend-web-non-nei-servizi)
    - 12.8 [PersonRepository come contratto di dominio](#128-personrepository-come-contratto-di-dominio)
13. [Casi d'uso per ruolo](#13-casi-duso-per-ruolo)
    - 13.1 [Gestore Missioni](#131-gestore-missioni)
    - 13.2 [Amministratore](#132-amministratore)
14. [Sistema di Plugin](#14-sistema-di-plugin)
    - 14.1 [Posizione nell'architettura](#141-posizione-nellarchitettura)
    - 14.2 [Interfaccia MissionHook](#142-interfaccia-missionhook)
    - 14.3 [Punti di hook e semantica](#143-punti-di-hook-e-semantica)
    - 14.4 [PluginRegistry](#144-pluginregistry)
    - 14.5 [Esempi di hook](#145-esempi-di-hook)
15. [Sistema di Estensioni](#15-sistema-di-estensioni)
    - 15.1 [Posizione nell'architettura](#151-posizione-nellarchitettura)
    - 15.2 [Interfaccia MissionExtension](#152-interfaccia-missionextension)
    - 15.3 [ExtensionRegistry](#153-extensionregistry)
    - 15.4 [ExtensionLoader](#154-extensionloader)
    - 15.5 [Esempi di estensioni](#155-esempi-di-estensioni)
    - 15.6 [Differenza tra plugin ed estensioni](#156-differenza-tra-plugin-ed-estensioni)

---

## 1. Panoramica del sistema

MissionManager è un sistema per la **gestione del ciclo di vita di missioni operative**. Gli operatori definiscono missioni articolate in obiettivi e attività, le assegnano a più persone e gruppi contemporaneamente, avanzano gli stati lungo una macchina a stati e riconoscono i completamenti con badge propagati automaticamente agli assegnatari. Il sistema espone la stessa logica attraverso tre interfacce utente distinte: un'interfaccia web asincrona, una REST API JSON asincrona, e una CLI.

### Capacità principali

- Creazione di missioni come blueprint strutturali (obiettivi e attività operative)
- Assegnazione di una missione a più persone e/o gruppi: ogni assegnazione (`MissionAssignment`) porta la propria copia di obiettivi e attività, con stato ed esito indipendenti
- Gestione del ciclo di vita di ogni `MissionAssignment` con macchina a stati applicata nel dominio
- Assegnazione e avanzamento di attività individuali all'interno di un `MissionAssignment`, con vincolo sugli assegnatari ammessi
- Riconoscimenti gestiti come definizioni di badge riutilizzabili e `BadgeAward` assegnabili al completamento di un assignment o di un'attività, con propagazione automatica agli assegnatari
- Gestione del ciclo di vita di persone (`PersonService`) e gruppi: creazione, modifica, rimozione
- Controllo degli accessi **dichiarativo a entry**: ogni decisione «chi può eseguire quale operazione su quale risorsa» deriva dalla valutazione di `AclEntry` persistite, con soggetti qualificati da livello e/o gruppo (il `Profile` di ogni `Person`), precedenza DENY > ALLOW, ereditarietà gerarchica e default-deny (vedi [§10](#10-sistema-acl-e-autorizzazione))

---

## 2. Modello del dominio: Missioni, Attività e Badge

### 2.1 Mission (Blueprint di missione)

È il **template strutturale** del sistema. Rappresenta la definizione di un'operazione: titolo, descrizione e la struttura degli obiettivi con le relative attività. **Non ha stato né esito propri.**

Una missione:

- deve contenere **almeno un Objective** al momento della creazione; ogni Objective deve includere **almeno un'Activity** definita contestualmente: obiettivi e attività vengono sempre creati insieme come blueprint;
- è **immutabile dopo la creazione**: obiettivi e attività si definiscono unicamente in fase di creazione e **non possono più essere aggiunti né modificati**; le sole operazioni successive sono l'assegnazione (che crea `MissionAssignment` indipendenti) e l'eliminazione del blueprint;
- può essere assegnata a **N persone e/o N gruppi** attraverso la creazione di `MissionAssignment` indipendenti: ciascuno con la propria copia di obiettivi e attività, il proprio stato e il proprio esito;
- espone il metodo di dominio: `validate`;
- ha una `AssignmentPolicy` che vincola il numero di `MissionAssignment` creabili; il valore di default è `AssignmentPolicy.unlimited()` (nessun limite).

### 2.2 AssignmentPolicy (Policy di assegnazione)

È un **value object di dominio** associato alla `Mission` che controlla se e quante volte una missione può essere assegnata. Ha due campi opzionali, indipendenti e componibili:

- `max_total: Optional[int]` — numero massimo di `MissionAssignment` creabili in tutta la storia della missione, indipendentemente dallo stato (incluse completate e fallite). `None` = nessun limite. Una missione con `max_total=1` (factory `once()`) può essere assegnata una sola volta, permanentemente.
- `max_concurrent: Optional[int]` — numero massimo di `MissionAssignment` operativi (`ASSIGNED`, `IN_PROGRESS`) coesistenti simultaneamente. `None` = nessun limite. Gli assignment `UNASSIGNED` sono bozze e non consumano capacità concorrente; il limite viene ricontrollato quando una bozza viene assegnata. Una missione con `max_concurrent=1` (factory `once_active()`) può avere al più un assignment attivo alla volta, ma può essere riassegnata dopo il completamento di quello precedente.

Se entrambi i campi sono impostati, il costruttore richiede `max_total >= max_concurrent`. Il valore di default su ogni `Mission` è `AssignmentPolicy.unlimited()` (`max_total=None, max_concurrent=None`).

Combinazioni libere sono possibili: `AssignmentPolicy(max_total=5, max_concurrent=2)` = al massimo 5 assignment totali con non più di 2 attivi contemporaneamente.

### 2.3 MissionAssignment (Esecuzione di una missione)

È l'**entità vivente** creata ogni volta che una `Mission` viene pianificata per l'esecuzione, con o senza un assegnatario già noto. Ogni `MissionAssignment`:

- porta la propria copia istanziata degli obiettivi e delle attività della `Mission`, **indipendente** dagli altri `MissionAssignment` della stessa missione;
- ha il proprio **stato** (`Status`) che segue la macchina a stati: `UNASSIGNED → ASSIGNED → IN_PROGRESS → COMPLETED/FAILED`;
- ha il proprio **esito** derivato dai propri obiettivi → attività — *Eseguita con successo*, *Parzialmente eseguita* o *Fallita* (vedi § Esiti derivati);
- può ricevere un **BadgeAward** di riconoscimento, ma soltanto quando il suo stato è `COMPLETED`; l'assegnazione del badge viene propagata automaticamente alle persone di quell'assignment;
- identifica l'assegnatario tramite `assignee_type` (`PERSON` o `GROUP`) e `assignee_id` (UUID di una `Person` o `Group` del dominio), entrambi opzionali finché è in stato `UNASSIGNED`;
- espone metodi di dominio: `assign_to`, `update_status`, `award_badge`, `is_completed`, `compute_outcome`, `validate`.

### 2.4 Objective (Obiettivo)

È il sotto-traguardo concreto di una missione. Ogni obiettivo deve contenere **almeno una Activity valida**: le attività sono le unità operative in cui l'obiettivo è suddiviso per essere concretamente eseguito, devono avere un titolo non vuoto e devono appartenere all'obiettivo tramite `objective_id`. La gerarchia è: Missione → Obiettivo → Attività.

L'**esito** di un obiettivo è derivato automaticamente dagli stati terminali delle sue attività. Il valore è calcolato da `Objective.compute_outcome()` e restituito come stringa (`str | None`):

| Valore `compute_outcome()` | Condizione |
|---|---|
| `"COMPLETED"` | Tutte le attività dell'obiettivo sono in stato `COMPLETED` |
| `"FAILED"` | Almeno una attività è in stato `FAILED` (include il caso misto COMPLETED+FAILED) |
| `"IN_PROGRESS"` | Nessuna attività `FAILED`, almeno una `IN_PROGRESS` |
| `None` | Nessuna attività, oppure tutte `UNASSIGNED`/`ASSIGNED` |

Gli obiettivi non possiedono uno stato operativo proprio e non vengono marcati manualmente: il loro esito è sempre calcolato. Le attività vengono definite contestualmente alla costruzione dell'Objective (in fase di creazione della missione) e non in un'operazione autonoma post-creazione. `compute_outcome()` calcola l'esito derivato dalle attività.

### 2.5 Activity (Attività)

È un'unità di lavoro eseguibile all'interno di un **Objective** (appartenente a un `MissionAssignment`). Ha un proprio ciclo di vita (`Status`). `ActivityService.assign_to()` aggiunge un assegnatario all'attività e, se l'attività era in stato `UNASSIGNED`, la transisce automaticamente ad `ASSIGNED`; l'attività deve avere almeno un assegnatario prima di poter passare allo stato `IN_PROGRESS`. Gli assegnatari ammessi dipendono dall'assignment: se `assignee_type == GROUP`, solo i membri di quel gruppo; se `assignee_type == PERSON`, solo quella persona. Una singola persona può essere assegnata a più attività dello stesso `MissionAssignment`. L'attività ha un unico stato e un unico esito, indipendentemente da quante persone vi siano assegnate. Può ricevere un `BadgeAward` di completamento indipendentemente dall'obiettivo e dall'assignment padre.

### 2.6 Badge (Definizione di riconoscimento)

Rappresenta la **definizione riutilizzabile** di un riconoscimento visuale: nome, descrizione e URL immagine opzionale. Non contiene dati di assegnazione e non cambia quando viene assegnato più volte.

### 2.7 BadgeAward (Assegnazione di riconoscimento)

Rappresenta una singola assegnazione di un `Badge` a un `MissionAssignment` o a un'`Activity`. Contiene `badge_id`, `target_type`, `target_id`, `awarded_at` e i destinatari raggiunti dalla propagazione. Ogni `BadgeAward` è indipendente: assegnare lo stesso `Badge` a target o persone diverse non modifica le altre assegnazioni.

Un `BadgeAward` viene creato **solo se il target è nello stato `COMPLETED`**. Una volta creato, viene propagato automaticamente:

- per un `MissionAssignment` con `assignee_type == GROUP`: a tutti i membri correnti del gruppo (risolti tramite `PersonRepository.get_by_group()`);
- per un `MissionAssignment` con `assignee_type == PERSON`: alla persona diretta;
- per un'`Activity`: a tutti gli assegnatari dell'attività.

### 2.8 Status — macchina a stati

`MissionAssignment` e `Activity` condividono lo stesso enumerato `Status` con la stessa macchina a stati di base:

```
UNASSIGNED ──► ASSIGNED ──► IN_PROGRESS ──► COMPLETED
                                        └──► FAILED
```

Le transizioni sono applicate dal dominio stesso: `Status` espone i metodi `can_transition_to(s)` e `is_terminal()`. Qualsiasi tentativo di transizione non prevista solleva `StatusTransitionError` prima ancora di raggiungere la persistenza. Per un `MissionAssignment`: la transizione `UNASSIGNED → ASSIGNED` avviene tramite `AssignmentService.assign()` che imposta l'assegnatario; la transizione `ASSIGNED → IN_PROGRESS` è automatica, scattata da `ActivityService.update_status()` quando almeno una Activity dell'assignment passa allo stato `IN_PROGRESS`; la transizione a `COMPLETED` richiede che tutte le attività associate siano `COMPLETED`. Se un'attività passa a `FAILED`, il `MissionAssignment` padre — se non è già in uno stato terminale — viene portato automaticamente a `FAILED` nella stessa operazione: un singolo fallimento operativo chiude l'intero assignment come fallito. Per un'`Activity`: la transizione `UNASSIGNED → ASSIGNED` è automatica, scattata da `ActivityService.assign_to()` quando il primo assegnatario viene aggiunto; la transizione `ASSIGNED → IN_PROGRESS` è manuale, tramite `ActivityService.update_status()`, e porta automaticamente il `MissionAssignment` padre da `ASSIGNED` a `IN_PROGRESS` se quest'ultimo si trova ancora in quello stato; le transizioni a `COMPLETED` e `FAILED` sono manuali.

| Stato | Significato per `MissionAssignment` | Significato per `Activity` |
|---|---|---|
| `UNASSIGNED` | Creato senza assegnatario: nessuna persona o gruppo ancora impostato | Nessun assegnatario ancora aggiunto |
| `ASSIGNED` | Assegnato a una persona o un gruppo, indipendentemente dallo stato delle attività interne | Almeno un assegnatario aggiunto; non ancora in esecuzione |
| `IN_PROGRESS` | Almeno una Activity interna è in stato `IN_PROGRESS` | In esecuzione |
| `COMPLETED` | Chiuso normalmente: tutte le attività associate sono `COMPLETED` — stato terminale | Completata — stato terminale |
| `FAILED` | Chiuso con fallimento operativo, impostato manualmente o automaticamente quando un'attività interna passa a `FAILED` — stato terminale | Fallita — stato terminale |

### 2.9 Esiti derivati

Lo stato operativo (`Status`) traccia il progresso dell'esecuzione. L'**esito** di `Objective` e `MissionAssignment` è invece un valore *calcolato* a partire dagli stati terminali delle entità sottostanti, non impostato manualmente.

**Esito del MissionAssignment** (derivato dagli esiti degli Objective, calcolato da `MissionAssignment.compute_outcome()`):

| Valore `compute_outcome()` | Condizione |
|---|---|
| `"COMPLETED"` | Tutti gli Objective restituiscono `"COMPLETED"` |
| `"FAILED"` | Almeno un Objective restituisce `"FAILED"` |
| `"IN_PROGRESS"` | Nessun Objective `"FAILED"`, almeno uno `"IN_PROGRESS"` |
| `None` | Nessun obiettivo, oppure tutti con esito `None` |

Lo stato `COMPLETED` del `MissionAssignment` rappresenta la chiusura operativa; `compute_outcome()` restituisce il valore qualitativo dell'esito. I valori sono le stesse costanti dell'enum `Status` come stringa, per coerenza con il resto dell'API.

---

## 3. Persone, Gruppi e Zone nel dominio

`Person`, `Group` e `Zone` sono **entità del dominio di MissionManager** al pari di `Mission` e `Badge`. Come per tutte le entità di dominio, il loro ciclo di vita è gestito attraverso i contratti del Layer 2 (`PersonRepository`, `GroupRepository`) e la logica applicativa risiede in `PersonService`. La scelta implementativa su come e dove questi dati vengono persistiti (database locale, servizio remoto, o altra fonte) appartiene al Layer 3 e non modifica i contratti architetturali.

### 3.1 Person (Persona)

`Person` è un operatore del dominio, identificato da un UUID e corredato di un insieme di nicknames usato per la visualizzazione. Porta un `Profile` (livello + gruppi ACL) che il sistema ACL valuta contro le `AclEntry` per ogni richiesta ([§10](#10-sistema-acl-e-autorizzazione)). Il ciclo di vita (creazione, modifica, rimozione) è gestito da `PersonService`; l'assegnazione del profilo è un'operazione separata e riservata (`set_acl_profile`, [§10.11](#1011-gestione-delle-acl-e-prevenzione-dellescalation)).

### 3.2 Profile (Profilo di controllo accessi)

`Profile` è un **value object** del dominio che descrive ciò che il sistema ACL conosce del richiedente:

- `level` — intero non negativo; **un numero più basso identifica un profilo più privilegiato** (convenzione `≤`, [§10.2](#102-modello-concettuale)). Il valore di default è la sentinella `ANON_SENTINEL` (il massimo rappresentabile): una persona appena creata è al minimo privilegio.
- `groups` — insieme di gruppi ACL (stringhe, es. `"operators"`); ogni profilo include **sempre** il gruppo universale `"public"`, implicito e non persistito.

I richiedenti **non autenticati** ricevono il **profilo anonimo implicito** `Profile.anonymous()` = `(ANON_SENTINEL, {"public"})`: livello e gruppo sono così sempre valutabili, senza rami speciali nella valutazione. `Profile` è immutabile e non ha identità propria: due profili con gli stessi valori sono equivalenti. Le entità lo trasportano ma non lo interpretano mai: la valutazione avviene solo nel sistema ACL ([§10.5](#105-semantica-di-valutazione)).

### 3.3 Group (Gruppo)

`Group` è un aggregato di persone identificato da un UUID, usato come destinatario di assegnazioni di missione. Quando MissionManager ne ha bisogno (es. propagazione badge, verifica perimetro attività), risolve i membri tramite `PersonRepository.get_by_group()`. Può avere una `Zone` associata. Il ciclo di vita dei gruppi è gestito da `PersonService`.

### 3.4 Zone (Zona)

Attributo opzionale di un gruppo. Il tipo è determinato dall'enumerazione `ZoneType`: `GEOGRAPHIC` (zona geografica reale, es. "Europa Centrale", "Settore Nord") o `VIRTUAL` (spazio non fisico, es. "Internet", "Sito web", "Infrastruttura cloud").

---

## 4. Regole di business e attori

### 4.1 Regole di business fondamentali

Le seguenti regole sono codificate nel dominio e nei servizi e non dipendono dal frontend attraverso cui si accede al sistema:

- Una missione deve avere **almeno un obiettivo** alla creazione; ogni Objective deve includere **almeno un'Activity** definita contestualmente — obiettivi e attività vengono sempre creati insieme, non in fasi separate.
- L'esito di un Objective è **calcolato** dagli stati terminali delle sue attività; non viene impostato manualmente.
- L'esito di un `MissionAssignment` è **calcolato** dagli esiti dei suoi Objective; non viene impostato manualmente.
- Una `Mission` non ha stato né esito propri: lo stato esiste solo a livello di `MissionAssignment`. Una `Mission` appena creata può non avere ancora nessun `MissionAssignment`.
- Una `Mission` può dare origine a **N `MissionAssignment`** indipendenti, uno per ogni persona o gruppo assegnato; ogni assignment porta la propria copia istanziata degli obiettivi e delle attività.
- La `AssignmentPolicy` della `Mission` può limitare quanti `MissionAssignment` possono essere creati: `max_total` impone un tetto storico permanente (nessun nuovo assignment è possibile una volta raggiunto, indipendentemente dallo stato degli assignment esistenti); `max_concurrent` impone un tetto sugli assignment operativi (`ASSIGNED`, `IN_PROGRESS`) attivi simultaneamente. Gli assignment `UNASSIGNED` sono bozze e non consumano capacità concorrente; il controllo viene ripetuto in `AssignmentService.assign()`. I controlli avvengono in `AssignmentService.create()` prima del hook `BEFORE_CREATE_ASSIGNMENT`.
- Gli identificatori di `Person` e `Group` usati nelle assegnazioni vengono verificati tramite `PersonRepository.exists()` e `GroupRepository.exists()` prima di creare un `MissionAssignment`.
- Un `MissionAssignment` può essere creato con o senza assegnatario. Se creato con `assignee_type` e `assignee_id` valorizzati, nasce in stato `ASSIGNED`; se creato senza assegnatario, nasce in stato `UNASSIGNED` e `assignee_type`/`assignee_id` rimangono `None` finché non viene invocato `AssignmentService.assign()`. Lo stato `IN_PROGRESS` si raggiunge automaticamente quando almeno una Activity interna passa allo stato `IN_PROGRESS` tramite `ActivityService.update_status()`.
- `ActivityService.assign_to()` aggiunge un assegnatario all'attività e, se l'attività era in stato `UNASSIGNED`, la porta automaticamente ad `ASSIGNED`. Un'attività deve avere **almeno un assegnatario** prima di poter passare a `IN_PROGRESS`; l'esistenza della persona viene verificata tramite `PersonRepository.exists()`.
- Gli assegnatari di un'attività sono vincolati al perimetro dell'assignment: se `assignee_type == GROUP`, solo i membri di quel gruppo; se `assignee_type == PERSON`, solo quella persona.
- Una persona può essere assegnata a **più attività** dello stesso `MissionAssignment`.
- Un `MissionAssignment` può passare a `COMPLETED` solo quando tutte le attività associate sono `COMPLETED`. Un esito aggregato `FAILED` richiede lo stato `FAILED`, propagato automaticamente quando una singola attività fallisce.
- Quando un'`Activity` passa a `FAILED`, il `MissionAssignment` padre non ancora terminale viene portato automaticamente a `FAILED` nella stessa operazione (`ActivityService.update_status()`): è sufficiente un singolo fallimento operativo per chiudere l'intero assignment come fallito, in modo speculare alla transizione automatica a `IN_PROGRESS`.
- Un `BadgeAward` può essere creato per un `MissionAssignment` o per un'`Activity` **solo se il target è nello stato `COMPLETED`**.
- Ogni target (`MissionAssignment`, `Activity`) può ricevere **al massimo un `BadgeAward`**, ma lo stesso `Badge` può essere assegnato più volte a target diversi senza condividere timestamp o stato di assegnazione.
- Quando si crea un `BadgeAward` per un `MissionAssignment` completato, l'assegnazione viene propagata automaticamente: se l'assignment è per un `Group`, a tutti i suoi membri correnti (risolti tramite `PersonRepository.get_by_group()`); se per una `Person`, a quella persona.

### 4.2 Attori e ruoli

Il sistema prevede tre attori distinti:

| Attore | Ruolo |
|---|---|
| **Gestore Missioni** | Crea e gestisce l'operativo: crea missioni con obiettivi e attività, assegna missioni a persone e gruppi, gestisce il ciclo di vita degli stati e crea `BadgeAward` |
| **Amministratore** | Gestisce il ciclo di vita di persone e gruppi del dominio: aggiunta, modifica e rimozione di `Person` e `Group` tramite `PersonService` |
| **Sistema** | Attore automatico che estende alcuni use case (es. calcolo degli esiti derivati dagli stati terminali) |

---

## 5. Architettura a strati

Il sistema è organizzato in cinque layer. Le dipendenze del codice applicativo seguono la regola della dipendenza unidirezionale: ogni layer conosce solo i layer interni o i contratti dei layer interni, mai i dettagli degli adapter esterni.

```
┌────────────────────────────────────────────────────────┐
│  Layer 5 — Frontends                                   │
│  REST API JSON (async) │ Web App (async) │ CLI          │
└───────────────────────────┬────────────────────────────┘
                            │ dipende da
┌───────────────────────────▼────────────────────────────┐
│  Layer 4 — Services                                    │
│  MissionService │ AssignmentService │ ActivityService  │
│  BadgeService │ PersonService │ AclService             │
│  AuthorizationPolicy │ PluginRegistry │ ExtensionRegistry │
└───────────────────────────┬────────────────────────────┘
                            │ dipende da contratti
┌───────────────────────────▼────────────────────────────┐  ┌──────────────────────┐
│  Layer 2 — Repository Interfaces e Porte               │◄─┤ Layer 3              │
│  *Repository │ PersonRepository │ GroupRepository      │  │ Repository Adapter e │
│  MissionHook │ MissionExtension                         │  │ Adapter Esterni      │
└───────────────────────────┬────────────────────────────┘  │                      │
                            │ dipende da                     │ implementano Layer 2;│
┌───────────────────────────▼────────────────────────────┐  │ iniettati a bootstrap│
│  Layer 1 — Domain                                      │◄─┤ nel Layer 4 via DI;  │
│  Mission │ MissionAssignment │ Objective │ Activity    │  │ dipendono da Layer 1 │
│  Badge │ BadgeAward │ Status │ AssignmentPolicy        │  │ e dai contratti      │
│  Person │ Group │ Zone │ Profile │ AclEntry            │  │ del Layer 2          │
└────────────────────────────────────────────────────────┘  └──────────────────────┘
```

La regola fondamentale è che il **Domain non dipende da nessun altro livello applicativo**. Il livello Service dipende dai contratti del Layer 2, mai dagli adapter del Layer 3 — questo è il confine critico della Dependency Injection. I frontend dipendono dai servizi e dai tipi/errori esposti dal dominio, ma non contengono logica di business.

### 5.1 I cinque layer

**Layer 1 — Domain (nucleo)**: nessuna dipendenza esterna. Modelli, enumerazioni, eccezioni di dominio. È il layer che cambia più raramente e che non deve mai sapere nulla di persistenza, protocolli di rete o interfacce utente.

**Layer 2 — Repository Interfaces e Porte**: definisce i contratti astratti di persistenza (`BaseRepository<T>`, `MissionRepository`, `PersonRepository`, `GroupRepository`, ecc.) e le porte verso meccanismi estensibili (`OperatorIdentityProvider`, `MissionHook`, `MissionExtension`). Dipende solo dal Domain. Non contiene logica di business. Questa separazione rende il livello Service indipendente dai meccanismi di persistenza, identità, plugin ed estensioni.

**Layer 3 — Repository Adapter**: implementa i contratti del Layer 2 con adapter sostituibili. Include gli adapter di persistenza per tutte le entità del dominio (incluse `PersonRepositoryAdapter` e `GroupRepositoryAdapter`), gli adapter di identità per i frontend e gli hook concreti dei plugin. Dipende da Domain e dai contratti del Layer 2. I dettagli tecnologici specifici non fanno parte di questa documentazione architetturale.

**Layer 4 — Services**: contiene tutta la logica applicativa (orchestrazione dei use case). Dipende da Domain e dai **contratti** del Layer 2, mai dagli adapter del Layer 3. I service ricevono gli adapter dall'esterno tramite iniezione nel costruttore. `PluginRegistry`, `ExtensionRegistry`, i moduli `MissionExtension` caricati e i **DTO** (Data Transfer Objects) risiedono in questo layer. I service non restituiscono mai entità di dominio ai frontend: le serializzano in DTO prima di restituirle.

**Layer 5 — Frontends**: tre implementazioni intercambiabili di interfaccia utente (REST API JSON, Web App, CLI). Dipende da Services e Domain. Non contiene logica di business — è puro adattamento tra il protocollo di comunicazione e i servizi.

### 5.2 Direzione delle dipendenze

La regola è semplice: **le frecce puntano sempre verso l'interno**. Nessun layer interno sa che esiste il layer che lo usa.

```
frontends    →  services
frontends    →  OperatorIdentityProvider (porta Layer 2, per l'identità dell'operatore)
services     →  repository interfaces e porte (Layer 2)
services     →  domain
repository adapter → repository interfaces e porte (Layer 2)
repository adapter → domain
adapter PersonRepository / GroupRepository → persistenza   (il meccanismo è un dettaglio del Layer 3)
frontends    →  domain              (per i tipi di ritorno e le eccezioni)
```

Gli adapter non dipendono dai servizi, e i servizi non dipendono dagli adapter: questa è la garanzia di sostituibilità del Layer 3.

---

## 6. Livello Domain

Il Domain è il nucleo invariante del sistema. Non dipende da nulla di esterno: nessun framework, nessun meccanismo di persistenza, nessun protocollo di rete. È composto esclusivamente da oggetti di dominio puri (Python `dataclass`), privi di qualsiasi conoscenza di SQL, HTTP, serializzazione o autorizzazione.

Le sezioni [§2](#2-modello-del-dominio-missioni-attività-e-badge) e [§3](#3-persone-gruppi-e-zone-nel-dominio) descrivono il **significato di business** di ciascun concetto (cosa rappresenta, quali regole lo governano). Questa sezione li classifica invece secondo il loro **ruolo architetturale** nel Livello Domain — entità, value object, enumerazioni, policy, eventi ed eccezioni — descrivendo quali responsabilità e quali metodi ciascun oggetto incapsula.

### 6.1 Categorie di oggetti del dominio

Il dominio non è un sacco indistinto di classi: ogni oggetto appartiene a una categoria precisa, con caratteristiche e responsabilità definite.

| Categoria | Oggetti | Caratteristiche |
|---|---|---|
| **Entità** | `Mission`, `MissionAssignment`, `Objective`, `Activity`, `Badge`, `BadgeAward`, `Person`, `Group`, `Zone` | Identità propria (UUID), ciclo di vita, mutabili; espongono `validate()` e (alcune) metodi comportamentali |
| **Value Object** | `AssignmentPolicy`, `Profile`, `AclEntry`, `SubjectRef`, `ResourceRef` | Immutabili (`frozen`), senza identità, uguaglianza per valore, auto-validanti |
| **Enumerazioni** | `Status`, `AssigneeType`, `ZoneType` | Insiemi chiusi di valori; `Status` è *comportamentale* (incapsula la macchina a stati) |
| **Policy di dominio** | `AssignmentStatusPolicy`, `BadgeAwardPolicy`, `ActivityAssignmentPolicy` | Oggetti stateless che reificano singole invarianti, testabili e iniettabili indipendentemente |
| **Eventi di dominio** | `DomainEvent` e sottoclassi | Value object immutabili pubblicati *dopo* una persistenza riuscita |
| **Eccezioni** | `MissionManagerError` e gerarchia | Errori di business tipizzati, condivisi da tutti i layer |

Il dominio dichiara anche alcune **porte** (Python `Protocol`) implementate all'esterno — `EventPublisherPort` (§6.6), `OperatorIdentityProvider` e i repository — descritte nel [§7](#7-livello-repository-e-porte) in quanto contratti del confine.

### 6.2 Entità

Le entità sono oggetti con **identità propria** (un `id: UUID`) e un ciclo di vita: due entità con gli stessi campi ma `id` diverso sono entità distinte. Si dividono in due famiglie:

- **Modello operativo**: `Mission`, `MissionAssignment`, `Objective`, `Activity`, `Badge`, `BadgeAward` — il cuore della gestione delle missioni.
- **Anagrafica**: `Person`, `Group`, `Zone` — gli attori e i loro raggruppamenti (vedi [§3](#3-persone-gruppi-e-zone-nel-dominio)).

A differenza dei value object, le entità sono **mutabili**: il loro stato evolve nel tempo. Le invarianti non vengono però lasciate ai servizi — ogni entità le applica nei propri metodi, sollevando un'eccezione di dominio prima che lo stato incoerente possa raggiungere la persistenza.

| Entità | Metodi di dominio | Responsabilità incapsulata |
|---|---|---|
| `Mission` | `validate()` | Blueprint immutabile; nessuno stato né esito propri; richiede titolo e ≥1 obiettivo |
| `MissionAssignment` | `assign_to()`, `update_status()`, `award_badge()`, `is_completed()`, `compute_outcome()`, `validate()` | L'entità più ricca: incapsula assegnazione, transizione di stato, premiazione ed esito derivato |
| `Objective` | `compute_outcome()`, `validate()` | Esito *calcolato* dalle attività; nessuno stato proprio; richiede ≥1 attività valida appartenente all'obiettivo |
| `Activity` | `update_status()`, `validate()` | Unità di lavoro con stato proprio e lista di `assignees`; richiede un titolo |
| `Badge` | — | Definizione pura riutilizzabile; nessuna logica |
| `BadgeAward` | — | Record immutabile di un fatto: `target_type` (stringa `"ASSIGNMENT"`/`"ACTIVITY"`), `target_id`, `recipients`, `awarded_at` |
| `Person` | `primary_nickname()`, `validate()` | Operatore; porta il `Profile` ACL; richiede ≥1 nickname non vuoto |
| `Group` | `validate()` | Aggregato di persone; `Zone` opzionale; `validate()` è volutamente un no-op (un gruppo è valido anche senza zona) |
| `Zone` | `validate()` | Attributo di un gruppo; richiede un nome; tipizzata da `ZoneType` |

`MissionAssignment` concentra il comportamento più significativo del dominio e illustra il principio del *self-enforcement*:

- `assign_to(type, id)` imposta l'assegnatario e, se l'assignment era `UNASSIGNED`, lo promuove automaticamente ad `ASSIGNED`;
- `update_status(new)` consulta `Status.can_transition_to()` e solleva `StatusTransitionError` su qualsiasi transizione non prevista — la macchina a stati non è replicata nei servizi;
- `award_badge(award)` rifiuta con `ValidationError` qualsiasi premiazione su un assignment non `COMPLETED`;
- `compute_outcome()` deriva l'esito dagli `Objective` (che a loro volta lo derivano dalle `Activity`), senza che nessuno stato qualitativo venga mai scritto a mano.

### 6.3 Value Object

I value object non hanno identità: sono definiti **interamente dal proprio valore** e due istanze con gli stessi campi sono intercambiabili. Sono dichiarati come `dataclass(frozen=True)` (immutabili) e validano i propri invarianti nel costruttore (`__post_init__`), così è impossibile costruirne uno incoerente. Non vivono da soli: sono sempre incorporati in un'entità.

| Value Object | Incorporato in | Invarianti (nel costruttore) | Metodi |
|---|---|---|---|
| `AssignmentPolicy` | `Mission` | `max_total ≥ 1`, `max_concurrent ≥ 1`, `max_total ≥ max_concurrent` | factory `unlimited()`, `once()`, `once_active()` |
| `Profile` | `Person` | `level ≥ 0`; `groups` include sempre `"public"` | factory `anonymous()`, `stored_groups()` |
| `AclEntry` | — (persistita a sé) | INV-1..INV-5 ([§10.4](#104-invarianti-strutturali)) in `validate()` | `matches(principal, profile)` |
| `SubjectRef` / `ResourceRef` | `AclEntry` | `USER` richiede un id, `PUBLIC` non lo ammette | `public()`, `user()`, `type_root()`, `key()` |

La semantica di business è in [§2.2](#22-assignmentpolicy-policy-di-assegnazione), [§3.2](#32-profile-profilo-di-controllo-accessi) e [§10](#10-sistema-acl-e-autorizzazione). Dal punto di vista del livello, l'aspetto rilevante è che questi oggetti sono **portati ma non interpretati dal dominio operativo**: `AssignmentPolicy` viene letta da `AssignmentService` per decidere se un nuovo `MissionAssignment` è ammesso; `Profile` e `AclEntry` sono valutati solo dal sistema ACL al confine — le entità non eseguono mai un controllo di autorizzazione (vedi [§12.3](#123-acl-al-confine-del-sistema-non-nelle-entità-di-dominio)).

### 6.4 Enumerazioni

Tre enumerazioni definiscono gli insiemi chiusi di valori del dominio.

- **`AssigneeType`** (`PERSON` | `GROUP`) — discrimina la natura dell'assegnatario di un `MissionAssignment` e governa la propagazione dei badge e il perimetro degli assegnatari di un'attività.
- **`ZoneType`** (`GEOGRAPHIC` | `VIRTUAL`) — qualifica il tipo di `Zone` associata a un gruppo.
- **`Status`** — non è un semplice elenco di etichette ma un'enumerazione **comportamentale**: la mappa delle transizioni ammesse è la sua unica fonte di verità, e i due metodi `can_transition_to(target) → bool` e `is_terminal() → bool` rendono la macchina a stati auto-contenuta nel dominio, senza alcuna catena `if/elif` dispersa nei servizi.

La mappa delle transizioni condivisa da `MissionAssignment` e `Activity`:

| Da | Verso (ammessi) |
|---|---|
| `UNASSIGNED` | `ASSIGNED` |
| `ASSIGNED` | `UNASSIGNED`, `IN_PROGRESS`, `FAILED` |
| `IN_PROGRESS` | `COMPLETED`, `FAILED` |
| `COMPLETED` | — (terminale) |
| `FAILED` | — (terminale) |

Il ritorno `ASSIGNED → UNASSIGNED` esiste nella mappa ma è riservato a un solo caso: la rimozione dell'ultimo assegnatario di un'`Activity` (`ActivityService.unassign()`). Per questo `AssignmentStatusPolicy.validate_transition()` rifiuta esplicitamente ogni richiesta *diretta* verso `UNASSIGNED` proveniente da un comando di cambio stato — il ripristino può avvenire solo come effetto della de-assegnazione (vedi [§6.5](#65-policy-di-dominio)).

### 6.5 Policy di dominio

Le policy sono **oggetti stateless** che estraggono singole invarianti dalla logica dei servizi e le esprimono come regole isolate, testabili e iniettabili. Ogni metodo `validate_*` solleva l'eccezione appropriata se la regola è violata e non restituisce nulla altrimenti. Reificano regole già implicite nelle entità e in [§4](#4-regole-di-business-e-attori), ma in una forma che i servizi possono invocare puntualmente.

| Policy | Responsabilità | Metodi |
|---|---|---|
| `AssignmentStatusPolicy` | Regole di transizione e di chiusura oltre la mappa di base | `validate_transition()`, `validate_activity_in_progress()`, `validate_assignment_completion()`, `validate_activity_unassign()` |
| `BadgeAwardPolicy` | Precondizioni dei `BadgeAward` | `validate_target_completed()`, `validate_no_duplicate_award()` |
| `ActivityAssignmentPolicy` | Perimetro degli assegnatari di un'attività | `validate_person_in_assignment()` |

La validazione della macchina a stati vive così su **due livelli complementari**: l'entità (`update_status()`) garantisce la transizione *strutturale* tramite la mappa, mentre `AssignmentStatusPolicy` aggiunge le regole *di processo* — un'attività passa a `IN_PROGRESS` solo se ha almeno un assegnatario, un assignment diventa `COMPLETED` solo se l'esito aggregato è `COMPLETED` (un esito `FAILED` impone di portarlo a `FAILED`), e `UNASSIGNED` non è un bersaglio diretto. `ActivityAssignmentPolicy` codifica il vincolo descritto in [§2.5](#25-activity-attività): per un assignment di tipo `GROUP` solo i membri del gruppo, per uno di tipo `PERSON` solo l'assegnatario nominale.

### 6.6 Eventi di dominio

Gli eventi di dominio sono value object immutabili (`frozen`) che registrano **un fatto già avvenuto**: vengono pubblicati *dopo* una persistenza riuscita e mai se l'operazione che li origina fallisce. Tutti derivano da `DomainEvent` (che porta `occurred_at`) e trasportano l'`operator_id` autore dell'azione insieme ai dati identificativi.

| Evento | Emesso quando | Dati principali |
|---|---|---|
| `MissionCreated` / `MissionDeleted` | Creazione / eliminazione del blueprint | `mission_id`, `operator_id`, (`title`) |
| `AssignmentCreated` | Creazione di un `MissionAssignment` | `assignment_id`, `mission_id`, `assignee_type`, `assignee_id` |
| `AssignmentStatusChanged` | Avanzamento di stato di un assignment | `assignment_id`, `old_status`, `new_status` |
| `ActivityAssigned` | Aggiunta di un assegnatario a un'attività | `activity_id`, `person_id` |
| `ActivityStatusChanged` | Avanzamento di stato di un'attività | `activity_id`, `assignment_id`, `old_status`, `new_status` |
| `BadgeAwarded` | Creazione di un `BadgeAward` | `badge_award_id`, `badge_id`, `target_type`, `target_id`, `recipient_ids` |

La pubblicazione passa per la porta di dominio `EventPublisherPort` (`publish(event)`): i servizi dipendono dall'interfaccia, l'implementazione concreta vive nell'infrastruttura. I consumatori (notificatore realtime della Web App — vedi [§9.2](#92-web-app-asincrona) e [§12.7](#127-realtimenotifier-nel-frontend-web-non-nei-servizi) — audit log, ecc.) si sottoscrivono e reagiscono in modo asincrono, senza che il dominio sappia chi li ascolta.

### 6.7 Eccezioni di dominio

Tutti gli errori di business formano una gerarchia con `MissionManagerError` come radice comune. I frontend possono catturare l'intera famiglia con un unico handler oppure intercettarne le sottoclassi in modo granulare per mapparle sui codici del protocollo (vedi [§10.5](#105-aclerror-e-mappatura)). Le eccezioni sono cross-cutting: definite in un punto unico e condivise da tutti i layer.

| Eccezione | Significato nel dominio |
|---|---|
| `MissionManagerError` | Radice comune di tutti gli errori di business |
| `ValidationError` | Invariante o campo non valido (porta il `field` opzionale) |
| `NotFoundError` | Entità richiesta inesistente (porta `resource_type`/`resource_id`) |
| `ForbiddenError` → `AuthorizationError` | Accesso negato / livello ACL insufficiente per l'operazione |
| `AuthenticationError` | Identità dell'operatore mancante o non valida |
| `ACLError` | Errore generico del sottosistema ACL |
| `StatusTransitionError` | Transizione di stato non ammessa (porta `current_status`/`requested_status`) |
| `OperationAbortedError` | Un hook plugin `BEFORE_*` ha impostato `abort = True` |
| `RateLimitExceededError` | Quota per (operatore, operazione) superata |
| `ExtensionLoadError` / `ExtensionConflictError` | Errori di caricamento o registrazione di un'estensione |

### 6.8 Principi invarianti del livello

Le scelte trasversali che tengono il dominio coeso e indipendente — approfondite in [§12](#12-scelte-architetturali):

1. **Purezza** — nessuna dipendenza da framework, persistenza o rete: il dominio è il layer che cambia più raramente.
2. **Auto-validazione** — le entità espongono `validate()`, invocato prima di ogni persistenza; i value object validano i propri invarianti già nel costruttore. Lo stato incoerente non è costruibile.
3. **Self-enforcement** — le invarianti vivono nei metodi delle entità e nelle policy, non nei servizi: ogni violazione solleva un'eccezione di dominio prima della persistenza.
4. **Stato come enum comportamentale** — la macchina a stati è incapsulata in `Status`; i servizi non contengono logica condizionale sulle transizioni.
5. **Esiti calcolati, mai impostati** — l'esito di `Objective` e `MissionAssignment` è sempre derivato da `compute_outcome()`, mai scritto manualmente.
6. **Immutabilità dove conta** — value object `frozen`, blueprint `Mission` immutabile dopo la creazione, `BadgeAward` come record di un fatto avvenuto.
7. **Nessuna ACL nelle entità operative** — le entità trasportano il `Profile` ma non eseguono mai controlli di autorizzazione: questi avvengono solo al confine del sistema, valutando le `AclEntry` (vedi [§12.3](#123-acl-al-confine-del-sistema-non-nelle-entità-di-dominio)).

---

## 7. Livello Repository e Porte

Il Layer 2 raccoglie i contratti che isolano i services dai dettagli esterni: repository per tutte le entità del dominio (missioni, assegnazioni, persone, gruppi, ecc.), le porte del sistema ACL (`AclEntryRepository`, `ProfileProvider`, `ResourceHierarchyProvider` — [§10.9](#109-architettura-porte-policy-service)), porte per identità operatore, plugin ed estensioni. Gli adapter che soddisfano questi contratti appartengono al Layer 3 e restano descritti in modo tecnologicamente neutro.

### 7.1 Repository locali (contratti)

`BaseRepository<T>` definisce il contratto CRUD generico:

```
get(id: UUID) → T
list(filters: dict) → List[T]
save(entity: T) → T
delete(id: UUID) → bool
exists(id: UUID) → bool
```

Ogni repository specializzato estende `BaseRepository` aggiungendo query semantiche proprie:

| Repository | Query aggiuntive |
|---|---|
| `MissionRepository` | `get_by_title` |
| `MissionAssignmentRepository` | `get_by_mission`, `get_by_assignee`, `get_by_status`, `count_by_mission`, `count_active_by_mission` |
| `ObjectiveRepository` | `get_by_assignment` |
| `ActivityRepository` | `get_by_objective`, `get_by_person` |
| `BadgeRepository` | Nessuna query aggiuntiva obbligatoria; CRUD sulle definizioni di badge |
| `BadgeAwardRepository` | `get_by_person`, `get_by_assignment`, `get_by_activity`, `exists_for_target` |
| `PersonRepository` | `get_by_group` |
| `GroupRepository` | `add_member`, `remove_member` |
| `AclEntryRepository` | `list_for(risorsa, operazione)`, `list_by_resource`, `list_all`, `save`, `delete`, `delete_by_resource`, `is_empty` — persistenza delle `AclEntry` ([§10.9](#109-architettura-porte-policy-service)) |

### 7.2 PersonRepository e GroupRepository

`PersonRepository` e `GroupRepository` seguono lo stesso pattern di `BaseRepository<T>` degli altri repository del sistema, aggiungendo le query semantiche proprie delle entità `Person` e `Group`.

**PersonRepository:**

| Operazione | Descrizione |
|---|---|
| `get(id)` | Recupera il profilo completo di una persona (incluso il `Profile` ACL) |
| `exists(id)` | Verifica l'esistenza di una persona (usato da `AssignmentService` e `ActivityService`) |
| `get_by_group(group_id)` | Restituisce le `Person` associate al gruppo (usato da `ActivityService` e `BadgeService`) |
| `save(p)` / `delete(id)` | Persistono le modifiche al ciclo di vita della persona |

**GroupRepository:**

| Operazione | Descrizione |
|---|---|
| `get(id)` | Recupera un gruppo per ID |
| `exists(id)` | Verifica l'esistenza del gruppo (usato da `AssignmentService`) |
| `save(g)` / `delete(id)` | Persistono le modifiche al ciclo di vita del gruppo |
| `add_member(group_id, person_id)` / `remove_member(group_id, person_id)` | Aggiornano la membership dei `Group` di dominio, usata da `PersonRepository.get_by_group()` |

### 7.3 OperatorIdentityProvider

`OperatorIdentityProvider` è una **porta del Layer 2** distinta da `PersonRepository`. Mentre `PersonRepository` gestisce i dati di tutte le persone del dominio, `OperatorIdentityProvider` stabilisce chi sta effettuando la richiesta corrente.

| Operazione | Descrizione |
|---|---|
| `get_current_operator()` | Restituisce la `Person` (con il `Profile` ACL) dell'operatore autenticato corrente |

L'adapter è specifico per frontend: REST API, Web App e CLI possono stabilire l'identità dell'operatore in modi diversi, ma tutti restituiscono una `Person` completa tramite `PersonRepository.get()` per materializzare il profilo completo.

### 7.4 Adapter

Gli adapter del Layer 3 realizzano i contratti del Layer 2: repository per tutte le entità del dominio, identità operatore, loader di estensioni e hook plugin. Ogni adapter si occupa di tradurre tra il modello del dominio e il meccanismo di persistenza o accesso corrispondente, senza esporre ai layer superiori il protocollo, il formato o la tecnologia usata.

I service non importano mai direttamente gli adapter: ricevono i contratti del Layer 2 tramite dependency injection al momento della costruzione dell'applicazione.

---

## 8. Livello Service

I servizi sono il cuore applicativo: orchestrano i use case coordinando repository e oggetti di dominio. Tutto ciò che riguarda la logica "come si fa" risiede qui; i frontend si limitano a invocare i servizi senza prendere decisioni di business.

### 8.1 MissionService

Gestisce il blueprint della missione. Non gestisce più assegnazioni né stato: queste responsabilità sono delegate ad `AssignmentService`.

| Metodo | Ritorna | Descrizione |
|---|---|---|
| `create(title, desc, objectives)` | `MissionDTO` | Crea il blueprint della missione con obiettivi e attività (unico punto in cui obiettivi/attività vengono definiti) |
| `get(id)` | `MissionDTO` | Recupera il blueprint per ID |
| `list(filters)` | `List[MissionDTO]` | Lista i blueprint con filtri facoltativi (titolo) |
| `delete(mission_id)` | — | Elimina il blueprint |

> Il blueprint è **immutabile dopo la creazione**: non esiste alcun metodo per aggiungere o modificare obiettivi/attività a posteriori.

### 8.2 AssignmentService

Gestisce il ciclo di vita dei `MissionAssignment`. È il service principale per le operazioni operative: crea assegnazioni replicando il blueprint, avanza gli stati, e fornisce il punto di delega verso `ActivityService` per la gestione delle attività interne.

Dipende da `MissionAssignmentRepository`, `MissionRepository`, `PersonRepository`, `GroupRepository`, `ActivityService` e `PluginRegistry`.

| Metodo | Ritorna | Descrizione |
|---|---|---|
| `create(mission_id, assignee_type, assignee_id)` | `AssignmentDTO` | Verifica la `AssignmentPolicy` della missione (limiti `max_total` e `max_concurrent`), valida l'assegnatario se fornito tramite `PersonRepository.exists()` o `GroupRepository.exists()`, replica il blueprint e crea il `MissionAssignment` con stato `ASSIGNED` se l'assegnatario è fornito, `UNASSIGNED` altrimenti |
| `assign(assignment_id, assignee_type, assignee_id)` | `AssignmentDTO` | Imposta l'assegnatario su un `MissionAssignment` in stato `UNASSIGNED`, valida tramite il repository corrispondente e lo porta a `ASSIGNED` |
| `get(id)` | `AssignmentDTO` | Recupera un `MissionAssignment` per ID |
| `list(mission_id, filters)` | `List[AssignmentDTO]` | Lista gli assignment di una missione con filtri facoltativi (stato, assegnatario) |
| `update_status(assignment_id, status)` | `AssignmentDTO` | Avanza lo stato rispettando la macchina a stati |
| `delete(assignment_id)` | — | Elimina l'assignment |

### 8.3 ActivityService

Gestisce il ciclo di vita delle attività all'interno di un `MissionAssignment`. Le attività non vengono create in modo autonomo: nascono all'interno di `AssignmentService.create()` durante la replica del blueprint. I metodi esposti gestiscono assegnazione, avanzamento di stato e consultazione.

Dipende da `ActivityRepository`, `ObjectiveRepository`, `MissionAssignmentRepository`, `PersonRepository` e `GroupRepository` (per verificare esistenza e perimetro degli assegnatari) e `PluginRegistry`.

| Metodo | Ritorna | Descrizione |
|---|---|---|
| `get(id)` | `ActivityDTO` | Recupera un'attività per ID |
| `assign_to(activity_id, person_id)` | `ActivityDTO` | Aggiunge un assegnatario all'attività (verifica che appartenga al gruppo dell'assignment o sia la persona diretta); se l'attività era `UNASSIGNED`, la porta automaticamente ad `ASSIGNED`; restituisce l'attività aggiornata |
| `unassign(activity_id, person_id)` | `ActivityDTO` | Rimuove l'assegnazione; restituisce l'attività aggiornata |
| `update_status(activity_id, status)` | `ActivityDTO` | Avanza lo stato dell'attività; se porta la Activity a `IN_PROGRESS` e il `MissionAssignment` padre è `ASSIGNED`, porta automaticamente il padre a `IN_PROGRESS`; se porta la Activity a `FAILED` e il padre non è ancora terminale, porta automaticamente il padre a `FAILED` |
| `list_by_objective(objective_id)` | `List[ActivityDTO]` | Lista le attività di un Objective |

### 8.4 BadgeService

Gestisce la creazione delle definizioni di badge e la creazione dei `BadgeAward` verso `MissionAssignment` o attività completati, con propagazione automatica agli assegnatari.

| Metodo | Ritorna | Descrizione |
|---|---|---|
| `create(name, desc, image_url)` | `BadgeDTO` | Crea una nuova definizione di badge riutilizzabile |
| `get(id)` | `BadgeDTO` | Recupera una definizione di badge per ID |
| `list()` | `List[BadgeDTO]` | Lista tutte le definizioni di badge |
| `award_to_assignment(badge_id, assignment_id)` | `BadgeAwardDTO` | Crea un `BadgeAward` per un `MissionAssignment` completato; restituisce badge, target, timestamp e conteggio destinatari |
| `award_to_activity(badge_id, activity_id)` | `BadgeAwardDTO` | Crea un `BadgeAward` per un'attività completata; restituisce badge, target, timestamp e conteggio destinatari |
| `list_by_person(person_id)` | `List[BadgeAwardDTO]` | Lista le assegnazioni di badge ricevute da una persona |

La propagazione del badge dipende dal tipo di target:

- per un `MissionAssignment` di tipo `GROUP`: interroga `PersonRepository.get_by_group()` per ottenere i membri correnti del gruppo;
- per un `MissionAssignment` di tipo `PERSON`: il destinatario è direttamente `assignee_id`;
- per un'`Activity`: i destinatari sono tutti gli assegnatari correnti dell'attività (campo `assignees`).

In tutti i casi il service itera su ciascun destinatario, registra la propagazione in `BadgeAwardRepository` e restituisce un `BadgeAwardDTO` con il conteggio dei destinatari raggiunti.

### 8.5 PersonService

Gestisce il ciclo di vita di `Person` e `Group` nel dominio. È il service dedicato alla **gestione degli utenti**: creazione, modifica e rimozione di operatori e gruppi.

Dipende da `PersonRepository`, `GroupRepository` e `PluginRegistry` (opzionale).

**Operazioni su Person:**

| Metodo | Ritorna | Descrizione |
|---|---|---|
| `add(nicknames)` | `PersonDTO` | Crea una nuova `Person` con almeno un nickname; il profilo ACL nasce al minimo privilegio |
| `update(id, nicknames?)` | `PersonDTO` | Aggiorna i nicknames di una `Person` esistente |
| `set_acl_profile(id, acl_level?, acl_groups?)` | `PersonDTO` | Assegna livello e/o gruppi del profilo ACL — operazione riservata `MANAGE_PROFILES` ([§10.11](#1011-gestione-delle-acl-e-prevenzione-dellescalation)) |
| `remove_acl_group(id, group)` | `PersonDTO` | Toglie la persona da un singolo gruppo ACL |
| `remove(id)` | — | Rimuove la `Person` dal dominio |
| `get(id)` | `PersonDTO` | Recupera una `Person` per ID |
| `list(filters)` | `List[PersonDTO]` | Lista le persone con filtri facoltativi |
| `list_by_group(group_id)` | `List[PersonDTO]` | Lista le persone associate a un gruppo |

**Operazioni su Group:**

| Metodo | Ritorna | Descrizione |
|---|---|---|
| `add_group(name?)` | `GroupDTO` | Crea un nuovo `Group` nel dominio |
| `update_group(group_id, name?, zone_type?, zone_description?)` | `GroupDTO` | Modifica nome e dati di zona di un `Group` |
| `remove_group(group_id)` | — | Rimuove un `Group` dal dominio |
| `get_group(group_id)` | `GroupDTO` | Recupera un `Group` per ID |
| `list_groups()` | `List[GroupDTO]` | Lista tutti i gruppi |
| `add_group_member(group_id, person_id)` | — | Aggiunge una persona a un `Group` di dominio |
| `remove_group_member(group_id, person_id)` | — | Rimuove una persona da un `Group` di dominio |

`PersonService` non modifica le entità usate dagli assignment in corso: la rimozione di una persona non invalida retroattivamente gli assignment già creati. I frontend espongono `PersonService` tramite `PersonRouter` (REST) e `PersonCommands` (CLI).

### 8.6 AclService

Gestisce le `AclEntry` del sistema ACL — la *gestione* delle regole, non la decisione (che vive in `AuthorizationPolicy`, [§10.9](#109-architettura-porte-policy-service)).

| Metodo | Ritorna | Descrizione |
|---|---|---|
| `list_entries(resource_type, resource_id, operator_id)` | `List[AclEntryDTO]` | Entry di una risorsa (richiede `MANAGE_ACL` su di essa) |
| `list_all_entries(operator_id)` | `List[AclEntryDTO]` | Tutte le entry (richiede `MANAGE_ACL` su `SYSTEM:global`) |
| `create_entry(...)` / `update_entry(...)` / `delete_entry(...)` | `AclEntryDTO` | CRUD delle entry, con validazione INV-1..INV-5 e autoprotezione `MANAGE_ACL` |
| `on_resource_created(resource, creator_id)` | — | Seeding automatico del creatore secondo la `SeedingPolicy` ([§10.7](#107-seeding-automatico-assenza-di-ownership)); invocato dai service di dominio nella stessa transazione della creazione |
| `on_resource_deleted(resource)` | — | Cascata: elimina le entry della risorsa rimossa |
| `ensure_bootstrap_entries(read, write, admin)` | — | Semina le soglie di default, una sola volta su repository vuoto ([§10.8](#108-bootstrap-e-soglie-di-default)) |

I service di dominio (`MissionService`, `AssignmentService`, `BadgeService`) notificano ad `AclService` creazione/eliminazione delle risorse ma **non eseguono mai controlli di autorizzazione**: l'enforcement resta al confine ([§10.10](#1010-enforcement-al-confine-per-frontend)).

### 8.7 DTO (Data Transfer Objects)

I service non restituiscono mai entità di dominio direttamente ai frontend: le serializzano in DTO prima di restituirle. I DTO espongono solo i campi necessari alla presentazione, sono privi di metodi comportamentali e isolano i frontend dalla struttura interna delle entità di dominio.

| DTO | Service | Campi principali |
|---|---|---|
| `MissionDTO` | `MissionService` | `id`, `title`, `description`, `assignment_policy`, `objectives: List[ObjectiveDTO]` |
| `AssignmentDTO` | `AssignmentService` | `id`, `mission_id`, `assignee_type`, `assignee_id`, `status`, `outcome: Optional[str]`, `objectives: List[ObjectiveDTO]`, `badge_award: Optional[BadgeAwardDTO]` |
| `ObjectiveDTO` | trasversale | `id`, `description`, `outcome: Optional[str]`, `activities: List[ActivityDTO]` |
| `ActivityDTO` | `ActivityService` | `id`, `title`, `description`, `status`, `assignees: List[UUID]`, `badge_award: Optional[BadgeAwardDTO]` |
| `BadgeDTO` | `BadgeService` | `id`, `name`, `description`, `image_url: Optional[str]` |
| `BadgeAwardDTO` | `BadgeService` | `id`, `badge: BadgeDTO`, `target_type: str`, `target_id: UUID`, `recipients: List[UUID]`, `recipients_count: int`, `awarded_at` |
| `PersonDTO` | `PersonService` | `id`, `nicknames: List[str]`, `primary_nickname: str`, `acl_level: int`, `acl_groups: List[str]` |
| `GroupDTO` | `PersonService` | `id` |
| `AclEntryDTO` | `AclService` | `id`, `subject_type`, `subject_id?`, `resource_type`, `resource_id`, `operation`, `permission`, `level?`, `group?`, `profile_join`, `subject_join` |

`outcome` in `AssignmentDTO` e `ObjectiveDTO` è il valore calcolato da `compute_outcome()` sull'entità di dominio corrispondente: viene popolato quando le attività figlio hanno raggiunto uno stato terminale, altrimenti è `None`. `BadgeDTO` descrive la definizione riutilizzabile del badge; `BadgeAwardDTO` descrive una specifica assegnazione indipendente.

---

## 9. Livello Frontend

I tre frontend condividono la stessa interfaccia verso i servizi. L'unica logica presente in questo livello riguarda la deserializzazione dell'input (parsing HTTP body, argomenti CLI), il controllo ACL, la serializzazione dell'output (JSON, tabelle ASCII) e la mappatura degli errori di dominio in codici HTTP o messaggi CLI.

### 9.1 REST API JSON

Frontend asincrono che espone endpoint HTTP con payload e risposte in JSON puro. Ogni router incapsula le route di un'entità; gli handler sono asincroni per supportare alta concorrenza su I/O.

`AuthMiddleware` identifica l'operatore corrente tramite `OperatorIdentityProvider.get_current_operator()` (assente → profilo anonimo implicito), mappa la richiesta su una coppia `(Operation, ResourceRef)` e interroga `AuthorizationPolicy.is_allowed()`: se la decisione è DENIED risponde 401 (richiedente anonimo, con `WWW-Authenticate`) o 403 (autenticato). Le route `/api/acl/*` e il cambio password sono autorizzati dal service/router ([§10.10](#1010-enforcement-al-confine-per-frontend)). `ErrorHandler` mappa le eccezioni di dominio in risposte HTTP: 404 per `NotFoundError`, 400 per `ValidationError`, 403 per `ACLError`/`ForbiddenError`, 409 per `StatusTransitionError`, 422 per `OperationAbortedError`.

**Blueprint missione:**

| Metodo | URL | Descrizione |
|---|---|---|
| `GET` | `/missions` | Lista blueprint missioni |
| `POST` | `/missions` | Crea un nuovo blueprint di missione |
| `GET` | `/missions/<id>` | Dettaglio blueprint |
| `DELETE` | `/missions/<id>` | Elimina blueprint |
| `GET` | `/missions/<id>/objectives` | Lista obiettivi del blueprint (sola lettura: il blueprint è immutabile) |
| `GET` | `/missions/<id>/assignments` | Lista assignment della missione |
| `POST` | `/missions/<id>/assignments` | Crea un `MissionAssignment` (payload: `assignee_type`, `assignee_id`) |

**Assignment:**

| Metodo | URL | Descrizione |
|---|---|---|
| `GET` | `/assignments/<id>` | Dettaglio `MissionAssignment` |
| `POST` | `/assignments/<id>/assign` | Imposta l'assegnatario su un `MissionAssignment` in stato `UNASSIGNED` (payload: `assignee_type`, `assignee_id`) |
| `PUT` | `/assignments/<id>/status` | Aggiorna stato dell'assignment |
| `POST` | `/assignments/<id>/badge` | Crea un `BadgeAward` (solo se COMPLETED) |
| `GET` | `/assignments/<id>/objectives` | Lista obiettivi dell'assignment |

**Attività e badge:**

| Metodo | URL | Descrizione |
|---|---|---|
| `GET` | `/activities/<id>` | Dettaglio attività |
| `PUT` | `/activities/<id>/status` | Aggiorna stato attività |
| `POST` | `/activities/<id>/assign` | Assegna attività a persona (vincolo: membro del gruppo o persona diretta) |
| `DELETE` | `/activities/<id>/assign` | Rimuove l'assegnazione di una persona all'attività |
| `POST` | `/activities/<id>/badge` | Crea un `BadgeAward` per attività |
| `GET` | `/objectives/<id>/activities` | Lista le attività di un Objective |
| `GET/POST` | `/badges` | Lista / Crea badge |
| `GET` | `/badges/<id>` | Dettaglio badge |

**Gestione persone e gruppi:**

| Metodo | URL | Descrizione |
|---|---|---|
| `GET` | `/persons` | Lista tutte le persone |
| `POST` | `/persons` | Crea una nuova persona (payload: `nicknames`; il profilo ACL nasce al minimo privilegio) |
| `GET` | `/persons/<id>` | Dettaglio persona |
| `PUT` | `/persons/<id>` | Aggiorna parzialmente una persona |
| `DELETE` | `/persons/<id>` | Rimuove una persona |
| `GET` | `/groups` | Lista tutti i gruppi |
| `POST` | `/groups` | Crea un nuovo gruppo |
| `GET` | `/groups/<id>` | Dettaglio gruppo |
| `DELETE` | `/groups/<id>` | Rimuove un gruppo |
| `GET` | `/groups/<id>/members` | Lista le persone associate al gruppo |
| `GET` | `/persons/<id>/badges` | Lista le assegnazioni di badge ricevute da una persona |

**Sistema ACL:**

| Metodo | URL | Descrizione |
|---|---|---|
| `GET` | `/acl/entries[?resource_type=&resource_id=]` | Lista le `AclEntry` (tutte, o di una risorsa) — autoprotetta da `MANAGE_ACL` |
| `POST` | `/acl/entries` | Crea una entry (payload: `resource_type`, `resource_id`, `operation`, `permission`, `subject_id?`, `level?`, `group?`, `profile_join?`, `subject_join?`) |
| `PATCH` | `/acl/entries/<id>` | Aggiorna permesso/criteri di una entry |
| `DELETE` | `/acl/entries/<id>` | Elimina una entry |
| `PUT` | `/persons/<id>/acl` | Assegna il profilo ACL (payload: `acl_level?`, `acl_groups?`) — `MANAGE_PROFILES` su `SYSTEM:global` |

### 9.2 Web App asincrona

Frontend asincrono che espone l'applicazione come interfaccia web navigabile. Tutte le route sono asincrone, garantendo alta concorrenza su I/O senza threading.

La caratteristica distintiva rispetto al frontend REST è la presenza di `RealtimeNotifier`: mantiene un set di connessioni aperte e notifica in tempo reale tutti i client connessi quando lo stato di un `MissionAssignment` o di un'attività cambia. Questo permette a dashboard operative di ricevere aggiornamenti push senza polling.

L'`ACLMiddleware` implementa la stessa logica di `AuthMiddleware`: recupera l'operatore tramite `OperatorIdentityProvider` (assente → profilo anonimo), mappa l'endpoint Quart su `(Operation, ResourceRef)` e interroga `AuthorizationPolicy.is_allowed()`; su DENIED risponde con redirect al login (anonimo, pagine), 401 (anonimo, mutazioni) o 403 (autenticato). La pagina `/acl` amministra profili ed entry ([§10.10](#1010-enforcement-al-confine-per-frontend)).

### 9.3 Interfaccia a riga di comando (CLI)

Frontend interattivo da terminale. All'avvio, il bootstrap CLI costruisce i service condivisi e configura l'adapter di identità della CLI, che può stabilire l'operatore corrente tramite `MISSIONMANAGER_OPERATOR_ID` e `PersonRepository.get()`. I gruppi di comandi (`mission`, `assignment`, `activity`, `badge`, `person`, `acl`) sono raggruppati sotto `CLIApp`. `OutputFormatter` centralizza la presentazione: tabelle ASCII, output JSON strutturato, messaggi di successo/errore e visualizzazione badge. Il decorator `@require_acl(operation, resource_type?, resource_param?)` è applicato a tutti i comandi core: mappa il comando su `(Operation, ResourceRef)` — risorsa concreta dall'argomento del comando, radice di tipo per gli elenchi, `SYSTEM:global` per le creazioni — e interroga la stessa `AuthorizationPolicy.is_allowed()` degli altri frontend. In modalità anonima vale il profilo anonimo implicito ([§10.3](#103-profilo-del-richiedente-e-profilo-anonimo)). Fa eccezione `create-superuser` (bootstrap del primo amministratore), che non richiede ACL ma è ammesso solo finché non esiste già un amministratore.

```
# Crea un blueprint di missione con obiettivi e attività
$ missionmanager mission create --title "Operazione Alba" --desc "..." \
    --objectives '[{"description":"Ricognizione","activities":[{"title":"Pattuglia Nord"},{"title":"Pattuglia Sud"}]},{"description":"Estrazione","activities":[{"title":"Trasporto unità"}]}]'

# Assegna la missione a una persona (crea un MissionAssignment)
$ missionmanager assignment create --mission-id <uuid> --assignee-type PERSON --assignee-id <uuid>

# Assegna la missione a un gruppo (crea un MissionAssignment)
$ missionmanager assignment create --mission-id <uuid> --assignee-type GROUP --assignee-id <uuid>

# Imposta l'assegnatario su un MissionAssignment creato in stato UNASSIGNED
$ missionmanager assignment assign <assignment-uuid> --type PERSON --id <uuid>
$ missionmanager assignment assign <assignment-uuid> --type GROUP --id <uuid>

# Aggiorna lo stato di un assignment
$ missionmanager assignment status <assignment-uuid> IN_PROGRESS

# Crea un BadgeAward per un assignment completato
$ missionmanager badge award-assignment --assignment-id <assignment-uuid> --badge-id <badge-uuid>

# Gestione persone
$ missionmanager person add --nickname "Alpha" --nickname "α"
$ missionmanager person update <person-uuid> --nickname "Bravo"
$ missionmanager person set-acl <person-uuid> --acl-level 50 --acl-group commanders
$ missionmanager person remove <person-uuid>
$ missionmanager person list
$ missionmanager person group-members <group-uuid>

# Gestione delle regole ACL (entry)
$ missionmanager acl list
$ missionmanager acl add --resource-type MISSION --resource-id "*" \
    --operation VIEW --permission ALLOW --group viewers
$ missionmanager acl remove <entry-uuid>

# Gestione gruppi
$ missionmanager person group-add --name "Squadra Nord"
$ missionmanager person group-update <group-uuid> --name "Squadra Nord 2"
$ missionmanager person group-remove <group-uuid>
$ missionmanager person group-list
$ missionmanager person group-member-add <group-uuid> <person-uuid>
$ missionmanager person group-member-remove <group-uuid> <person-uuid>
```

### 9.4 Autenticazione e verifica delle credenziali

L'**autenticazione** (*chi sei*) è distinta dall'**autorizzazione** (*cosa puoi fare*, [§10](#10-sistema-acl-e-autorizzazione)): stabilisce l'identità del richiedente, che i frontend trasportano poi come `Person`/`Profile` verso il confine ACL. Backend selezionato in configurazione (`security.auth.backend`), coerente con quello delle persone (`local` con `local`, `oidc` con `oidc`):

- **Locale** — l'operatore prova la propria identità con nickname + password; il sistema verifica l'hash e rilascia un token di sessione applicativo. Le credenziali locali sono un contratto di dominio (porta `CredentialRepository`) separato dall'anagrafica `Person`, così una `Person` può esistere senza credenziali.
- **OIDC** — l'identità è delegata a un identity provider esterno (Authentik/Keycloak) via Authorization Code + PKCE; l'applicazione non custodisce password.

Il backend locale applica quattro **proprietà di sicurezza**, indipendenti dal frontend:

1. **Verifica a tempo costante** — il costo della verifica non dipende dall'esistenza del nickname, così i tempi di risposta non rivelano quali account esistano (difesa contro l'enumerazione degli utenti).
2. **Policy di robustezza della password** — lunghezza minima sempre applicata; requisiti sulle classi di caratteri (maiuscola, cifra, carattere speciale) attivabili in configurazione. Regola valutata alla *impostazione* della password, non al login.
3. **Blocco dell'account** — dopo un numero configurabile di tentativi falliti consecutivi l'account è bloccato per una finestra temporizzata; una nuova password sblocca sempre l'account. Il conteggio dei fallimenti è uno stato che **deve persistere anche quando il tentativo fallisce** (non è annullabile dal fallimento stesso).
4. **Cambio password forzato** (`must_change_password`) — una password impostata da un amministratore *per conto di* un altro operatore deve essere cambiata al primo accesso; il cambio self-service, invece, non impone nulla. Al primo accesso i frontend dirottano l'operatore sul cambio password prima di consentire ogni altra operazione.

Il **primo amministratore** è creato fuori banda (setup web o `person create-superuser`) ed è l'unico flusso anonimo ammesso, valido solo finché non esiste già un amministratore ([§10.8](#108-bootstrap-e-soglie-di-default)). Gli endpoint di autenticazione (login/logout/setup/callback OIDC/cambio password forzato) sono pubblici per definizione.

---

## 10. Sistema ACL e autorizzazione

### 10.1 Principi e decisioni

Il sistema ACL definisce **chi** (Soggetto, qualificato da livello e/o gruppo) può eseguire **quale azione** (Operazione) su **quale risorsa** (Risorsa), con quale **esito** (Permesso: consenti o nega). L'unità atomica è la **`AclEntry`**.

Principi guida:

1. **Autorizzazione dichiarativa a entry.** Le decisioni derivano esclusivamente dalla valutazione di `AclEntry` persistite; nessuna regola è cablata nel codice di dominio.
2. **Qualificazione per livello e gruppo.** Ogni entry è qualificata da un **livello** e/o da un **gruppo**, valutati contro il *profilo* del richiedente.
3. **Decisione pura e stateless.** La logica di decisione (`AuthorizationPolicy`) è una funzione pura che consulta la persistenza solo tramite porte astratte.
4. **Controllo al confine.** L'enforcement avviene al confine del sistema (middleware REST/Web, ingresso comandi CLI), mai dentro le entità di dominio o i service operativi.
5. **Indipendenza dall'implementazione.** Il modello è espresso tramite porte; persistenza, identità e gerarchia delle risorse sono adapter sostituibili.

Decisioni fondamentali (base normativa della sezione):

| # | Nodo | Decisione adottata |
|---|------|--------------------|
| D1 | Ruolo di livello/gruppo rispetto al Soggetto | **Criteri indipendenti combinabili**: Soggetto, Livello e Gruppo sono criteri distinti; ogni entry dichiara come combinarli (AND/OR). |
| D2 | Significato di *Operazione* e *Permesso* | **Operazione** = l'azione governata (VIEW, DELETE, …); **Permesso** = il verdetto **ALLOW** oppure **DENY**. |
| D3 | Semantica del livello e conflitti | Un requisito di livello `L` è soddisfatto da chi ha **livello ≤ L**. Con più entry applicabili la precedenza è **DENY > ALLOW > negato di default**. |
| D4 | Ambito e scoping delle risorse | **Risorsa `SYSTEM:global`**, **Soggetto PUBLIC/anonimo**, **gerarchia + ereditarietà**. **Non esiste ownership.** |
| D5 | PUBLIC vs livello/gruppo obbligatori | **Profilo anonimo implicito**: i richiedenti non autenticati ricevono `(ANON_SENTINEL, {"public"})`, così livello/gruppo sono sempre valutabili. |
| D6 | Appartenenza a gruppi | Un profilo può appartenere a **più gruppi** (`groups` è un insieme). |
| D7 | Sostituto dell'ownership | **Seeding automatico configurabile**: alla creazione di una risorsa la `SeedingPolicy` genera entry esplicite per il creatore ([§10.7](#107-seeding-automatico-assenza-di-ownership)). |
| D8 | Orientamento numerico del livello | Conseguenza di D3: **numero più basso = privilegio più alto / raggio più ampio**. |

### 10.2 Modello concettuale

Una `AclEntry` esprime una singola affermazione di autorizzazione:

```
AclEntry
  ── campi fondamentali ───────────────────────────────────────
  soggetto      : SubjectRef       ← chi (USER(id) | PUBLIC)
  risorsa       : ResourceRef      ← su cosa (tipo + id, incl. radici * e SYSTEM:global)
  operazione    : Operation        ← quale azione (VIEW, DELETE, …)
  permesso      : Permission       ← verdetto: ALLOW | DENY
  ── criteri di profilo (almeno uno obbligatorio: INV-1) ──────
  livello       : Optional[int]    ← soglia; soddisfatta se profilo.level ≤ livello
  gruppo        : Optional[str]    ← soddisfatto se gruppo ∈ profilo.groups
  ── operatori di combinazione ────────────────────────────────
  profile_join  : {OR | AND}       ← combina livello e gruppo   (default: OR)
  subject_join  : {AND | OR}       ← combina soggetto e profilo (default: AND)
```

- **Soggetto** (`SubjectRef`): `USER(id)` identifica un principale specifico; `PUBLIC` significa «nessuna restrizione di identità» (anche non autenticato), delegando la selettività ai criteri di profilo.
- **Risorsa** (`ResourceRef`): coppia *(tipo, id)*. I tipi sono quelli del dominio (`MISSION`, `ASSIGNMENT`, `OBJECTIVE`, `ACTIVITY`, `BADGE`, `PERSON`, `GROUP`) più `SYSTEM`. Tre forme di id: UUID concreto; **`*`** (radice di tipo, es. `MISSION:*` — ambito dei default per-tipo); **`global`** (la sentinella `SYSTEM:global` per le operazioni senza risorsa specifica).
- **Operazione** (`Operation`): catalogo aperto fornito dal dominio; ogni operazione dichiara `read_only`, usato da INV-2. Catalogo di MissionManager:

| Operazione | `read_only` | Risorsa su cui si valuta |
|------------|:-----------:|---|
| `VIEW`, `LIST` | ✔ | risorsa / radice di tipo (elenchi) |
| `EDIT`, `DELETE` | ✘ | risorsa |
| `ASSIGN`, `UPDATE_STATUS`, `AWARD_BADGE` | ✘ | assignment o attività |
| `MANAGE_MEMBERS` | ✘ | gruppo |
| `CREATE_ASSIGNMENT` | ✘ | la **missione** sotto cui si crea (delegabile per-missione) |
| `CREATE_MISSION`, `CREATE_BADGE`, `CREATE_PERSON`, `CREATE_GROUP` | ✘ | `SYSTEM:global` |
| `MANAGE_PROFILES` | ✘ | `SYSTEM:global` (assegnazione dei profili, [§10.11](#1011-gestione-delle-acl-e-prevenzione-dellescalation)) |
| `EXECUTE` | ✘ | `SYSTEM:global` (estensioni e mutazioni non mappate) |
| `MANAGE_ACL` | ✘ | risorsa o `SYSTEM:global`; **non ereditabile** |

- **Permesso** (`Permission`): `ALLOW` concede, `DENY` nega; `DENY` prevale nella risoluzione ([§10.5](#105-semantica-di-valutazione)).
- **Livello**: intero ≥ 0. La soglia `L` di una entry è soddisfatta da chi ha `profilo.level ≤ L` (D3/D8): un numero più basso identifica un profilo più privilegiato; su una `ALLOW` la soglia definisce *fino a quale tier* si concede, su una `DENY` *fino a quale tier* si nega. La **soglia universale** (il massimo rappresentabile, lo stesso `ANON_SENTINEL` del profilo anonimo) è soddisfatta da chiunque: è lo strumento per scrivere concessioni «legate al solo soggetto» rispettando INV-1 (usata dal seeding, [§10.7](#107-seeding-automatico-assenza-di-ownership)).
- **Gruppo**: identificatore; il criterio è soddisfatto se `gruppo ∈ profilo.groups`. Il gruppo **`"public"`** è universale (ogni profilo vi appartiene) e serve a esprimere le concessioni «a chiunque» in sola lettura restando entro INV-1.

### 10.3 Profilo del richiedente e profilo anonimo

Il profilo è il value object descritto in [§3.2](#32-profile-profilo-di-controllo-accessi): `(level, groups)`, risolto **ad ogni richiesta** tramite la porta `ProfileProvider`. I richiedenti non autenticati ricevono il profilo anonimo implicito `(ANON_SENTINEL, {"public"})` (D5): un unico percorso di valutazione, nessun ramo speciale «se anonimo». L'anonimo è tipicamente raggiunto tramite il gruppo `"public"` su operazioni di sola lettura, mai tramite il livello.

### 10.4 Invarianti strutturali

Applicate da `AclEntry.validate()` **prima** della persistenza, indipendentemente dal chiamante:

| ID | Invariante |
|----|------------|
| **INV-1** | Ogni entry ha **almeno uno** tra `livello` e `gruppo`. |
| **INV-2** *(adattata)* | Nessuna entry **`ALLOW` su operazione mutante** può essere soddisfatta dal **profilo anonimo**: le mutazioni richiedono un richiedente identificato. La forma originaria («PUBLIC solo su operazioni read-only») è stata generalizzata perché le **entry-soglia** di [§10.8](#108-bootstrap-e-soglie-di-default) («chiunque abbia livello ≤ L») usano il soggetto PUBLIC anche su operazioni mutanti: la formulazione adottata ne conserva l'intento di sicurezza — l'anonimo non può mutare — coprendo anche il caso `USER + subject_join=OR` con soglia universale. |
| **INV-3** | `livello` (se presente) è un intero ≥ 0; `gruppo` (se presente) è un identificatore non vuoto. |
| **INV-4** | `profile_join` e `subject_join` assumono i valori definiti; in assenza valgono i default (`OR`, `AND`). |
| **INV-5** | `soggetto = PUBLIC` **e** `subject_join = OR` è rifiutata: renderebbe vacui i criteri di profilo. |

### 10.5 Semantica di valutazione

La domanda è sempre: *«il richiedente con profilo `P` può eseguire l'operazione `O` sulla risorsa `R`?»* → `is_allowed(principal, O, R) → bool`.

**Match di una entry** (`AclEntry.matches`):

```
subjectMatch = (soggetto = PUBLIC) OR (soggetto = USER(id) AND principal = id)
levelMatch   = profilo.level ≤ livello          (solo se livello presente)
groupMatch   = gruppo ∈ profilo.groups          (solo se gruppo presente)

profilePart  = profile_join sui predicati presenti (OR → almeno uno; AND → tutti)
matches      = subject_join su (subjectMatch, profilePart)
```

Casi tipici (con `subject_join = AND` di default):

| soggetto | livello | gruppo | join | Significato |
|----------|:-------:|:------:|:----:|---|
| `PUBLIC` | — | `"public"` | OR | Chiunque, anche anonimo (sola lettura, INV-2) |
| `PUBLIC` | `≤ L` | — | OR | Chiunque abbia livello ≤ L (le entry-soglia del bootstrap) |
| `PUBLIC` | `≤ L` | `G` | OR | Livello ≤ L **oppure** gruppo G |
| `PUBLIC` | `≤ L` | `G` | AND | Livello ≤ L **e** gruppo G |
| `USER(a)` | `≤ L` | — | subj=AND | La persona `a`, solo se ha anche livello ≤ L |
| `USER(a)` | universale | — | subj=AND | La persona `a`, incondizionatamente (forma del seeding) |

**Algoritmo di risoluzione** (in `AuthorizationPolicy`):

1. **Entry proprie.** Si caricano le entry di `(R, O)`. Se esistono, decidono da sole: si filtrano per match e si applica la precedenza — **se c'è una `DENY` matchante → DENIED; altrimenti se c'è una `ALLOW` matchante → ALLOWED; altrimenti → DENIED (default deny)**. Nessun fallback ai padri.
2. **Ereditarietà.** Se `R` non ha entry proprie per `O` (e `O` è ereditabile — `MANAGE_ACL` non lo è), si valuta ricorsivamente ciascun **padre** di `R` con **OR permissiva**: si concede se almeno un padre concede; una `DENY` su un padre non blocca la concessione di un altro.
3. **Default deny.** Senza entry matchanti in tutta la catena, l'esito è DENIED. Non esiste alcun gradino di ownership (D4).

```
        entry proprie di (O, R)?
          │sì                     │no
   c'è un DENY matchante?    O ereditabile?
          │sì → DENIED            │no → DENIED
          │no                     │sì
   c'è un ALLOW matchante?   qualche padre concede?
          │sì → ALLOWED           │sì → ALLOWED
          │no → DENIED            │no → DENIED
```

### 10.6 Gerarchia delle risorse e ambiti

La relazione padre→figlio è fornita dalla porta `ResourceHierarchyProvider`. In MissionManager la catena strutturale segue il dominio, e ogni risorsa concreta risale infine alla **radice del proprio tipo**, dove il bootstrap semina le soglie di default:

```
ACTIVITY:<id> → OBJECTIVE:<id> → ASSIGNMENT:<id> → MISSION:<id> → MISSION:*
                       └───────────(blueprint)──→ MISSION:<id> ──┘
BADGE:<id>  → BADGE:*        PERSON:<id> → PERSON:*        GROUP:<id> → GROUP:*
ASSIGNMENT:* │ OBJECTIVE:* │ ACTIVITY:*  → MISSION:*   (albero operativo)
SYSTEM:global → nessun padre          radici di tipo → nessun padre
```

`MISSION:*` è quindi la radice dell'intero albero operativo: una entry su di essa governa per ereditarietà missioni, assegnazioni, obiettivi e attività prive di entry proprie. L'ereditarietà è **unidirezionale** (figlio ← padre) e **incapsulata nella policy**: il chiamante invoca sempre `is_allowed(…, ResourceRef(figlio))`.

**Ambito di sistema.** Le operazioni senza risorsa specifica (creazioni, `MANAGE_PROFILES`, `EXECUTE`, privilegi globali) sono valutate su `SYSTEM:global`, con le stesse regole di match e precedenza: è il punto in cui il modello esprime le **regole per-operazione** («per eseguire X serve livello ≤ L o gruppo G» = una entry `ALLOW X` su `SYSTEM:global`). Eccezione deliberata: `CREATE_ASSIGNMENT` è valutata sulla **missione** sotto cui si crea l'assegnazione, così la creazione è delegabile per-missione via entry (con fallback ereditato su `MISSION:*`).

### 10.7 Seeding automatico (assenza di ownership)

L'**ownership non esiste** (D4): non c'è un canale di accesso implicito garantito al creatore; ogni accesso deriva da entry esplicite. Con il default-deny, però, una risorsa appena creata resterebbe amministrabile solo dal tier amministrativo. Il divario è colmato dal **seeding automatico** (D7):

- alla creazione di una risorsa, `AclService.on_resource_created(resource, creator)` applica la **`SeedingPolicy`** configurata e materializza le entry iniziali del creatore, **nella stessa transazione** della creazione;
- la policy è **attivabile/disattivabile** (`acl.seeding_enabled`) e parametrizzata **per tipo di risorsa**;
- la forma dell'entry seminata è `ALLOW <op> USER(creatore)` con la **soglia universale** (INV-1 rispettata): «il creatore, incondizionatamente»;
- le entry seminate sono **ordinarie**: soggette a INV-1..INV-5 e alla precedenza, e in seguito modificabili o **revocabili** via `MANAGE_ACL` — è la differenza sostanziale con l'ownership.

Parametrizzazione di MissionManager: per `MISSION`, `ASSIGNMENT` e `BADGE` viene seminato il solo **`MANAGE_ACL`**. Il creatore ottiene così il controllo (revocabile) dell'ACL della propria risorsa — può restringerla o condividerla aggiungendo entry — senza alterarne la visibilità di default, che resta governata dalle soglie ereditate dalle radici di tipo. Seminare anche `VIEW`/`DELETE` (il default suggerito dal modello generale) renderebbe ogni nuova risorsa *privata* per costruzione, perché le entry proprie sopprimono l'ereditarietà ([§10.5](#105-semantica-di-valutazione)); la scelta è documentata e modificabile via `SeedingPolicy`.

### 10.8 Bootstrap e soglie di default

Il sistema **nasce senza entry** e in tale stato **nega tutto**. Al primo avvio (repository vuoto) `AclService.ensure_bootstrap_entries()` semina lo stato iniziale coerente come **entry-soglia** `ALLOW <op> PUBLIC level≤L`, con tre soglie configurabili (`acl.read_threshold`=100, `acl.write_threshold`=50, `acl.admin_threshold`=0):

| Ambito | Operazioni → soglia |
|---|---|
| `MISSION:*` (albero operativo) | `VIEW`, `LIST` → lettura; `DELETE`, `CREATE_ASSIGNMENT`, `ASSIGN`, `UPDATE_STATUS`, `AWARD_BADGE` → scrittura; `MANAGE_ACL` → amministrazione |
| `BADGE:*` | `VIEW`, `LIST` → lettura; `MANAGE_ACL` → amministrazione |
| `PERSON:*` | `VIEW`, `LIST` → lettura; `EDIT`, `DELETE`, `MANAGE_ACL` → amministrazione |
| `GROUP:*` | `VIEW`, `LIST` → lettura; `DELETE`, `MANAGE_MEMBERS`, `MANAGE_ACL` → amministrazione |
| `SYSTEM:global` | `VIEW`, `LIST` → lettura; `CREATE_MISSION`, `CREATE_BADGE`, `EXECUTE` → scrittura; `CREATE_PERSON`, `CREATE_GROUP`, `MANAGE_PROFILES`, `MANAGE_ACL` → amministrazione |

Il primo amministratore (setup web o `person create-superuser`) riceve **livello 0**: soddisfa ogni soglia, incluso il `MANAGE_ACL` amministrativo, rendendo il sistema amministrabile. Dopo il bootstrap le soglie sono normali entry, ispezionabili e modificabili come tutte le altre; le tre soglie di configurazione servono **solo** alla semina iniziale.

### 10.9 Architettura: porte, policy, service

```
┌──────────────────────────────────────────────────────────────┐
│  Confine / Enforcement (AuthMiddleware, ACLMiddleware,       │
│  require_acl) — chiama is_allowed e mappa l'esito            │
└───────────────────────────────┬──────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────┐
│  Application — AclService                                    │
│  gestione entry (INV-1..5) + seeding + bootstrap             │
│  autoprotetta da MANAGE_ACL                                  │
└───────────────────────────────┬──────────────────────────────┘
                                │ usa
┌───────────────────────────────▼──────────────────────────────┐
│  Policy — AuthorizationPolicy (decisione pura, stateless)    │
│  is_allowed(principal, operation, resource) → bool           │
└───────────────────────────────┬──────────────────────────────┘
                                │ dipende dai contratti
┌───────────────────────────────▼──────────────────────────────┐  ┌───────────────┐
│  Ports (Layer 2)                                             │◄─┤ Adapters (L3) │
│  AclEntryRepository │ ProfileProvider │                      │  │ persistenza,  │
│  ResourceHierarchyProvider                                   │  │ identità,     │
└───────────────────────────────┬──────────────────────────────┘  │ gerarchia     │
                                │                                 └───────────────┘
┌───────────────────────────────▼──────────────────────────────┐
│  Domain (nucleo) — AclEntry │ SubjectRef │ ResourceRef       │
│  Operation │ Permission │ Profile │ JoinOp │ INV-1..5        │
└──────────────────────────────────────────────────────────────┘
```

- **`AuthorizationPolicy`** incapsula interamente match, precedenza, ereditarietà e ambito di sistema; non possiede stato e consulta la persistenza solo tramite le porte.
- **`AclService`** orchestra la *gestione* delle entry ([§8.6](#86-aclservice)): ogni mutazione è a sua volta autorizzata da `MANAGE_ACL` sulla risorsa interessata **oppure** da `MANAGE_ACL` su `SYSTEM:global` (il tier amministrativo è la chiave mastra, dato che `MANAGE_ACL` non eredita). Non restituisce mai entità grezze: serializza in `AclEntryDTO`.
- Le direzioni delle dipendenze seguono la regola dei layer: enforcement → service/policy → porte → dominio; gli adapter implementano le porte e sono iniettati al bootstrap.

### 10.10 Enforcement al confine per frontend

Ogni frontend mappa le proprie richieste su coppie `(Operation, ResourceRef)` e interroga la stessa `AuthorizationPolicy`:

| Frontend | Mappatura | Esito DENIED |
|---|---|---|
| REST API | `(route, metodo)` → operazione + risorsa dal path (`/api/missions/<id>` → `VIEW MISSION:<id>`); collezioni → radici di tipo; creazioni → `SYSTEM:global` (assegnazioni → `MISSION:<id>`); route non mappate (estensioni): letture → `VIEW SYSTEM`, mutazioni → `EXECUTE SYSTEM` | 401 + `WWW-Authenticate` (anonimo), 403 (autenticato) |
| Web App | endpoint Quart → operazione + risorsa dai view-args; i **form di creazione** sono mappati sull'operazione a cui conducono (chi non può creare non vede il form) | redirect a `/login` (anonimo, pagine), 401 (anonimo, mutazioni), 403 (autenticato) |
| CLI | `@require_acl(operation, resource_type?, resource_param?)` su ogni comando core; comandi d'estensione → `EXECUTE SYSTEM` | messaggio su stderr, exit code non-zero |

Casi particolari, autorizzati dal service o dal router anziché dal middleware:

- **Gestione entry** (`/api/acl/*`, web `/acl/entries*`, CLI `acl *`): autoprotezione `MANAGE_ACL` in `AclService` — così un creatore delegato dal seeding può gestire la *propria* risorsa senza appartenere a un tier globale; il middleware richiede la sola autenticazione.
- **Cambio password** (`PUT /api/auth/password`): self-service per la propria password; per quella altrui il router richiede `EDIT` sulla risorsa `PERSON` interessata via `is_allowed` — l'unico confronto «operatore corrente vs. risorsa» del sistema. Il cambio *per conto di altri* marca la credenziale come `must_change_password` (cambio forzato al primo accesso, [§9.4](#94-autenticazione-e-verifica-delle-credenziali)); il cambio self-service azzera il flag.
- Il richiedente **anonimo** non è più un errore immediato: procede con il profilo anonimo implicito, e le eventuali entry `PUBLIC` di sola lettura possono concedergli l'accesso (es. una vetrina pubblica delle missioni si ottiene con `ALLOW VIEW/LIST` su `MISSION:*` con `group="public"`).

### 10.11 Gestione delle ACL e prevenzione dell'escalation

La modifica delle entry è essa stessa governata dal sistema (`MANAGE_ACL`). Per prevenire l'innalzamento di privilegi:

1. **`MANAGE_ACL` scoperto conservativamente**: le entry che lo concedono usano criteri restrittivi (al bootstrap: soglia amministrativa; via seeding: il solo creatore sulla singola risorsa).
2. **`MANAGE_ACL` non ereditabile**: la gestione delle entry di una risorsa è un atto esplicito su quella risorsa; il tier amministrativo vi accede tramite `MANAGE_ACL` su `SYSTEM:global` ([§10.9](#109-architettura-porte-policy-service)), non per discesa gerarchica.
3. **Assegnazione dei profili fuori dal catalogo delegabile**: modificare `Profile` (livello/gruppi di una persona) è l'operazione riservata `MANAGE_PROFILES` su `SYSTEM:global`, distinta da `EDIT`/`CREATE_PERSON`: chi è delegato a creare o modificare persone **non** può auto-promuoversi assegnando profili. Per lo stesso motivo la creazione di una persona non accetta un profilo iniziale: ogni `Person` nasce al minimo privilegio.
4. **`SYSTEM:global` e radici di tipo protette**: le loro entry (i default globali) sono gestibili solo dal tier con `MANAGE_ACL` su `SYSTEM:global`, seminato al bootstrap.

### 10.12 Riepilogo autorizzazioni per operazione

Con i default di bootstrap (lettura=100, scrittura=50, amministrazione=0); ogni riga è modificabile a runtime come entry:

| Operazione applicativa | Check ACL | Default |
|---|---|---|
| Lista/visualizza missioni, assignment, attività, badge, persone, gruppi | `VIEW`/`LIST` su risorsa o radice di tipo | soglia lettura |
| Crea missione / badge | `CREATE_MISSION` / `CREATE_BADGE` su `SYSTEM:global` | soglia scrittura |
| Crea assegnazione | `CREATE_ASSIGNMENT` sulla missione | soglia scrittura (ereditata da `MISSION:*`) |
| Imposta assegnatario / stato assignment | `ASSIGN` / `UPDATE_STATUS` sull'assignment | soglia scrittura |
| Assegna/rimuovi assegnatario attività; stato attività | `ASSIGN` / `UPDATE_STATUS` sull'attività | soglia scrittura (ereditata) |
| Crea `BadgeAward` | `AWARD_BADGE` sul target | soglia scrittura |
| Crea/modifica/elimina persona; crea/elimina gruppo; membership | `CREATE_PERSON`/`EDIT`/`DELETE`/`CREATE_GROUP`/`MANAGE_MEMBERS` | soglia amministrazione |
| Assegna profilo ACL (livello/gruppi) | `MANAGE_PROFILES` su `SYSTEM:global` | soglia amministrazione |
| Gestisci entry di una risorsa | `MANAGE_ACL` sulla risorsa **o** su `SYSTEM:global` | seeding del creatore / soglia amministrazione |
| Cambia password | propria: sempre; altrui: `EDIT` sulla `PERSON` | soglia amministrazione |
| Route/comandi d'estensione | lettura: `VIEW SYSTEM`; mutazione: `EXECUTE SYSTEM` | lettura / scrittura |

Regola trasversale: in **assenza** di entry matchanti l'esito è DENIED; una `DENY` matchante prevale sempre su qualunque `ALLOW`. Gli endpoint di autenticazione (login/logout/OIDC/setup) sono pubblici per definizione; `create-superuser` è ammesso solo finché non esiste un amministratore.

### 10.13 ACLError e mappatura

Il middleware non solleva eccezioni per gli esiti DENIED: risponde direttamente secondo la tabella di [§10.10](#1010-enforcement-al-confine-per-frontend). `ForbiddenError` (dall'autoprotezione di `AclService`) e `ACLError` (errori del sottosistema, es. operatore CLI inesistente) restano nella gerarchia `MissionManagerError` e sono mappati dai frontend:

| Frontend | Risposta |
|---|---|
| REST API | HTTP 403 (`ErrorHandler`) |
| Web App | HTTP 403 JSON |
| CLI | Messaggio di errore su stderr, exit code non-zero |

## 11. Flussi operativi chiave

### 11.1 Creazione di una missione (blueprint)

Il client invia la richiesta con titolo, descrizione e lista di obiettivi; ogni obiettivo porta con sé le proprie attività. Il frontend verifica l'ACL. `MissionService.create()` valida i dati: almeno un obiettivo, almeno un'attività per obiettivo. Il `PluginRegistry` esegue gli hook `BEFORE_CREATE_MISSION` con possibilità di veto. Viene creato il blueprint `Mission` con i suoi `Objective` e `Activity` (senza stato attivo); l'intero blueprint viene persistito tramite `MissionRepository.save()`. Gli hook `AFTER_CREATE_MISSION` vengono eseguiti a creazione completata. Il service restituisce un `MissionDTO` con il blueprint appena creato, privo di stato e pronto ad essere assegnato.

### 11.2 Creazione di un MissionAssignment

Si fornisce `mission_id` e, facoltativamente, `assignee_type` (`PERSON` o `GROUP`) e `assignee_id`. `AssignmentService.create()` carica il blueprint e verifica immediatamente la `AssignmentPolicy`: se `max_total` è impostato, conta il totale storico degli assignment tramite `count_by_mission()` e solleva `ValidationError` se il limite è già raggiunto; se `max_concurrent` è impostato e la creazione include già un assegnatario, conta gli assignment operativi (`ASSIGNED`, `IN_PROGRESS`) tramite `count_active_by_mission()` e solleva `ValidationError` se il limite è raggiunto. Il `PluginRegistry` esegue quindi gli hook `BEFORE_CREATE_ASSIGNMENT` con possibilità di veto. Se l'assegnatario è fornito, viene verificata la sua esistenza tramite `PersonRepository.exists()` (se `PERSON`) o `GroupRepository.exists()` (se `GROUP`): se non trovato, `NotFoundError`. Viene replicato il blueprint: nuove istanze di `Objective` e `Activity` vengono create e associate al `MissionAssignment`, che nasce con stato `ASSIGNED` se l'assegnatario è fornito, `UNASSIGNED` altrimenti (con `assignee_type` e `assignee_id` a `None`). L'assignment viene persistito tramite `MissionAssignmentRepository.save()`. Gli hook `AFTER_CREATE_ASSIGNMENT` vengono eseguiti a creazione completata. Il service restituisce un `AssignmentDTO` con lo stato corrente e la lista degli `ObjectiveDTO` istanziati. Per assegnare un `MissionAssignment` in stato `UNASSIGNED`, si usa successivamente `AssignmentService.assign()`, che imposta l'assegnatario, ricontrolla `max_concurrent` e porta lo stato a `ASSIGNED`.

### 11.3 Aggiornamento di stato

Il service carica l'entità (`MissionAssignment` o `Activity`) e chiama `Status.can_transition_to(new_status)`: se la transizione non è consentita, viene sollevata `StatusTransitionError` prima di toccare la persistenza. Se un `MissionAssignment` viene portato a `COMPLETED`, il service verifica che l'esito aggregato sia `COMPLETED`, quindi che tutte le attività associate siano `COMPLETED`; se esistono attività ancora `UNASSIGNED`, `ASSIGNED`, `IN_PROGRESS` o `FAILED`, solleva `ValidationError` e non aggiorna lo stato. Il `PluginRegistry` esegue quindi gli hook `BEFORE_UPDATE_STATUS` con possibilità di veto. Lo stato viene aggiornato. Se l'entità aggiornata è un'`Activity` portata a `IN_PROGRESS` e il `MissionAssignment` padre è in stato `ASSIGNED`, quest'ultimo viene automaticamente portato a `IN_PROGRESS` nella stessa operazione — una singola chiamata ad `ActivityService.update_status()` produce in questo caso due transizioni di stato. Allo stesso modo, se l'`Activity` è portata a `FAILED` e il `MissionAssignment` padre non è ancora in uno stato terminale, quest'ultimo viene automaticamente portato a `FAILED` nella stessa operazione. Le modifiche (all'Activity e, se applicabile, al MissionAssignment padre) vengono persistite. Gli hook `AFTER_UPDATE_STATUS` vengono eseguiti a operazione completata. Il service restituisce un `AssignmentDTO` o un `ActivityDTO` con il nuovo stato, secondo il tipo di entità aggiornata.

### 11.4 Creazione di un BadgeAward al completamento

Il `BadgeService` verifica che il `MissionAssignment` o l'attività sia in stato `COMPLETED`; se non lo è, `ValidationError`. Verifica che non esista già un `BadgeAward` per lo stesso target. Il `PluginRegistry` esegue gli hook `BEFORE_AWARD_BADGE` con possibilità di veto. Crea una nuova assegnazione indipendente del badge al target. Raccoglie i destinatari in base al tipo di target: per un `MissionAssignment` di tipo `GROUP`, interroga `PersonRepository.get_by_group()` per ottenere i membri correnti del gruppo; per tipo `PERSON`, il destinatario è direttamente `assignee_id`; per un'`Activity`, i destinatari sono tutti gli assegnatari correnti dell'attività. Per ogni persona destinataria registra la propagazione dell'assegnazione. Gli hook `AFTER_AWARD_BADGE` vengono eseguiti a propagazione completata. Il service restituisce un `BadgeAwardDTO` con badge, target, timestamp e conteggio dei destinatari raggiunti.

---

## 12. Scelte architetturali

### 12.1 Repository Pattern con interfacce esplicite

I servizi dipendono esclusivamente dai contratti del Layer 2 (`*Repository`, `OperatorIdentityProvider` quando serve ai frontend), mai dagli adapter del Layer 3. Questo è il confine di Dependency Injection del sistema: al bootstrap dell'applicazione, gli adapter vengono costruiti e iniettati dietro le rispettive interfacce. Il risultato è che i servizi possono essere verificati con adapter sostituibili senza coinvolgere persistenza reale.

### 12.2 Tre frontend intercambiabili

La scelta di tre frontend distinti non è ridondanza: ciascuno serve un caso d'uso diverso. Il frontend REST asincrono è adatto a integrazione con client HTTP che non richiedono notifiche push; è intercambiabile senza impatto sugli altri layer. La Web App è adatta a dashboard operative che richiedono notifiche in tempo reale via WebSocket. Il CLI è adatto ad automazione scripting, operazioni manuali one-shot e ambienti senza rete.

### 12.3 ACL al confine del sistema, non nelle entità di dominio

Il controllo degli accessi opera al confine del sistema — nel middleware dei frontend e all'ingresso dei comandi CLI — tramite `OperatorIdentityProvider` e `AuthorizationPolicy.is_allowed()`, mai nelle entità di dominio né nei service operativi. Le entità (`Mission`, `MissionAssignment`, `Activity`) non contengono logica di autorizzazione: non sanno chi le sta richiedendo né quale profilo abbia l'operatore; i service di dominio si limitano a notificare ad `AclService` creazione/eliminazione delle risorse (seeding e cascata, [§10.7](#107-seeding-automatico-assenza-di-ownership)). `AuthorizationPolicy` è stateless e dipende solo dalle porte del Layer 2. Questa separazione semplifica i test (i service possono essere testati senza contesti di autenticazione) e rende le regole di accesso interamente dati (`AclEntry`), modificabili a runtime senza toccare il modello di dominio.

### 12.4 Status come enum comportamentale

Invece di disperdere la logica delle transizioni in strutture condizionali nei service, la macchina a stati è incapsulata nell'enum `Status` stesso tramite `can_transition_to()`. Questo garantisce che nessun percorso di codice — indipendentemente dal frontend usato — possa bypassare le regole di transizione.

### 12.5 Profile come Value Object del dominio

`Profile` non ha identità propria: due `Profile` con gli stessi valori sono equivalenti. È parte integrante di ogni `Person` del dominio; la sua *assegnazione* è però un'operazione riservata (`PersonService.set_acl_profile`, governata da `MANAGE_PROFILES` — [§10.11](#1011-gestione-delle-acl-e-prevenzione-dellescalation)), distinta dal resto dell'anagrafica proprio per impedire l'auto-promozione. La *valutazione* del profilo avviene esclusivamente nel sistema ACL, contro le `AclEntry`: nessun altro componente lo interpreta.

### 12.6 AssignmentService compone ActivityService

`AssignmentService` ha una dipendenza diretta su `ActivityService`. Poiché gli obiettivi e le relative attività vengono istanziati contestualmente alla creazione dell'assignment (replica del blueprint), la creazione delle attività è un'operazione applicativa che deve passare dal service, non aggirarlo puntando direttamente al repository.

### 12.7 RealtimeNotifier nel frontend web, non nei servizi

Il `RealtimeNotifier` risiede nel frontend web e non nei servizi. Questo mantiene la logica di notifica push come concern di presentazione: i servizi restituiscono dati, il frontend decide come consegnarli ai client (risposta HTTP o broadcast realtime). Gli aggiornamenti notificati riguardano lo stato dei `MissionAssignment` e delle attività.

### 12.8 PersonRepository come contratto di dominio

`PersonRepository` e `GroupRepository` seguono lo stesso Repository Pattern degli altri repository del sistema: i service conoscono solo i contratti (`get`, `exists`, `get_by_group`, `add_member`, ecc.) e non dipendono dal meccanismo di persistenza sottostante. Sostituire l'implementazione (database locale, servizio remoto, mock per test) richiede solo un nuovo adapter del Layer 3, senza toccare alcun service. Questo è il confine di Dependency Injection che rende il Layer 4 indipendente dai dettagli tecnologici del Layer 3.

---

## 13. Casi d'uso per ruolo

### 13.1 Gestore Missioni

| Use Case | Descrizione |
|---|---|
| Creare missione (blueprint) | Crea il blueprint con almeno un obiettivo; ogni obiettivo include le proprie attività |
| Assegnare missione a persona | Crea un `MissionAssignment` per una persona del dominio; replica obiettivi e attività |
| Assegnare missione a gruppo | Crea un `MissionAssignment` per un gruppo del dominio; replica obiettivi e attività |
| Assegnare MissionAssignment non assegnato | Imposta l'assegnatario su un `MissionAssignment` in stato `UNASSIGNED`, portandolo ad `ASSIGNED` |
| Aggiornare stato assignment | Porta avanti lo stato del `MissionAssignment` (UNASSIGNED → ASSIGNED → IN_PROGRESS → COMPLETED/FAILED) |
| Assegnare attività a persona | Assegna un'attività a uno o più operatori del gruppo (o alla persona diretta) |
| Aggiornare stato attività | Porta avanti lo stato dell'attività |
| Creare badge | Crea una nuova definizione di riconoscimento |
| Creare BadgeAward per assignment | Crea un `BadgeAward` per `MissionAssignment` completato (con propagazione agli assegnatari) |
| Creare BadgeAward per attività | Crea un `BadgeAward` per attività completata (con propagazione agli assegnatari dell'attività) |
| Visualizzare assegnazioni badge persona | Consulta le assegnazioni di riconoscimento ricevute da una persona |

### 13.2 Amministratore

| Use Case | Descrizione |
|---|---|
| Aggiungere persona | Crea una nuova `Person` nel dominio (profilo ACL al minimo privilegio) |
| Modificare dati persona | Aggiorna i nicknames di una `Person` esistente |
| Assegnare profilo ACL | Imposta livello e gruppi ACL di una persona (`MANAGE_PROFILES`) |
| Gestire regole ACL | Crea/elimina `AclEntry` su risorse, radici di tipo e `SYSTEM:global` (`MANAGE_ACL`) |
| Rimuovere persona | Elimina una `Person` dal dominio |
| Visualizzare persona | Recupera i dati di una `Person` per ID |
| Elencare persone | Lista tutte le persone, con filtri facoltativi |
| Elencare persone di un gruppo | Lista le persone associate a un `Group` |
| Aggiungere gruppo | Crea un nuovo `Group` nel dominio |
| Rimuovere gruppo | Elimina un `Group` dal dominio |
| Elencare gruppi | Lista tutti i gruppi del dominio |

---

## 14. Sistema di Plugin

Il sistema di plugin permette di estendere il comportamento delle **operazioni esistenti** dei service — creazione missione, assegnazione, aggiornamento stato, creazione `BadgeAward` — senza modificare il codice del core. Un hook intercetta un'operazione a punti predefiniti (prima e dopo l'esecuzione) e può aggiungere side effect, validazioni aggiuntive o comportamenti specifici del deployment.

### 14.1 Posizione nell'architettura

I plugin si inseriscono nel **Layer 4 (Service)** come collaboratori opzionali. Ogni service riceve un `PluginRegistry` tramite dependency injection; quando presente, chiama `registry.fire(HookPoint, HookContext)` prima e dopo ogni operazione soggetta a hook. Se il registry non è fornito, il comportamento è identico a prima: nessuna penalità per i test o per i deployment che non usano plugin.

```
Frontend  →  Service  →  PluginRegistry  →  MissionHook_1, MissionHook_2, ...
                     ↘  Repository (inclusi PersonRepository, GroupRepository)
                     ↘  OperatorIdentityProvider
```

`MissionHook` è una **porta del Layer 2**: l'interfaccia è dichiarata tra i contratti architetturali, mentre gli hook concreti sono adapter del Layer 3.

### 14.2 Interfaccia MissionHook

`MissionHook` è una porta del Layer 2 con due elementi: un `manifest` che dichiara i punti di hook di interesse e un metodo `execute` invocato dal registry.

```
MissionHook (interfaccia, porta Layer 2):
    manifest: PluginManifest
    execute(context: HookContext) → None
```

`PluginManifest` descrive il plugin e dichiara i `HookPoint` a cui è registrato:

```
PluginManifest:
    id: str                               # identificatore stabile nel registry
    name: str                             # nome leggibile
    version: str
    hooks: list[HookPoint]                # punti di hook di interesse (usati da register())
    description: str
    trust_level: PluginTrustLevel         # TRUSTED | SANDBOXED (default: SANDBOXED)
    priority: int                         # priorità di esecuzione (default: 0, più alto = prima)
    code_checksum: str                    # SHA-256 del file plugin.py approvato
```

`PluginTrustLevel` è un enum con due valori: `TRUSTED` e `SANDBOXED`. Solo i plugin `TRUSTED` possono abortire un'operazione e propagare mutazioni del `HookContext`; i plugin `SANDBOXED` ricevono una copia difensiva senza contenuti sensibili e tutte le loro mutazioni (`result`, `abort`, `user_message`) vengono ignorate. Il livello effettivo viene dal `PluginTrustRegistry`, che autorizza il bundle con `manifest_checksum` e `code_checksum` prima dell'import.

Un plugin installabile è sempre un bundle `plugin_id/manifest.json + plugin.py`. `PluginLoader` legge `manifest.json` senza eseguire codice, verifica il checksum del manifest e del codice contro il registry esterno, converte gli hook stringa in `HookPoint` e importa `plugin.py` solo dopo il successo di entrambe le verifiche. I file `.py` flat non sono caricabili.

`HookPoint` è un enum del Layer 2 con 8 costanti (4 operazioni × BEFORE/AFTER):

```
HookPoint:
    BEFORE_CREATE_MISSION      AFTER_CREATE_MISSION
    BEFORE_CREATE_ASSIGNMENT   AFTER_CREATE_ASSIGNMENT
    BEFORE_UPDATE_STATUS       AFTER_UPDATE_STATUS
    BEFORE_AWARD_BADGE         AFTER_AWARD_BADGE
```

`HookContext` è un oggetto tipizzato:

```
HookContext:
    hook_point: HookPoint   # evento corrente
    operator_id: UUID       # identità dell'operatore
    payload: dict           # dati dell'operazione
    result: Any?            # valorizzato dopo l'azione; gli AFTER_* possono arricchirlo
    abort: bool             # se True, PluginRegistry solleva OperationAbortedError
    abort_reason: str?      # motivo opzionale del veto (per l'errore restituito al client)
```

### 14.3 Punti di hook e semantica

| HookPoint | Fase | Effetto veto | Payload principale |
|---|---|---|---|
| `BEFORE_CREATE_MISSION` | pre-creazione blueprint | sì | `payload` con titolo, obiettivi, attività |
| `AFTER_CREATE_MISSION` | post-creazione blueprint | no | `result` = `mission` appena persistita |
| `BEFORE_CREATE_ASSIGNMENT` | pre-creazione assignment | sì | `payload` con `mission_id`, `assignee_type`, `assignee_id` |
| `AFTER_CREATE_ASSIGNMENT` | post-creazione assignment | no | `result` = `MissionAssignment` creato |
| `BEFORE_UPDATE_STATUS` | pre-transizione stato | sì | `payload` con `entity_id`, `entity_type`, `new_status` |
| `AFTER_UPDATE_STATUS` | post-transizione stato | no | `result` = entità con stato aggiornato |
| `BEFORE_AWARD_BADGE` | pre-creazione `BadgeAward` | sì | `payload` con `badge_id`, `target_type`, `target_id` |
| `AFTER_AWARD_BADGE` | post-propagazione | no | `result` = `{badge_award, target, recipients_count}` |

I hook **BEFORE_\*** possono annullare l'operazione impostando `ctx.abort = True`: `PluginRegistry` interrompe l'iterazione e solleva `OperationAbortedError` (HTTP 422, errore CLI). L'operazione non procede a scritture o mutazioni di stato; eventuali letture preliminari già necessarie al service possono essere avvenute. I hook **AFTER_\*** ricevono il risultato già persistito in `ctx.result`: le eccezioni che sollevano vengono catturate e loggate, ma non propagate (l'operazione è già completata).

### 14.4 PluginRegistry

`PluginRegistry` mantiene i plugin indicizzati per `HookPoint` ed espone quattro operazioni:

- `register(hook: MissionHook)`: legge `hook.manifest.hooks` e inserisce il plugin nel dizionario interno per ogni `HookPoint` dichiarato; dopo ogni `register()` la lista per quel `HookPoint` viene riordinata per `priority` DESC (priorità maggiore = eseguito prima).
- `unregister(plugin_id: str)`: rimuove il plugin (per id) da tutti gli insiemi in cui era stato registrato.
- `fire(point: HookPoint, context: HookContext)`: recupera la lista dei plugin registrati per quel `HookPoint` e invoca `execute(context)` su ciascuno in ordine di priorità; per i BEFORE_* controlla `ctx.abort` dopo ogni hook TRUSTED e si ferma se `True` sollevando `OperationAbortedError`; i plugin SANDBOXED ricevono `ScopedHookContext` e tutte le loro mutazioni vengono ignorate; per gli AFTER_* cattura e loga le eccezioni continuando.
- `list_plugins() → List[PluginManifest]`: restituisce i manifest di tutti i plugin registrati (utile per introspection e diagnostica).

Al bootstrap dell'applicazione, `PluginRegistry` viene costruito, gli hook vengono registrati nell'ordine voluto e il registry viene iniettato nei service tramite DI, esattamente come gli altri adapter.

### 14.5 Esempi di hook

| Implementazione | `manifest.hooks` | Descrizione |
|---|---|---|
| `ExternalSyncHook` | `AFTER_UPDATE_STATUS`, `AFTER_AWARD_BADGE` | Propaga gli aggiornamenti di stato verso sistemi operativi che consumeranno i dati di MissionManager |

---

## 15. Sistema di Estensioni

Il sistema di estensioni permette di aggiungere **nuove operazioni** al sistema — operazioni che non esistono nei service del core — mantenendo la struttura a strati. Dove i plugin si agganciano a operazioni già esistenti, un'estensione aggiunge un'operazione del tutto nuova, visibile ai client come nuovi endpoint REST, nuove route Web App o nuovi comandi CLI.

### 15.1 Posizione nell'architettura

Le estensioni abitano il **Layer 4 (Service)** come moduli aggiuntivi indipendenti, affiancati ai service esistenti senza modificarli. Al Layer 5, ogni frontend legge i manifest delle estensioni attive al bootstrap e registra dinamicamente le route e i comandi aggiuntivi — senza modifiche al proprio codice base.

```
Frontend  →  [MissionRouter, create_web_blueprint, CLIApp, ...]
          →  [route e comandi registrati dinamicamente via ExtensionRegistry.list()]

Service   →  [MissionService, ActivityService, BadgeService]
          →  [mission-stats, badge-export, assignment-timeline]   ← moduli MissionExtension
```

Le estensioni ricevono i service applicativi (`MissionService`, `BadgeService`, `PersonService`...) direttamente nel costruttore. La dipendenza è `Extension → Services`, mai il contrario. Non dipendono dal Layer 5 (frontend) e non modificano i contratti del Layer 2, gli adapter del Layer 3 o il Layer 1 (Domain).

### 15.2 Interfaccia MissionExtension

```
MissionExtension (Protocol, porta Layer 2):
    manifest: ExtensionManifest           # metadati e capacità dell'estensione
    execute(request: ExtensionRequest) → ExtensionResult
```

`ExtensionManifest` descrive l'estensione e dichiara le sue capacità frontend:

```
ExtensionManifest:
    id: str                           # identificatore stabile dell'estensione nel registry
    name: str                         # nome leggibile
    version: str
    description: str
    provides_routes: list[RouteSpec]  # endpoint REST/web aggiunti dall'estensione
    provides_commands: list[CommandSpec]  # comandi CLI aggiunti dall'estensione
    code_checksum: str                # SHA-256 del file extension.py
```

`InstalledManifestRegistry` contiene entry `{manifest_checksum, code_checksum}` per ogni estensione approvata. Il loader rifiuta l'estensione se il manifest non è approvato, se il manifest è stato alterato, o se `extension.py` non corrisponde al checksum installato.

`RouteSpec` e `CommandSpec` descrivono i punti di accesso dichiarati dall'estensione:

```
RouteSpec:
    path: str        # percorso dell'endpoint; deve iniziare con /extensions/{id}/
    method: str      # metodo HTTP (GET, POST, ...)
    description: str

CommandSpec:
    name: str        # nome del comando CLI (es. sync, report)
    description: str
```

`ExtensionRequest` e `ExtensionResult` sono oggetti tipizzati:

```
ExtensionRequest:
    operator_id: UUID   # identità dell'operatore
    params: dict        # parametri specifici dell'estensione
    body: dict          # body normalizzato dal frontend, se presente
    subject: Any?       # opzionale per adapter che usano soggetti applicativi

ExtensionResult:
    data: Any
    status_code: int    # codice di esito (es. 200, 201, 404)
    message: str?       # messaggio opzionale (per errori o conferme)
```

### 15.3 ExtensionRegistry

`ExtensionRegistry` mantiene le estensioni indicizzate per `id` ed espone cinque operazioni:

- `register(extension: MissionExtension)`: registra l'estensione indicizzandola per `manifest.id`; l'id deve essere univoco e ogni route deve stare nel namespace `/extensions/{id}/`.
- `unregister(ext_id: str)`: rimuove l'estensione dal registry.
- `get(ext_id: str) → MissionExtension?`: restituisce l'istanza dell'estensione per id.
- `list() → List[ExtensionManifest]`: restituisce i manifest di tutte le estensioni registrate; i frontend lo chiamano al bootstrap per decidere quali route e comandi aggiuntivi montare.
- `execute(ext_id: str, request: ExtensionRequest) → ExtensionResult`: smista la richiesta all'estensione corrispondente per id.

Al bootstrap, `ExtensionLoader` scopre e crea le istanze delle estensioni; ciascuna viene registrata con `registry.register(extension)`. I frontend chiamano `list()` una volta all'avvio e registrano dinamicamente i nuovi endpoint e comandi leggendo `provides_routes` e `provides_commands` dai manifest.

### 15.4 ExtensionLoader

`ExtensionLoader` è un componente del **Layer 3 (Infrastructure)** responsabile della scoperta, del caricamento e dell'istanziazione delle estensioni. Risiede in `infrastructure/extensions/` insieme all'`InstalledManifestRegistry`. Riceve i service applicativi al costruttore (iniettati dal bootstrap) e li passa alle estensioni che istanzia:

```
ExtensionLoader:
    scan_paths: list[str]                       # percorsi da esaminare
    load_all() → list[MissionExtension]         # carica tutte le estensioni trovate
```

Scopre solo bundle `<scan_dir>/<id>/manifest.json + extension.py`. Il loader legge il manifest senza eseguire codice, verifica `manifest_checksum` e `code_checksum` contro `InstalledManifestRegistry`, importa `extension.py` solo dopo il successo di entrambe le verifiche e istanzia `Extension(manifest=..., **services)`. Se il registry è assente o vuoto non viene caricata alcuna estensione. Viene invocato una volta al bootstrap, prima dell'avvio del server o del CLI, e passa le istanze caricate a `ExtensionRegistry.register()`.

### 15.5 Esempi di estensioni

| Estensione | `provides_routes` | `provides_commands` | Operazione principale |
|---|---|---|---|
| `mission-stats` | `/extensions/mission-stats/...` | `mission-stats` | Statistiche aggregate di una missione |
| `badge-export` | `/extensions/badge-export/...` | `badge-export` | Esporta i badge ricevuti da una persona |
| `assignment-timeline` | `/extensions/assignment-timeline/...` | `assignment-timeline` | Timeline degli assignment di una missione |

### 15.6 Differenza tra plugin ed estensioni

| Aspetto | Plugin (MissionHook) | Estensione (MissionExtension) |
|---|---|---|
| Scopo | Modificare il comportamento di operazioni esistenti | Aggiungere operazioni nuove |
| Visibilità ai client | Trasparente — nessun nuovo endpoint o comando | Visibile — nuovi `RouteSpec` e `CommandSpec` dichiarati nel manifest |
| Punto di integrazione | Hook BEFORE_*/AFTER_* nei service esistenti | Nuovo modulo con `execute()` + manifest letto dai frontend al bootstrap |
| Accesso al core | Riceve dati tramite `HookContext` | Riceve i service applicativi nel costruttore |
| Veto possibile | Sì — BEFORE_* via `ctx.abort=True` + `abort_reason` | N/A — l'estensione è l'operazione stessa |
