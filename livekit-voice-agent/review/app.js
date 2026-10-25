const REVIEW_STATUSES = ["Pending Review", "Under Review", "Escalated", "Resolved"];
const state = { sessions: [], selectedId: null, artifact: null };

const $ = (id) => document.getElementById(id);
const create = (tag, className, text) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = text;
  return element;
};
const label = (value) => String(value ?? "Not recorded").replaceAll("_", " ");
const statusClass = (value) => String(value ?? "").toLowerCase().replaceAll(" ", "-");
const fieldValue = (field) => field?.value || null;
const dateTime = (seconds) => {
  if (!seconds) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(seconds * 1000));
};

function badge(text, status = "") {
  return create("span", `badge ${statusClass(status)}`, label(text));
}

function incidentRecord(artifact) {
  return artifact.incident?.record || artifact.incident_record || {};
}

function incidentId(artifact) {
  return artifact.incident?.id || artifact.session?.incident_id || null;
}

function isUrgent(artifact) {
  const urgency = incidentRecord(artifact).urgency?.classification || artifact.safety?.urgency;
  return Boolean(
    artifact.safety?.human_review_required || urgency === "urgent" || urgency === "emergency",
  );
}

function evidenceLinks(turnIds = []) {
  const row = create("div", "evidence-row");
  turnIds.forEach((turnId) => {
    const button = create("button", "evidence-link", turnId);
    button.type = "button";
    button.addEventListener("click", () => focusTurn(turnId));
    row.append(button);
  });
  return row;
}

function focusTurn(turnId) {
  const turn = document.getElementById(`transcript-${turnId}`);
  if (!turn) return;
  document.querySelectorAll(".turn.highlight").forEach((item) => item.classList.remove("highlight"));
  turn.classList.add("highlight");
  turn.scrollIntoView({ behavior: "smooth", block: "center" });
  window.setTimeout(() => turn.classList.remove("highlight"), 2400);
}

async function loadSessions() {
  $("session-list").replaceChildren(create("p", "muted", "Loading incidents…"));
  try {
    const response = await fetch("/api/sessions", { cache: "no-store" });
    if (!response.ok) throw new Error("Could not load incidents");
    state.sessions = (await response.json()).sessions;
    renderSessionList();
    const selected = state.sessions.find((item) => item.artifact_id === state.selectedId);
    const firstReady = state.sessions.find((item) => item.review_status === "ready");
    if (selected) await selectSession(selected.artifact_id, { refreshList: false });
    else if (firstReady) await selectSession(firstReady.artifact_id, { refreshList: false });
  } catch (error) {
    $("session-list").replaceChildren(create("p", "empty-panel", error.message));
  }
}

function renderSessionList() {
  const query = $("session-search").value.trim().toLowerCase();
  const filtered = state.sessions.filter((session) => {
    const searchable = [
      session.incident_id,
      session.incident_type,
      session.location,
      session.summary,
      session.caller_name,
      session.review?.status,
      session.urgency,
    ].join(" ").toLowerCase();
    return searchable.includes(query);
  });
  $("session-count").textContent = `${filtered.length} ${filtered.length === 1 ? "incident" : "incidents"}`;
  const list = $("session-list");
  list.replaceChildren();
  if (!filtered.length) {
    list.append(create("p", "empty-panel", "No matching incident records."));
    return;
  }
  filtered.forEach((session) => {
    const button = create("button", "session-button");
    button.type = "button";
    button.classList.toggle("active", session.artifact_id === state.selectedId);
    button.classList.toggle(
      "urgent",
      session.human_review_required || ["urgent", "emergency"].includes(session.urgency),
    );
    const top = create("div", "session-button-top");
    top.append(
      badge(session.review?.status || "Pending Review", session.review?.status),
      badge(session.urgency || "unknown", session.urgency),
    );
    button.append(top);
    button.append(create("strong", "", session.incident_id || "Legacy session"));
    button.append(create("small", "", label(session.incident_type || session.plan?.id)));
    button.append(create("small", "", session.location || dateTime(session.submission_time)));
    button.disabled = session.review_status !== "ready";
    if (!button.disabled) button.addEventListener("click", () => selectSession(session.artifact_id));
    list.append(button);
  });
}

