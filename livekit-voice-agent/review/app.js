const state = { sessions: [], selectedId: null };

const $ = (id) => document.getElementById(id);
const create = (tag, className, text) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = text;
  return element;
};

const label = (value) => String(value ?? "Not recorded").replaceAll("_", " ");
const dateTime = (seconds) => {
  if (!seconds) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(seconds * 1000));
};

function badge(text, status = "") {
  return create("span", `badge ${status}`, label(text));
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
  $("session-list").replaceChildren(create("p", "muted", "Loading interviews…"));
  try {
    const response = await fetch("/api/sessions", { cache: "no-store" });
    if (!response.ok) throw new Error("Could not load interviews");
    state.sessions = (await response.json()).sessions;
    renderSessionList();
    const firstReady = state.sessions.find((session) => session.review_status === "ready");
    if (!state.selectedId && firstReady) selectSession(firstReady.artifact_id);
  } catch (error) {
    $("session-list").replaceChildren(create("p", "empty-panel", error.message));
  }
}

function renderSessionList() {
  const query = $("session-search").value.trim().toLowerCase();
  const filtered = state.sessions.filter((session) => {
    const searchable = [
      session.session_id,
      session.plan?.title,
      session.respondent_context?.department,
      session.respondent_context?.property_id,
      session.review_status,
    ].join(" ").toLowerCase();
    return searchable.includes(query);
  });
  $("session-count").textContent = `${filtered.length} ${filtered.length === 1 ? "record" : "records"}`;
  const list = $("session-list");
  list.replaceChildren();
  if (!filtered.length) {
    list.append(create("p", "empty-panel", "No matching session artifacts."));
    return;
  }
  filtered.forEach((session) => {
    const button = create("button", "session-button");
    button.type = "button";
    button.classList.toggle("active", session.artifact_id === state.selectedId);
    button.append(badge(session.status || session.review_status, session.status || session.review_status));
    button.append(create("strong", "", session.plan?.title || "Unreadable artifact"));
    button.append(create("small", "", session.error || dateTime(session.started_at)));
    button.disabled = session.review_status !== "ready";
    if (!button.disabled) button.addEventListener("click", () => selectSession(session.artifact_id));
    list.append(button);
  });
}

