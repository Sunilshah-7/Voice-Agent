# ShiftSignal Prototype Plan

Date: 2026-09-06

## Objective

Turn the working LiveKit voice agent into a focused hospitality research prototype that conducts natural post-shift interviews and produces evidence-grounded operational insights.

The plan protects the working voice path and builds one small vertical slice at a time. The first milestone is not a platform, a generic survey builder, or an Arbor clone. It is one excellent hospitality interview with one reviewable output.

## Chosen Use Case

**Post-shift guest-experience debrief**

Target respondents include front-desk associates, housekeepers, food-and-beverage staff, maintenance technicians, guest-services employees, and shift supervisors.

Target duration: four to six minutes.

Research question:

> What happened during this shift that most affected a guest's experience, why did it happen, and what practical change could improve it?

## Existing Foundation

The `livekit-voice-agent/` directory already contains the working real-time pipeline:

- LiveKit AgentSession
- LLM, STT, and TTS provider fallbacks
- voice activity and multilingual turn detection
- background voice cancellation
- preemptive generation and interruption support
- latency and usage metrics
- LiveKit configuration and container deployment files

The immediate work is therefore product behavior and research output—not replacement of the real-time audio architecture.

## Product Principles

- Treat interview objectives as a flexible research map, not a fixed script.
- Ask one question at a time and follow the respondent's most useful detail.
- Prefer a short clarifying probe over generic encouragement.
- Protect respondent dignity and avoid evaluative or blame-oriented language.
- Minimize collection of identifiable information.
- Preserve transcript evidence before generating an interpretation.
- Clearly separate observations, hypotheses, and recommendations.
- Do not infer organization-wide prevalence from an individual interview.
- Optimize for a usable manager decision, not merely a complete transcript.

## Milestone 1: Hospitality Interviewer

**Status: implemented and locally validated.** Live voice quality still requires a manual
room session; the state, policy, tool wiring, worker import, and deterministic scenarios
are covered by the local validation suite.

The implementation batches all objectives supported by each respondent turn, binds every
research question to its objective, supersedes stale evidence after corrections, and limits
the final confirmation to a short voice-friendly statement.

### Build

- Replace the generic tech-support instructions.
- Add a hospitality interviewer class.
- Add a versioned `post_shift_guest_experience` plan.
- Track phases: opening, interviewing, confirmation, closing, completed.
- Track objective coverage separately from question order.
- Add time and turn budgets.
- Add skip, correction, uncertainty, early-exit, and sensitive-disclosure behavior.
- Generate an explicit opening and natural closing.

### Acceptance criteria

- The agent identifies itself and accurately sets expectations.
- It asks only one question at a time.
- It does not ask for details already supplied.
- It can leave the nominal question order to pursue useful evidence.
- It returns to uncovered objectives after a probe.
- It reflects the main finding back before closing.
- It completes within the configured budget.

### Test scenarios

- Front desk: rooms unavailable at check-in because status updates lag.
- Housekeeping: supply shortage creates inconsistent room readiness.
- Restaurant: kitchen-to-server handoff causes long guest wait times.
- Maintenance: recurring HVAC complaints are temporarily worked around.
- Positive shift: no major incident, but one practice is worth sharing.
- Minimal respondent: short answers, skips, and an early exit.
- Sensitive disclosure: agent acknowledges without investigating.

## Milestone 2: Transcript and Session Artifact

**Status: implemented and locally validated.** The LiveKit worker captures committed
conversation turns, links objective evidence to stable respondent turn IDs, records close
and completion state, and atomically writes one versioned JSON artifact per job. A real
room or console shutdown should still be checked once in the user's LiveKit environment.

### Build

- Capture finalized agent and respondent transcript turns.
- Assign stable turn identifiers and timestamps.
- Preserve interview plan and schema versions.
- Save respondent metadata only when supplied and allowed.
- Record objective coverage and completion reason.
- Write one JSON artifact per session for local development.
- Keep partial transcripts and routine logs out of the evidence record.

### Acceptance criteria

- Every final quote can be traced to a respondent turn.
- A disconnect or duplicate completion event cannot create contradictory results.
- An incomplete interview remains distinguishable from a completed one.
- No secrets or unnecessary personal identifiers appear in the artifact.
- Failure to write the artifact is observable and not reported as success.

## Milestone 3: Evidence-Grounded Synthesis

