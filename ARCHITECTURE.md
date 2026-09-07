# Architecture

## Purpose

The project is a lightweight prototype for real-time AI interview agents. It should demonstrate the same class of system used for scaled frontline/customer research:

- live conversational interviewing
- structured interview plans
- transcript capture
- turn-level state
- post-call synthesis
- deployable session workers

## High-Level Flow

```text
Browser or phone respondent
        |
        v
Transport layer
  - Browser: LiveKit WebRTC
  - Phone: Twilio Media Streams or LiveKit telephony
        |
        v
Voice pipeline
  - Pipecat orchestration
  - VAD / turn detection
  - Deepgram streaming STT
  - Interview policy / LLM
  - ElevenLabs streaming TTS
        |
        v
Application API
  - session creation
  - interview-plan loading
  - transcript persistence
  - synthesis requests
        |
        v
Storage
  - sessions
  - turns
  - interview summaries
  - optional recordings
```

## Prototype Phases

### Phase 1: Text Interview Engine

Build the interview engine without audio first. This gives us testable behavior before real-time media complexity enters the system.

Responsibilities:

- create interview sessions
- ask intro and interview questions
- record respondent answers
- generate follow-up probes
- decide when the interview is complete
- produce a structured summary

### Phase 2: Browser Voice

Add LiveKit/Pipecat browser voice.

Responsibilities:

- create a LiveKit room for each session
- run an agent process that joins the room
- pass respondent audio into the Pipecat pipeline
- use Deepgram for speech-to-text
- use ElevenLabs for text-to-speech
- persist transcript turns as they happen

### Phase 3: Phone Interviews

Add Twilio.

Two viable routes:

- Twilio Media Streams directly into a Pipecat WebSocket transport.
- Twilio connected to LiveKit through LiveKit telephony/SIP/Twilio Connector.

For this prototype, phone should reuse the same interview engine and transcript store as browser voice.

### Phase 4: Deployable Scaling

Scale by session worker:

- one active agent job per interview
- stateless worker process
- durable session/transcript state in storage
- configured max concurrency
- optional warm worker for demo responsiveness

This avoids premature distributed systems work while preserving a credible path to scale.

## Core Modules

```text
src/interview_agent/
  main.py              FastAPI app factory and routes
  config.py            Environment-driven settings
  models.py            Pydantic API/domain models
  engine.py            Interview state machine
  synthesis.py         Lightweight summary extraction
  store.py             In-memory store now; SQLite later
```

Future modules:

```text
src/interview_agent/voice/
  pipecat_bot.py       Pipecat pipeline entrypoint
  livekit.py           LiveKit room/session helpers
  twilio.py            Twilio webhook/media stream helpers
  providers.py         Deepgram/ElevenLabs adapters
```

## Data Model

Session:

- id
- status
- interview plan
- current question index
- created timestamp
- completed timestamp

Turn:

- id
- session id
- role: interviewer or respondent
- text
- timestamp
- optional provider metadata

Summary:

- session id
- themes
- pain points
- representative quotes
- suggested actions
- confidence notes

## Provider Boundaries

Real-time providers should stay behind small adapters:

- STT provider: audio stream to transcript events
- TTS provider: text stream to audio chunks
- transport provider: user audio in and agent audio out
- room provider: create/connect/end sessions

The interview engine should not know whether the respondent came from a browser, phone, or test client.

## Deployment Shape

Minimum deployable prototype:

- Dockerized FastAPI service
- environment variables for provider keys
- `/health` endpoint
- `/sessions` endpoint
- `/sessions/{id}/turns` endpoint
- `/sessions/{id}/summary` endpoint

Managed deployment options:

- Pipecat Cloud for managed agent instances and scaling.
- LiveKit Cloud for WebRTC, agent dispatch, telephony, transcripts/traces.
- A simple container host for the API when provider-managed agent hosting is not used.

## Current Step

The current repo starts with Phase 1: a text-mode interview engine, API, and browser console. This provides the core behavior that the real-time voice system will call into.

## Browser App

The browser app is served by FastAPI from `src/interview_agent/static`.

Current screens:

- new interview form
- session list
- active interviewer prompt
- respondent reply box
- transcript view
- structured summary view

This is intentionally not a separate frontend build yet. Keeping it static avoids a Node toolchain while the core product loop is still changing.
