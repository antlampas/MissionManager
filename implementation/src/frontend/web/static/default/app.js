// SPDX-License-Identifier: CC-BY-SA-4.0

/**
 * Mission Manager — Web App client
 *
 * Responsabilità:
 *   1. Connessione WebSocket per aggiornamenti real-time di stato
 *   2. Aggiornamento live dei badge di stato senza reload
 *   3. Indicatore di connessione visibile in header
 *
 * CSP-compliant: nessun eval(), nessun inline handler.
 */
(function () {
  "use strict";

  /* ------------------------------------------------------------------ */
  /* Costanti                                                             */
  /* ------------------------------------------------------------------ */

  const STATUS_LABELS = {
    UNASSIGNED:  "Non assegnato",
    ASSIGNED:    "Assegnato",
    IN_PROGRESS: "In corso",
    COMPLETED:   "Completato",
    FAILED:      "Fallito",
  };

  const STATUS_CLASSES = Object.keys(STATUS_LABELS).map(
    (s) => "status-badge--" + s
  );

  /* ------------------------------------------------------------------ */
  /* WebSocket                                                            */
  /* ------------------------------------------------------------------ */

  function buildWsUrl() {
    const bodyPath = document.body.dataset.wsPath;
    if (!bodyPath) return null;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + location.host + bodyPath;
  }

  function connectWs(url, indicator) {
    let ws;
    let retryDelay = 2000;

    function connect() {
      ws = new WebSocket(url);

      ws.addEventListener("open", function () {
        retryDelay = 2000;
        setIndicator(indicator, true);
      });

      ws.addEventListener("close", function () {
        setIndicator(indicator, false);
        setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 1.5, 30000);
      });

      ws.addEventListener("error", function () {
        ws.close();
      });

      ws.addEventListener("message", function (evt) {
        let msg;
        try { msg = JSON.parse(evt.data); } catch { return; }
        handleEvent(msg.event, msg.data);
      });
    }

    connect();
  }

  function setIndicator(el, connected) {
    if (!el) return;
    el.classList.toggle("ws-indicator--connected", connected);
    el.title = connected ? "Aggiornamenti live attivi" : "Connessione interrotta";
  }

  /* ------------------------------------------------------------------ */
  /* Gestione eventi                                                      */
  /* ------------------------------------------------------------------ */

  function handleEvent(event, data) {
    if (event === "assignment_status") {
      updateStatus("[data-assignment-id='" + data.assignment_id + "']", data.status);
    } else if (event === "activity_status") {
      updateStatus("[data-activity-id='" + data.activity_id + "']", data.status);
    }
  }

  function updateStatus(selector, newStatus) {
    document.querySelectorAll(selector + " .status-badge").forEach(function (el) {
      STATUS_CLASSES.forEach((c) => el.classList.remove(c));
      el.classList.add("status-badge--" + newStatus);
      el.textContent = STATUS_LABELS[newStatus] || newStatus;
    });
  }

  /* ------------------------------------------------------------------ */
  /* Alert auto-dismiss                                                   */
  /* ------------------------------------------------------------------ */

  function initAlerts() {
    document.querySelectorAll(".alert[data-autohide]").forEach(function (el) {
      const delay = parseInt(el.dataset.autohide, 10) || 4000;
      setTimeout(function () {
        el.style.transition = "opacity .4s";
        el.style.opacity = "0";
        setTimeout(function () { el.remove(); }, 420);
      }, delay);
    });

    document.querySelectorAll(".alert__close").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const alert = btn.closest(".alert");
        if (alert) alert.remove();
      });
    });
  }

  /* ------------------------------------------------------------------ */
  /* Creazione entità — form builder (missioni, obiettivi, assegnazioni)  */
  /*                                                                      */
  /* I form inviano JSON via fetch agli endpoint esistenti del frontend   */
  /* web. Tutto il comportamento è qui (CSP: nessun handler inline).      */
  /* ------------------------------------------------------------------ */

  function fieldValue(scope, selector) {
    const el = scope.querySelector(selector);
    return el ? el.value.trim() : "";
  }

  function cloneTemplate(selector) {
    const tpl = document.querySelector(selector);
    if (!tpl || !tpl.content || !tpl.content.firstElementChild) return null;
    return tpl.content.firstElementChild.cloneNode(true);
  }

  function addActivityRow(activitiesContainer) {
    const row = cloneTemplate("[data-activity-template]");
    if (row) activitiesContainer.appendChild(row);
  }

  function addObjectiveBlock(objectivesContainer) {
    const block = cloneTemplate("[data-objective-template]");
    if (!block) return;
    objectivesContainer.appendChild(block);
    const acts = block.querySelector("[data-activities]");
    if (acts && !acts.children.length) addActivityRow(acts);
  }

  function serializeActivities(scope) {
    const out = [];
    scope.querySelectorAll("[data-activity]").forEach(function (row) {
      const title = fieldValue(row, '[data-field="activity-title"]');
      const description = fieldValue(row, '[data-field="activity-description"]');
      if (title || description) out.push({ title: title, description: description });
    });
    return out;
  }

  function serializeObjectives(form) {
    const out = [];
    form.querySelectorAll("[data-objective]").forEach(function (objEl) {
      const acts = objEl.querySelector("[data-activities]");
      out.push({
        description: fieldValue(objEl, '[data-field="objective-description"]'),
        activities: acts ? serializeActivities(acts) : [],
      });
    });
    return out;
  }

  function showFormError(message) {
    const box = document.querySelector("[data-form-error]");
    if (!box) { window.alert(message); return; }
    const txt = box.querySelector("[data-form-error-text]");
    if (txt) txt.textContent = message;
    box.hidden = false;
    box.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function clearFormError() {
    const box = document.querySelector("[data-form-error]");
    if (box) box.hidden = true;
  }

  function sendJson(method, endpoint, payload) {
    const csrf = document.querySelector('meta[name="csrf-token"]');
    return fetch(endpoint, {
      method: method,
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf ? csrf.content : "",
      },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    }).then(function (resp) {
      return resp.json().catch(function () { return null; }).then(function (data) {
        return { ok: resp.ok, status: resp.status, data: data };
      });
    });
  }

  /* Selettore tipo+id assegnatario condiviso da assignment-create/assign.
   * Ritorna:
   *   null       → nessun tipo scelto (= "non assegnato")
   *   undefined  → tipo scelto ma id mancante (errore)
   *   {type,id}  → selezione valida
   */
  function readAssignee(form) {
    const typeSel = form.querySelector("[data-assignee-type]");
    const type = typeSel ? typeSel.value : "";
    if (!type) return null;
    const idSel = form.querySelector('[data-assignee-id="' + type + '"]');
    const id = idSel ? idSel.value.trim() : "";
    if (!id) return undefined;
    return { assignee_type: type, assignee_id: id };
  }

  /* Raccoglie i campi semplici marcati con [data-json="<chiave>"].
   *   data-json-type="int"  → intero, oppure null se vuoto
   *   data-json-type="list" → lista di stringhe (separatori: virgola o a-capo)
   *   data-json-optional    → null se vuoto, altrimenti la stringa
   */
  function collectJsonFields(form) {
    const payload = {};
    form.querySelectorAll("[data-json]").forEach(function (el) {
      const key = el.getAttribute("data-json");
      const raw = typeof el.value === "string" ? el.value.trim() : el.value;
      const type = el.getAttribute("data-json-type");
      if (type === "int") {
        payload[key] = raw === "" ? null : parseInt(raw, 10);
      } else if (type === "list") {
        payload[key] = raw
          .split(/[\n,]+/)
          .map(function (s) { return s.trim(); })
          .filter(Boolean);
      } else if (el.hasAttribute("data-json-optional")) {
        payload[key] = raw === "" ? null : raw;
      } else {
        payload[key] = raw;
      }
    });
    return payload;
  }

  function buildPayload(kind, form) {
    if (kind === "mission-create") {
      return {
        title: fieldValue(form, '[name="title"]'),
        description: fieldValue(form, '[name="description"]'),
        objectives: serializeObjectives(form),
      };
    }
    if (kind === "assignment-create") {
      const a = readAssignee(form);
      if (a === undefined) return null;     // tipo scelto ma assegnatario mancante
      const payload = a === null ? {} : a;  // a===null → assignment non assegnato
      // La pagina dedicata sceglie anche la missione; se mancante, la lascio fuori
      // così il backend risponde con un errore di campo obbligatorio chiaro.
      const missionSel = form.querySelector("[data-mission-id]");
      if (missionSel && missionSel.value) payload.mission_id = missionSel.value;
      return payload;
    }
    if (kind === "assignment-assign") {
      const a = readAssignee(form);
      if (!a) return null;             // qui la scelta è obbligatoria
      return a;
    }
    // Tutti gli altri kind (status-change, assign, badge-award, person/group/
    // badge create-edit, delete, member add/remove) usano i campi [data-json].
    return collectJsonFields(form);
  }

  function onCreateSuccess(kind, data) {
    if (kind === "mission-create" && data && data.id) {
      window.location.assign("/missions/" + data.id);
    } else if (kind === "assignment-create" && data && data.id) {
      window.location.assign("/assignments/" + data.id);
    } else {
      window.location.reload();
    }
  }

  /* Destinazione dopo il successo:
   *   data-redirect assente  → comportamento legacy (onCreateSuccess)
   *   "reload"               → ricarica la pagina
   *   URL (con "{id}" opz.)  → naviga, sostituendo {id} con l'id restituito
   */
  function onSuccess(form, kind, data) {
    const redirect = form.getAttribute("data-redirect");
    if (redirect === null) { onCreateSuccess(kind, data); return; }
    if (redirect === "reload") { window.location.reload(); return; }
    let url = redirect;
    if (data && data.id && url.indexOf("{id}") !== -1) {
      url = url.replace("{id}", data.id);
    }
    window.location.assign(url);
  }

  function handleBuilderClick(target) {
    if (target.closest("[data-add-objective]")) {
      const form = target.closest("[data-form]");
      const cont = form && form.querySelector("[data-objectives]");
      if (cont) addObjectiveBlock(cont);
    } else if (target.closest("[data-remove-objective]")) {
      const obj = target.closest("[data-objective]");
      if (obj) obj.remove();
    } else if (target.closest("[data-add-activity]")) {
      const btn = target.closest("[data-add-activity]");
      const scope = btn.closest("[data-objective]") || btn.closest("[data-form]");
      const acts = scope && scope.querySelector("[data-activities]");
      if (acts) addActivityRow(acts);
    } else if (target.closest("[data-remove-activity]")) {
      const row = target.closest("[data-activity]");
      if (row) row.remove();
    }
  }

  function onAssigneeTypeChange(sel) {
    const form = sel.closest("[data-form]");
    if (!form) return;
    form.querySelectorAll("[data-assignee-field]").forEach(function (field) {
      field.hidden = field.getAttribute("data-assignee-field") !== sel.value;
    });
  }

  function onFormSubmit(form) {
    const kind = form.getAttribute("data-form");
    const endpoint = form.getAttribute("data-endpoint");
    if (!kind || !endpoint) return;

    const confirmMsg = form.getAttribute("data-confirm");
    if (confirmMsg && !window.confirm(confirmMsg)) return;

    const method = (form.getAttribute("data-method") || "POST").toUpperCase();
    const payload = buildPayload(kind, form);
    if (payload === null) {
      showFormError("Seleziona una persona o un gruppo, oppure scegli «Non assegnato».");
      return;
    }
    clearFormError();

    const submitBtn = form.querySelector("[data-submit]");
    if (submitBtn) submitBtn.disabled = true;

    sendJson(method, endpoint, payload).then(function (res) {
      if (res.ok) {
        onSuccess(form, kind, res.data);
        return;
      }
      const msg = (res.data && res.data.error) || ("Errore " + res.status);
      showFormError(msg);
      if (submitBtn) submitBtn.disabled = false;
    }).catch(function () {
      showFormError("Errore di rete. Riprova.");
      if (submitBtn) submitBtn.disabled = false;
    });
  }

  function initForms() {
    document.querySelectorAll('[data-form="mission-create"]').forEach(function (form) {
      const cont = form.querySelector("[data-objectives]");
      if (cont && !cont.children.length) addObjectiveBlock(cont);
    });

    document.addEventListener("click", function (e) {
      if (e.target && e.target.closest) handleBuilderClick(e.target);
    });

    document.addEventListener("change", function (e) {
      const sel = e.target && e.target.closest && e.target.closest("[data-assignee-type]");
      if (sel) onAssigneeTypeChange(sel);
    });

    document.addEventListener("submit", function (e) {
      const form = e.target && e.target.closest && e.target.closest("[data-form]");
      if (!form) return;
      e.preventDefault();
      onFormSubmit(form);
    });
  }

  /* ------------------------------------------------------------------ */
  /* Init                                                                 */
  /* ------------------------------------------------------------------ */

  document.addEventListener("DOMContentLoaded", function () {
    initAlerts();
    initForms();

    const wsUrl = buildWsUrl();
    if (!wsUrl) return;

    const indicator = document.querySelector(".ws-indicator");
    connectWs(wsUrl, indicator);
  });
})();
