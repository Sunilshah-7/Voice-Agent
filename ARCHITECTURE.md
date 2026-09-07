# Architecture

## Purpose

ShiftSignal is a real-time hospitality research interviewer built on the working LiveKit Agents pipeline in `livekit-voice-agent/`. Its first job is to conduct short post-shift interviews with hotel staff and turn those conversations into traceable operational findings.

The system is intentionally narrower than a general voice assistant. Every component should support one of four outcomes:

1. make it safe and easy for frontline staff to speak
2. uncover useful detail through adaptive interview probes
3. preserve the respondent's evidence accurately
4. turn that evidence into clearly qualified action for operators

## Architecture Status

The diagrams distinguish implemented components from planned components. The current
repository contains the LiveKit voice worker, three hospitality interview plans, shared
interview state, finalized-turn recorder, local JSON artifact writer, post-interview
synthesis, transactional SQLite indexing, and thresholded cross-interview review. It does
not currently contain a separate FastAPI application, Pipecat pipeline, Postgres deployment,
semantic clustering service, or cross-interview model synthesis.

### Implemented today

```text
Respondent in LiveKit room
          |
          v
LiveKit AgentSession
  - background voice cancellation
  - Silero VAD
  - multilingual turn detection
  - interruption handling
  - preemptive generation
          |
          +--> STT: Deepgram -> AssemblyAI fallback
          |
          +--> LLM: OpenAI -> Gemini fallback
          |
          +--> TTS: Cartesia -> Inworld fallback
          |
          v
Spoken agent response

Session telemetry
  - model and pipeline metrics
  - time to first audio
  - usage summary

Committed conversation events
          |
          v
Local session artifact
  - stable transcript turn IDs
  - objective coverage and evidence links
  - completion and close state
  - plan and schema versions
  - permitted respondent context
  - validated post-interview synthesis or explicit failure status
          |
          v
Local read-only review surface
  - session list and categorical context
  - evidence-linked synthesis and coverage
  - finalized transcript
  - thresholded cross-interview signals
          |
          v
Local SQLite index
  - idempotent session ingestion
  - issue and positive-practice signals
  - supporting session and artifact links
```

The transport and provider pipeline are preserved. Milestone 1 adds the hospitality
interviewer, versioned interview plan, explicit coverage state, deterministic budget and
exit transitions, and internal tools that prevent premature completion.

### Implemented Milestone 3 flow

```text
Frontline employee
          |
          v
LiveKit voice pipeline (existing)
          |
          v
Hospitality Interviewer
  - selected versioned interview plan
  - privacy and safety policy
  - research-objective coverage
  - probe selection
  - turn/time budget
  - completion policy
          |
          +------------------+
          |                  |
          v                  v
Transcript recorder     Interview state
          |                  |
          +--------+---------+
                   v
          Session artifact (JSON first)
                   |
                   v
          Post-interview synthesis
          - issue and guest impact
          - root-cause hypotheses
          - frequency and severity
          - workaround
          - positive practice
          - recommended action
          - evidence and confidence
```

JSON files are sufficient for the first locally reviewable vertical slice. A transactional database becomes necessary when multiple deployed workers must share durable state.

## Architectural Boundaries

### 1. Voice pipeline

Owns real-time media behavior:

- room participation
- speech recognition and synthesis
- voice activity and turn detection
- interruptions and endpointing
- provider fallback
- latency and usage metrics

It should not decide which research objective matters next or fabricate a business finding.

### 2. Interview intelligence

Owns the research conversation:

- opening and consent language
- respondent context
- required and optional objectives
- follow-up selection
- repetition avoidance
- explicit binding between each spoken question and its research objective
- handling skips, uncertainty, and early exits
- safety escalation language
- closing and completion reason

This should be explicit application state rather than relying entirely on an increasingly large prompt.

### 3. Evidence capture

Owns the audit trail:

- finalized respondent and interviewer turns
- timestamps and stable turn identifiers
- optional speech-provider confidence and language
- objective-to-turn evidence links
- active and superseded evidence when a respondent corrects an earlier statement
- session metadata and completion state