**Status: implemented and locally validated.** A separate post-interview model call produces
a typed result, cites finalized respondent turns, and is saved inside artifact schema 1.1.
Generation or validation failure is recorded without losing the transcript. Deterministic
tests cover malformed output, invalid or interrupted evidence links, invented quotations,
invented numeric frequency, organization-wide overclaims, and superseded evidence exclusion.
A real provider-backed shutdown and qualitative review remain manual checks.

### Build

- Run synthesis after the interview rather than inside the spoken conversation.
- Produce a validated structured result.
- Link findings and quotes to transcript turn identifiers.
- Include operational issue, guest impact, root-cause hypotheses, frequency, severity, workaround, positive practice, recommendation, confidence, and evidence gaps.
- Reject or flag unsupported structured fields.

The current validator enforces evidence identity, quote fidelity, numeric-frequency
grounding, schema shape, and selected overclaim rules. It does not establish full semantic
entailment for every model paraphrase, so the evidence links and gaps remain reviewer-visible.

### Acceptance criteria

- The summary does not invent facts or quotations.
- The primary finding is supported by cited turns.
- Root causes are labeled as hypotheses where appropriate.
- Frequency reflects the respondent's wording rather than an invented number.
- The recommendation is proportionate to the evidence.
- A reviewer can inspect why the system reached its conclusion.

## Milestone 4: Hospitality Template Set

**Status: implemented and locally validated.** The plan registry now includes the original
post-shift debrief, a new-process or training rollout check-in, and a recurring
service-breakdown investigation. Each plan owns its objectives, opening question,
completion objectives, duration, and turn budget while reusing the existing interviewer,
state, transcript, and synthesis contracts. Strict LiveKit job-metadata selection is tested;
a real voice session for each new plan remains a manual quality check.

Add templates only after the first interview is reliable:

1. Post-shift guest-experience debrief.
2. New process or training rollout check-in.
3. Recurring service-breakdown investigation.

All templates should reuse the same plan, state, transcript, and synthesis contracts. Templates vary research objectives and domain probes; they do not create separate agent architectures.

## Milestone 5: Review Surface

**Status: implemented and locally validated.** A responsive, read-only local web interface
lists saved sessions and renders status, permitted context, synthesis, coverage, evidence
gaps, and the finalized transcript. Evidence controls navigate to supporting turn IDs;
failed synthesis, incomplete sessions, interrupted turns, and superseded evidence remain
visible. Loader and route tests cover malformed files, unknown sessions, path traversal,
and write attempts. Browser rendering remains a manual visual acceptance check.

Build a small operator-facing review experience showing:

- interview status and completion reason
- permitted property, department, role, and shift metadata
- transcript with stable turn identifiers
- objective coverage
- primary issue and guest impact
- root-cause hypotheses
- workaround and positive practice
- recommended action
- quotes, evidence, confidence, and gaps

The review surface should make evidence inspection easier. It should not imply that one interview represents a trend.

## Milestone 6: Cross-Interview Intelligence

After individual artifacts are trustworthy:

- group recurring issues across property, department, role, and shift
- compare patterns between properties using minimum sample thresholds
- detect newly emerging or increasing issues
- surface successful practices that may transfer elsewhere
- retain links from every aggregate finding to supporting interviews

At this stage, move from local JSON to durable transactional storage suitable for the deployment topology.

## Milestone 7: Distribution and Deployment

Potential additions:

- anonymous browser participation links
- QR-code distribution
- plan selection and respondent metadata setup
- controlled worker concurrency
- prompt, plan, and schema version tracking
- transcript retention and deletion controls
- deployment monitoring that excludes sensitive content
- optional LiveKit SIP or phone entry

Phone support is not required for the first compelling prototype. It should reuse the same interview intelligence and artifact pipeline when introduced.

## Explicit Non-Goals for Early Milestones

- cloning Arbor's interface or brand
- a general-purpose chatbot
- hotel reservations or guest concierge features
- a survey-form builder
- multi-agent orchestration
- a full enterprise dashboard
- predictive scoring from insufficient interviews
- automatic managerial action without human review
- adding Pipecat, FastAPI, Twilio, or a new database before a concrete requirement

## Definition of V1 Complete

V1 is complete when a real voice session can:

1. conduct the post-shift interview naturally
2. discover and clarify an operational event
3. avoid rigid or repetitive questioning
4. confirm the respondent's meaning
5. save a reliable final transcript
6. create a structured, evidence-linked hospitality insight
7. expose failures and incomplete sessions honestly

A working call without transcript persistence and evidence-grounded output is an important checkpoint, but it is not the completed V1.
