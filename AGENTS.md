# AGENTS.md

## Project

This repository contains ShiftSignal, an independent LiveKit voice-agent prototype for hospitality operational research. Its first use case is a short post-shift guest-experience debrief with hotel frontline staff.

The working application is `livekit-voice-agent/`. Preserve its functioning LiveKit voice pipeline while progressively adding hospitality interview intelligence, transcript capture, and evidence-grounded synthesis.

## Product Goal

Demonstrate this complete loop:

1. A hotel employee joins a LiveKit voice session.
2. A calm AI interviewer conducts a natural, structured debrief.
3. The system captures a reliable transcript and research-objective coverage.
4. A post-interview artifact identifies the issue, impact, root-cause hypotheses, workaround, supporting evidence, and a realistically scoped action.

Do not build a generic chatbot, hotel concierge, booking assistant, or guest-support bot. Every feature must support frontline listening and operational research.

## Source of Truth

- `livekit-voice-agent/agent.py` is the current implemented voice pipeline.
- `README.md` defines the product promise and current status.
- `ARCHITECTURE.md` defines current versus planned components and system boundaries.
- `prototype-plan.md` defines implementation order and acceptance criteria.

Keep documentation honest. Do not describe planned files, databases, APIs, dashboards, providers, or integrations as implemented.

## Current Technical Direction

- LiveKit Agents is the real-time orchestration and room runtime.
- Keep the current LLM, STT, and TTS fallback behavior unless a tested change requires otherwise.
- Keep Silero VAD, multilingual turn detection, noise cancellation, latency measurement, and usage collection.
- Use typed Python models for interview plans, state, transcripts, and summaries.
- Start with one local JSON artifact per session; introduce a database only when deployment needs durable shared state.
- Use a separate post-interview synthesis step rather than asking the live interviewer to narrate or invent a final business analysis.
- Keep provider credentials in environment variables and never log or commit secret values.

Pipecat, FastAPI, Twilio, a frontend framework, and a full analytics stack are not current dependencies. Add them only for a demonstrated requirement and update the architecture when doing so.

## Interview Behavior

The agent must:

- identify itself as an AI interviewer
- explain the interview purpose and applicable anonymity boundary
- clarify that the conversation is not a performance evaluation
- ask one clear question at a time
- keep spoken turns short and neutral
- follow useful respondent details rather than rigidly reciting a questionnaire
- avoid asking for information already provided
- probe for examples, operational causes, recurrence, impact, workarounds, and proposed fixes
- distinguish what the respondent observed from what they inferred
- allow skipping, uncertainty, correction, and early exit
- reflect the main finding back for confirmation before closing
- never promise that management will take action

Do not use sarcasm. Do not praise every answer. Do not blame a respondent or ask them to identify coworkers or guests.

## Privacy and Sensitive Disclosures

- Collect only metadata needed for research, preferably categorical fields.
- Do not request guest names, room numbers, employee names, exact schedules, or contact information.
- Do not call a conversation anonymous if identifiers, room metadata, or recordings make the respondent identifiable.
- Do not enable or retain recordings without an explicit requirement, consent behavior, and retention policy.
- Do not investigate allegations, safety incidents, harassment, discrimination, medical events, or emergencies through improvisational probing.
- For sensitive disclosures, acknowledge neutrally and direct the respondent to a configured human or emergency channel when available.

## Evidence Rules

- Only finalized transcript turns may support quotes or findings.
- Attach transcript turn identifiers to extracted quotes and material findings.
- Never invent a quote, frequency, severity, cause, or recommendation.
- Label causes as hypotheses unless the transcript establishes them directly.
- State evidence gaps and confidence.
- Do not generalize one interview into a property-wide or company-wide trend.
- Cross-interview claims must remain traceable to supporting sessions and meet a defined minimum sample threshold.

## Implementation Order

1. Replace the generic tech-support prompt with the hospitality interview policy.
2. Add the post-shift interview plan and typed state for objective coverage.
3. Add tests for interview progression, repetition avoidance, skipping, correction, early exit, and completion.
4. Capture finalized transcript turns and create a versioned local session artifact.
5. Add evidence-grounded post-interview synthesis and validation tests.
6. Add more hospitality interview templates only after the first plan works well.
7. Add a small review surface for transcripts and findings.
8. Add cross-interview aggregation and durable shared storage.
9. Add distribution, telephony, or broader deployment components only after the browser voice workflow is proven.

## Coding Guidance

- Keep `agent.py` focused on LiveKit session construction and event wiring.
- Put domain behavior in small, plainly named modules.
- Prefer explicit state and validated schemas over prompt-only behavior.
- Version interview plans and output schemas.
- Make session completion idempotent; disconnects and duplicate events must not create contradictory artifacts.
- Separate partial streaming transcript events from finalized turns.
- Keep sensitive transcript text out of routine logs.
- Add fake or deterministic paths for tests that should not call voice or model providers.
- Test behavior before changing the working provider pipeline.
- Avoid premature databases, queues, microservices, and frontend frameworks.

## Validation Expectations

For behavior changes, verify at the appropriate levels:

- unit tests for state transitions and evidence rules
- deterministic transcript simulations for interview quality
- an import or startup check for the LiveKit worker
- a manual voice session for turn-taking, interruption, noise, and naturalness
- inspection of the saved session artifact and summary

Do not claim the voice experience is verified from unit tests alone. Do not claim persistence or synthesis is complete merely because a conversation succeeds.

## V1 Demo Bar

A strong demo proves that the interviewer:

- conducts a respectful four-to-six-minute hospitality debrief
- discovers a concrete guest-experience event
- probes from symptom to operational context without repeating questions
- captures recurrence, impact, workaround, and a proposed improvement
- records a positive practice
- confirms its understanding and closes naturally
- saves a transcript and produces a useful evidence-linked output

Voice connection alone is not a finished vertical slice.