async function selectSession(artifactId) {
  state.selectedId = artifactId;
  renderSessionList();
  $("empty-state").hidden = true;
  $("review-content").hidden = true;
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(artifactId)}`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not load interview");
    renderArtifact(payload);
    $("review-content").hidden = false;
  } catch (error) {
    $("empty-state").hidden = false;
    $("empty-state").querySelector("h2").textContent = "Interview could not be loaded";
    $("empty-state").querySelector("p:last-child").textContent = error.message;
  }
}

function renderArtifact(artifact) {
  const session = artifact.session;
  const synthesis = artifact.synthesis || { status: "not_run" };
  const result = synthesis.result || {};
  $("plan-title").textContent = artifact.interview_plan.title;
  $("session-subtitle").textContent = `Session ${session.id} · schema ${artifact.schema_version}`;
  $("header-badges").replaceChildren(
    badge(session.status, session.status),
    badge(label(artifact.interview_plan.id)),
  );
  const confidence = $("confidence-card");
  confidence.replaceChildren(create("small", "", "Confidence"), create("strong", "", label(result.confidence)));
  renderFacts(session, artifact.respondent_context || {});
  renderSynthesis(synthesis);
  renderCoverage(artifact.objective_coverage || []);
  renderTranscript(artifact.transcript || []);
}

function renderFacts(session, context) {
  const facts = [
    ["Started", dateTime(session.started_at)],
    ["Completion", label(session.completion_reason)],
    ["Close reason", label(session.close_reason)],
    ["Final turns", session.transcript_turns ?? 0],
  ];
  $("session-facts").replaceChildren(...facts.map(([name, value]) => {
    const card = create("div", "fact");
    card.append(create("small", "", name), create("strong", "", value));
    return card;
  }));
  const chips = Object.entries(context).map(([name, value]) =>
    create("span", "context-chip", `${label(name)}: ${label(value)}`),
  );
  $("context-chips").replaceChildren(...chips);
  if (!chips.length) $("context-chips").append(create("span", "muted", "No optional respondent context recorded."));
}

function statementCard(title, statement, extraClass = "") {
  const card = create("article", `detail-card ${extraClass}`.trim());
  card.append(create("h4", "", title));
  if (!statement) {
    card.append(create("p", "muted", "Not supported by this interview."));
    return card;
  }
  card.append(create("p", "", statement.text));
  card.append(evidenceLinks(statement.evidence_turn_ids));
  return card;
}

function renderSynthesis(synthesis) {
  $("synthesis-status").className = `badge ${synthesis.status}`;
  $("synthesis-status").textContent = label(synthesis.status);
  const container = $("synthesis-content");
  container.replaceChildren();
  if (synthesis.status !== "completed" || !synthesis.result) {
    const message = synthesis.status === "failed"
      ? `Synthesis failed (${label(synthesis.error_code)}). The transcript remains available for review.`
      : "No completed synthesis is available for this session.";
    container.append(create("div", "empty-panel", message));
    return;
  }
  const result = synthesis.result;
  const primary = create("article", "finding-card");
  primary.append(create("h4", "", "Operational issue"));
  primary.append(create("p", "", result.operational_issue.text));
  primary.append(evidenceLinks(result.operational_issue.evidence_turn_ids));
  container.append(primary);

  const grid = create("div", "detail-grid");
  grid.append(
    statementCard("Guest or team impact", result.guest_impact),
    statementCard("Reported frequency", result.reported_frequency),
    statementCard("Reported severity", result.reported_severity),
    statementCard("Workaround", result.workaround),
    statementCard("Positive practice", result.positive_practice),
    statementCard(
      result.recommended_action ? `Recommended action · ${label(result.recommended_action.scope)}` : "Recommended action",
      result.recommended_action,
    ),
  );
  (result.root_cause_hypotheses || []).forEach((hypothesis, index) => {
    grid.append(statementCard(`Root-cause hypothesis ${index + 1}`, hypothesis));
  });
  (result.representative_quotes || []).forEach((quote) => {
    const card = create("article", "detail-card");
    card.append(create("h4", "", "Representative quote"));
    card.append(create("blockquote", "", `“${quote.text}”`));
    card.append(evidenceLinks([quote.turn_id]));
    grid.append(card);
  });
  const gaps = create("article", "detail-card full");
  gaps.append(create("h4", "", "Evidence gaps"));
  gaps.append(create("p", "", (result.evidence_gaps || []).join(" · ") || "No gaps recorded by synthesis."));
  grid.append(gaps);
  container.append(grid);
}

function renderCoverage(coverage) {
  const grid = $("coverage-grid");
  grid.replaceChildren();
  coverage.forEach((objective) => {
    const card = create("article", "coverage-card");
    const top = create("div", "coverage-top");
    top.append(create("h4", "", label(objective.objective_id)), badge(objective.status, objective.status));
    card.append(top);
    const evidence = objective.evidence || [];
    if (!evidence.length) card.append(create("p", "muted", "No structured evidence recorded."));
    evidence.forEach((note) => {
      const row = create("div", `evidence-note ${note.active ? "" : "superseded"}`.trim());
      row.append(document.createTextNode(note.summary));
      if (note.source_turn_id) row.append(evidenceLinks([note.source_turn_id]));
      card.append(row);
    });
    grid.append(card);
  });
}

function renderTranscript(turns) {
  $("turn-count").textContent = `${turns.length} finalized turns`;
  const transcript = $("transcript");
  transcript.replaceChildren();
  if (!turns.length) {
    transcript.append(create("div", "empty-panel", "No finalized transcript turns were captured."));
    return;
  }
  turns.forEach((turn) => {
    const article = create("article", "turn");
    article.id = `transcript-${turn.id}`;
    const meta = create("div", "turn-meta");
    meta.append(create("strong", "", turn.role), create("span", "", turn.id));
    if (turn.interrupted) meta.append(badge("interrupted", "failed"));
    article.append(meta, create("p", "", turn.text));
    transcript.append(article);
  });
}

$("refresh-button").addEventListener("click", loadSessions);
$("session-search").addEventListener("input", renderSessionList);
loadSessions();