Only finalized turns should be treated as quotable evidence. Partial streaming transcripts may be useful for the live experience but must not silently become the final record.

A respondent correction must supersede the affected earlier evidence rather than merely
append a contradictory note. Likewise, a skip applies to the objective of the question
actually asked, not whichever objective happens to be first in the plan.

### 4. Synthesis

Owns structured interpretation after the interview:

- separates observations from hypotheses
- cites transcript turns for findings and quotes
- describes missing evidence
- qualifies confidence
- avoids inferring prevalence from one interview
- recommends appropriately scoped follow-up or action

Cross-interview aggregation is a later layer and should consume structured individual interview artifacts rather than raw audio.

## Domain Model

### InterviewPlan

- identifier and version
- title and business goal
- respondent type
- target duration and maximum turns
- required research objectives
- optional probes
- opening and closing policy
- safety and privacy rules

### ResearchObjective

- identifier
- question the research needs to answer
- evidence requirements
- optional domain-specific probes
- coverage state: not started, partial, sufficient, skipped
- supporting transcript turn identifiers

### RespondentContext

All fields should be optional or categorical where possible:

- property identifier
- department
- role category
- shift type
- tenure band
- preferred language
- anonymous participation flag

Do not request guest names, room numbers, employee names, exact schedules, or other identifiers that are unnecessary for the research goal.

### InterviewState

- session identifier
- plan version
- phase: opening, interviewing, confirmation, closing, completed
- current objective
- objective coverage
- turns and elapsed-time budget
- consent/privacy acknowledgement
- completion reason

### InterviewSummary

- primary operational issue
- guest and staff impact
- supported root-cause hypotheses
- reported frequency and severity
- workaround
- positive practice
- recommended action
- representative quotes and evidence turns
- confidence and evidence gaps

## Interview Template Set

All templates use the same interviewer, state, transcript, and synthesis contracts. The
LiveKit worker selects a template using the optional top-level job-metadata field
`interview_plan_id`; the post-shift plan remains the default.

### Post-shift guest experience

The default plan is `post_shift_guest_experience`.

Its research objectives are:

1. Identify the event that most affected a guest's experience.
2. Locate the affected point in the guest journey.
3. Understand the operational conditions or handoffs behind it.
4. Establish whether the event appears isolated or recurring.
5. Capture the consequence for guests and staff.
6. Capture any workaround employees currently use.
7. Ask for one realistic improvement.
8. Capture a positive practice worth repeating.

These are objectives, not a script that must be recited in order. The interviewer should use information already supplied and ask only the next question that materially improves the research record.

### New process rollout

`new_process_rollout` checks a new process or training against real-shift experience,
expectation clarity, preparedness, workflow effect, friction, support or workarounds, an
improvement, and a positive element worth retaining.

### Recurring service breakdown

`recurring_service_breakdown` develops a firsthand example into the journey stage,
observed conditions, recurrence, impact, workaround, prior responses, a scoped next step,
and a positive recovery practice. It explicitly avoids turning the interview into an
investigation of individuals.

## Interview Policy

The interviewer must:

- ask one clear question at a time
- keep spoken responses concise
- acknowledge without judging or performing exaggerated empathy
- probe for examples, causes, frequency, consequences, and possible improvements
- avoid repeating answered questions
- let respondents skip, say they do not know, or end the interview
- avoid blaming staff or asking them to identify another person
- reflect the principal finding back before closing
- never promise that management will act on the feedback

Potential safety, harassment, discrimination, medical, or emergency disclosures should not be investigated conversationally. The agent should acknowledge the concern, avoid promises, and direct the respondent to the configured human or emergency channel when one exists.

## Code Shape

