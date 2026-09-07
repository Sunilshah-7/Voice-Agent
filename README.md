# ShiftSignal

ShiftSignal is a LiveKit voice-agent prototype for short, natural hospitality interviews. It is designed to help hotel operators learn what frontline staff observed during a shift, understand how operational problems affected guests, and identify practical improvements.

The first use case is a **post-shift guest-experience debrief** with hotel employees such as front-desk associates, housekeepers, restaurant staff, maintenance technicians, guest-services employees, and shift supervisors.

This is an independent prototype inspired by the operational-listening problem described by Arbor. It is not an Arbor product or a reproduction of Arbor's platform.

## Product Thesis

Hospitality leaders often see outcomes in reviews, satisfaction scores, and operational reports after the fact. Frontline staff usually know the missing context:

- what happened during the guest journey
- why it happened
- whether it is recurring
- how staff worked around it
- what small change could prevent it next time

ShiftSignal uses a voice interview rather than a fixed survey so it can ask a relevant follow-up, clarify the impact, and capture the respondent's own explanation.

The prototype's core promise is:

> Learn what disrupted the guest experience during each shift, why it happened, and what managers should fix first.

## Current Working System

The runnable application is in `livekit-voice-agent/`. It currently provides:

- a LiveKit Agents worker and real-time room session
- OpenAI LLM with Gemini fallback through LiveKit Inference
- Deepgram STT with AssemblyAI fallback
- Cartesia TTS with Inworld fallback
- Silero voice activity detection
- multilingual turn detection
- background voice cancellation
- interruption-aware, preemptive response generation
- per-session latency and usage metrics
- a Docker image and LiveKit project configuration

Milestones 1 through 4 are implemented. The generic assistant has been replaced with a
hospitality interviewer, a versioned post-shift plan, explicit objective coverage, turn
and time budgets, and controlled handling for skips, corrections, early exits, and
sensitive disclosures. Finalized conversation turns, evidence links, completion state,
permitted respondent context, close reason, and usage are written to a versioned local
JSON artifact when the LiveKit job shuts down. A separate post-interview model call now
produces an evidence-linked synthesis and stores either its validated result or an explicit
failure status without discarding the transcript.

The same interviewer architecture now supports three versioned hospitality plans:

- `post_shift_guest_experience` (default)
- `new_process_rollout`
- `recurring_service_breakdown`

## Target Interview

The first complete workflow is a four-to-six-minute post-shift debrief:

1. Explain the purpose, anonymity option, and privacy boundaries.
2. Ask what most affected a guest's experience during the shift.
3. Follow the most useful thread to learn what happened and why.
4. Clarify frequency, guest or staff impact, and any workaround.
5. Ask what management could change in the near term.
6. Capture something the team handled well.
7. Reflect the main finding back for correction, then close.

The interviewer should ask one question at a time. It should be calm, neutral, concise, and curious—not evaluative, overly cheerful, or interrogative.

## Session Artifact

Each interview now produces a local artifact containing:

- optional property, department, role, shift, tenure-band, and language metadata
- the timestamped transcript
- research-objective coverage with active or superseded evidence
- stable links from evidence to respondent transcript turns
- completed versus incomplete status
- completion and LiveKit close reasons
- interview-plan and artifact-schema versions
- voice-pipeline usage metrics
- synthesis status and, when successful, an evidence-linked operational finding

Artifacts are written under `livekit-voice-agent/outputs/` by default. Set
`SHIFT_SIGNAL_OUTPUT_DIR` to use another directory. The output directory is ignored by
Git and Docker so local transcripts are not accidentally committed or copied into images.

Operational synthesis includes the issue, impact, root-cause hypotheses, reported frequency
and severity, workaround, positive practice, a scoped action, representative quotes,
confidence, and evidence gaps when those fields are supported. Every material statement
references finalized respondent turns. Deterministic validation rejects unknown or
interrupted evidence, non-verbatim quotes, unsupported frequency numbers, malformed output,
and selected organization-wide overclaims. Semantic support for ordinary paraphrases remains
a model-quality concern and should be reviewed in the artifact.

Findings must remain traceable to what the respondent actually said. A single interview is evidence from one perspective, not proof of an organization-wide cause.

## Project Layout

```text
.
├── AGENTS.md                    Contributor guidance and product guardrails
├── ARCHITECTURE.md              Current and target system architecture
├── README.md                    Product overview and local operation
├── prototype-plan.md            Phased implementation plan
└── livekit-voice-agent/
    ├── agent.py                 Current LiveKit worker and voice pipeline
    ├── hospitality_agent/       Interview state, transcript, and artifact modules
    ├── tests/                   Deterministic behavior and persistence tests
    ├── pyproject.toml           Python dependencies
    ├── uv.lock                  Locked dependency graph
    ├── livekit.toml             LiveKit project and agent configuration
    └── Dockerfile               Agent deployment image
```

Implemented and planned modules are distinguished in `ARCHITECTURE.md`.

## Run the Current Agent

Requirements:

- Python 3.11 or later
- `uv`
- a LiveKit project
- LiveKit credentials available in the environment or a local `.env`

From the agent directory:

```bash
cd livekit-voice-agent
uv sync --locked
uv run agent.py download-files
uv run agent.py dev
```

For a production-style worker:

```bash
uv run agent.py start
```

Do not commit provider credentials or LiveKit secrets.

After ending a console or room session, inspect the newest JSON file in:

```text
livekit-voice-agent/outputs/
```

Optional per-session context may be passed in LiveKit job metadata under the strict
`respondent_context` key. Supported fields are `property_id`, `department`,
`role_category`, `shift_type`, `tenure_band`, `language`, and
`anonymous_participation`. Other respondent fields are rejected.

Select a non-default template with the top-level `interview_plan_id` field. For example:

```json
{
  "interview_plan_id": "new_process_rollout",
  "respondent_context": {
    "department": "front_desk",
    "shift_type": "evening"
  }
}
```

An absent or blank plan ID uses `post_shift_guest_experience`. An unknown or non-string
ID is rejected by the selector; the worker logs that metadata problem and uses the default
plan rather than guessing another template.

## Build Order

1. Replace the generic assistant with the hospitality interview policy.
2. Add an explicit interview plan, objective coverage, and stopping rules.
3. Capture finalized transcript turns and write one session artifact. **Implemented.**
4. Generate an evidence-grounded structured summary. **Implemented.**
5. Add additional hospitality interview templates. **Implemented.**
6. Build a small transcript-and-insight review surface.
7. Aggregate recurring signals across interviews, shifts, departments, and properties.
8. Add durable storage, anonymous links or QR access, retention controls, and deployment hardening.

Phone entry, a separate application API, and a full analytics product are later options. They are not dependencies for proving the first LiveKit hospitality interview.

## V1 Demo Bar

A successful V1 should show one complete story:

1. A hotel employee joins a LiveKit room.
2. The interviewer sets expectations and begins a short debrief.
3. It discovers a concrete guest-experience problem.
4. It probes from the symptom to an operational cause without following a rigid script.
5. It captures the impact, recurrence, workaround, and proposed fix.
6. It confirms its understanding and closes naturally.
7. The system saves a transcript and produces an evidence-grounded hospitality insight.

Voice quality alone is not completion. The prototype is complete only when the conversation yields a useful, reviewable research artifact.
