const state = { sessions: [], selectedId: null, mode: "session" };

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
    button.classList.toggle(
      "active",
      state.mode === "session" && session.artifact_id === state.selectedId,
    );
    button.append(badge(session.status || session.review_status, session.status || session.review_status));
    button.append(create("strong", "", session.plan?.title || "Unreadable artifact"));
    button.append(create("small", "", session.error || dateTime(session.started_at)));
    button.disabled = session.review_status !== "ready";
    if (!button.disabled) button.addEventListener("click", () => selectSession(session.artifact_id));
    list.append(button);
  });
}