```text
livekit-voice-agent/
├── agent.py
├── review_app.py               Local read-only HTTP and artifact API
├── review/                     Static review UI
├── hospitality_agent/
│   ├── interviewer.py        LiveKit Agent behavior and session coordination
│   ├── plans.py              Three versioned hospitality plans and strict selection
│   ├── state.py              Objective coverage and completion state
│   ├── transcript.py         Final turn capture and session artifact writing (implemented)
│   ├── synthesis.py          Evidence-grounded extraction and validation (implemented)
│   ├── review.py             Safe local artifact discovery and loading (implemented)
│   ├── intelligence.py       SQLite indexing and thresholded aggregation (implemented)
│   └── models.py             Typed domain and artifact models
├── outputs/                  Local-only artifacts; do not commit sensitive data
└── tests/
```

The interviewer, plan registry, state, transcript, synthesis, and model modules are implemented.
Synthesis runs only after the spoken interview and cannot prevent transcript persistence
when generation or validation fails.

The review server is a separate local process backed by Python's standard library. It reads
the same JSON artifacts and exposes only explicit list, detail, and static-asset routes. It
does not modify artifacts, use a model to invent aggregate findings, or become part of the
LiveKit media worker.

Phase 6 adds a transactional SQLite index beside the local artifacts. The worker indexes a
saved artifact only after JSON persistence succeeds; database failure is observable but does
not destroy that artifact. The review server also performs idempotent artifact synchronization
before returning its intelligence snapshot.

## Storage Evolution

### V1: local artifact

- one structured JSON document per completed or interrupted session
- suitable for local demos and behavior testing
- recordings disabled unless explicitly needed
- atomic, idempotent writes under `outputs/` or `SHIFT_SIGNAL_OUTPUT_DIR`
- unique LiveKit job identity prevents room-name reuse from overwriting another interview

### Deployed prototype

- transactional SQLite for a single worker or Postgres for multiple workers
- durable session, turn, summary, and plan-version records
- explicit retention and deletion behavior
- optional encrypted object storage for consented recordings

Agent processes must not be described as stateless until all required interview state and transcripts survive worker termination.

## Cross-Interview Intelligence

After individual artifacts are reliable, aggregation can identify:

- repeated issues by property, department, role, or shift
- emerging operational risks
- differences between high- and low-performing properties
- transferable positive practices
- issues whose reported frequency or severity is rising

The implemented local intelligence layer:

- indexes every session durably, while extracting signals only from completed syntheses
- groups conservative normalized matches for issues and positive practices
- withholds any group supported by fewer than three interviews
- supports grouping by property, department, role category, or shift type
- labels issues as emerging or increasing only when the recent 30-day window has at least
  three interviews and exceeds the preceding equal-length window
- returns supporting session and artifact identifiers for every displayed signal

Counts represent interviews, not unique people or independently verified incidents.
Normalized matching is intentionally narrower than semantic clustering, so differently
worded descriptions of the same underlying issue may remain separate. SQLite is appropriate
for the current local or single-worker topology; multiple deployed workers require Postgres
or another transactional shared store.

## Deployment Direction

The current deployment unit is the containerized LiveKit agent worker. Near-term deployment work should focus on:

- environment-based credentials
- health and readiness behavior appropriate to LiveKit workers
- controlled concurrency
- plan and prompt versioning
- structured logging without sensitive transcript content
- session completion under disconnects and provider failures
- retention controls for transcript artifacts

Phone/SIP entry, a separate application API, QR-code distribution, and a reviewer dashboard are optional later components. They should reuse the same interview plan, state, transcript, and synthesis contracts.

## Quality Attributes

### Naturalness

Measure interruption recovery, unnecessary repetition, response length, silence, and time to first audio—not only whether the call connects.

### Research quality

Measure objective coverage, useful probe rate, unsupported inference, evidence linkage, and whether a reviewer can understand the proposed action.

### Privacy

Minimize metadata, avoid unnecessary identifiers, make anonymity language accurate, and define retention before collecting production interviews.

### Reliability

Test disconnects, partial transcripts, duplicate events, provider fallback, early exits, and synthesis failure. Conversation completion and artifact completion are separate states.