async function selectSession(artifactId, { refreshList = true } = {}) {
  state.selectedId = artifactId;
  if (refreshList) renderSessionList();
  $("empty-state").hidden = true;
  $("review-content").hidden = true;
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(artifactId)}`, {
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not load incident");
    state.artifact = payload;
    renderArtifact(payload);
    $("review-content").hidden = false;
  } catch (error) {
    $("empty-state").hidden = false;
    $("empty-state").querySelector("h2").textContent = "Incident could not be loaded";
    $("empty-state").querySelector("p:last-child").textContent = error.message;
  }
}

function renderArtifact(artifact) {
  const session = artifact.session || {};
  const incident = incidentRecord(artifact);
  const id = incidentId(artifact) || "Legacy session";
  const urgency = incident.urgency?.classification || artifact.safety?.urgency || "unknown";
  $("incident-id").textContent = id;
  $("incident-subtitle").textContent = `${label(incident.incident_type)} · submitted ${dateTime(session.artifact_created_at)}`;
  $("header-badges").replaceChildren(
    badge(artifact.incident?.status || "Not submitted", artifact.incident?.status),
    badge(artifact.review?.status || "Pending Review", artifact.review?.status),
  );
  $("urgency-card").replaceChildren(
    create("small", "", "Urgency"),
    create("strong", "", label(urgency)),
  );
  $("urgency-card").classList.toggle("urgent", isUrgent(artifact));
  $("urgent-alert").hidden = !isUrgent(artifact);

  renderReviewState(artifact.review, Boolean(incidentId(artifact)));
  renderFacts(artifact, incident, urgency);
  renderCaller(incident);
  renderSummary(incident);
  renderDetails(incident);
  renderTranscript(artifact.transcript || []);
}

function renderReviewState(review, enabled) {
  const status = review?.status || "Pending Review";
  $("status-select").value = REVIEW_STATUSES.includes(status) ? status : "Pending Review";
  $("status-select").disabled = !enabled;
  $("save-status-button").disabled = !enabled;
  $("acknowledge-button").disabled = !enabled || Boolean(review?.acknowledged_at);
  $("acknowledgment-text").textContent = review?.acknowledged_at
    ? `Acknowledged ${dateTime(review.acknowledged_at)} · last updated ${dateTime(review.updated_at)}`
    : "Not yet acknowledged by an operator.";
  $("operator-message").textContent = enabled ? "" : "Review actions are unavailable for legacy artifacts.";
}

function renderFacts(artifact, incident, urgency) {
  const notification = artifact.operator_notification || {};
  const facts = [
    ["Incident type", label(incident.incident_type)],
    ["Subcategory", label(incident.subcategory)],
    ["Urgency", label(urgency)],
    ["Submission time", dateTime(artifact.session?.artifact_created_at)],
    ["Notification", label(notification.status || "Not sent")],
    ["Transcript turns", artifact.session?.transcript_turns ?? artifact.transcript?.length ?? 0],
  ];
  $("incident-facts").replaceChildren(...facts.map(([name, value]) => {
    const card = create("div", "fact");
    card.append(create("small", "", name), create("strong", "", value));
    return card;
  }));
}

function detailCard(title, value, turnIds = []) {
  const card = create("article", "detail-card");
  card.append(create("h4", "", title));
  card.append(create("p", value ? "" : "muted", value || "Not provided"));
  if (turnIds.length) card.append(evidenceLinks(turnIds));
  return card;
}

function renderCaller(incident) {
  const caller = incident.caller || {};
  const location = incident.location;
  $("caller-grid").replaceChildren(
    detailCard("Caller-reported location", fieldValue(location), location?.evidence_turn_ids),
    detailCard("Caller name", fieldValue(caller.name), caller.name?.evidence_turn_ids),
    detailCard("Contact method", fieldValue(caller.contact), caller.contact?.evidence_turn_ids),
  );
}

function renderSummary(incident) {
  const summary = incident.summary;
  $("confidence-badge").className = `badge ${statusClass(incident.confidence)}`;
  $("confidence-badge").textContent = `Confidence: ${label(incident.confidence)}`;
  const card = create("article", "finding-card");
  card.append(create("h4", "", "Summary for human review"));
  card.append(create("p", summary ? "" : "muted", fieldValue(summary) || "No AI summary is available."));
  if (summary?.evidence_turn_ids?.length) card.append(evidenceLinks(summary.evidence_turn_ids));
  $("summary-content").replaceChildren(card);
}

function renderDetails(incident) {
  const description = incident.description;
  const occurredAt = incident.occurred_at;
  const urgency = incident.urgency || {};
  const cards = [
    detailCard("Incident description", fieldValue(description), description?.evidence_turn_ids),
    detailCard("Date and time of occurrence", fieldValue(occurredAt), occurredAt?.evidence_turn_ids),
    detailCard("Urgency rationale", urgency.rationale, urgency.evidence_turn_ids),
  ];
  (incident.relevant_details || []).forEach((detail, index) => {
    cards.push(detailCard(`Relevant detail ${index + 1}`, fieldValue(detail), detail.evidence_turn_ids));
  });
  cards.push(
    detailCard(
      "Evidence gaps",
      (incident.evidence_gaps || []).join(" · ") || "No evidence gaps recorded.",
    ),
  );
  $("detail-grid").replaceChildren(...cards);
}

function renderTranscript(turns) {
  $("turn-count").textContent = `${turns.length} finalized ${turns.length === 1 ? "turn" : "turns"}`;
  const transcript = $("transcript");
  transcript.replaceChildren();
  if (!turns.length) {
    transcript.append(create("div", "empty-panel", "No finalized transcript turns were captured."));
    return;
  }
  turns.forEach((turn) => {
    const article = create("article", `turn ${turn.role}`);
    article.id = `transcript-${turn.id}`;
    const meta = create("div", "turn-meta");
    meta.append(
      create("strong", "", turn.role),
      create("span", "", turn.id),
      create("time", "", dateTime(turn.created_at)),
    );
    if (turn.interrupted) meta.append(badge("interrupted", "failed"));
    article.append(meta, create("p", "", turn.text));
    transcript.append(article);
  });
}

async function postReviewAction(action, payload) {
  const id = incidentId(state.artifact || {});
  if (!id) return;
  const button = action === "acknowledge" ? $("acknowledge-button") : $("save-status-button");
  button.disabled = true;
  $("operator-message").className = "operator-message";
  $("operator-message").textContent = "Saving…";
  try {
    const response = await fetch(`/api/incidents/${encodeURIComponent(id)}/${action}`, {
      method: "POST",
      headers: payload ? { "Content-Type": "application/json" } : {},
      body: payload ? JSON.stringify(payload) : undefined,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Review update failed");
    state.artifact.review = result.review;
    renderReviewState(result.review, true);
    $("operator-message").className = "operator-message success";
    $("operator-message").textContent = action === "acknowledge"
      ? "Incident acknowledged."
      : `Status updated to ${result.review.status}.`;
    await loadSessions();
  } catch (error) {
    $("operator-message").className = "operator-message error";
    $("operator-message").textContent = error.message;
    renderReviewState(state.artifact.review, true);
  }
}

$("refresh-button").addEventListener("click", loadSessions);
$("session-search").addEventListener("input", renderSessionList);
$("acknowledge-button").addEventListener("click", () => postReviewAction("acknowledge"));
$("save-status-button").addEventListener("click", () =>
  postReviewAction("status", { status: $("status-select").value }),
);
loadSessions();
