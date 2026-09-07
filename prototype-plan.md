# Real-Time Interview Voice Agent Prototype Plan

Date: 2026-09-05

## Goal

Build a lightweight, deployable prototype that conducts natural structured interviews at scale:

- Browser voice interviews first.
- Phone interviews second.
- Real-time transcription, interruption handling, interview-state tracking, and post-call synthesis.
- Small enough to ship quickly, but shaped like a production voice-agent system.

## Recommended Stack

- Pipecat: pipeline orchestration for voice agents.
- LiveKit: WebRTC rooms, browser voice sessions, optional cloud observability and telephony bridge.
- Deepgram: streaming speech-to-text.
- ElevenLabs: streaming text-to-speech.
- Twilio: phone calls through Media Streams or LiveKit telephony.
- FastAPI: prototype backend for session creation, interview configuration, and results.
- Postgres or SQLite: transcript and interview-result storage.
- S3-compatible object storage: optional call recordings/audio artifacts.

## V1 Architecture

User joins from browser or phone.

For browser:

1. Frontend requests an interview session from the backend.
2. Backend creates or joins a LiveKit room.
3. Pipecat/agent process joins the same room as an AI participant.
4. LiveKit transports real-time audio.
5. Pipecat pipeline runs VAD/turn detection, Deepgram STT, LLM interview policy, ElevenLabs TTS.
6. Transcript events and state updates are persisted.
7. End-of-interview summarizer extracts themes, quotes, issue tags, and follow-up recommendations.

For phone:

1. Twilio receives inbound call or places outbound call.
2. Twilio streams audio using bidirectional Media Streams, or Twilio is connected to LiveKit through LiveKit SIP/Twilio Connector.
3. The same Pipecat interview pipeline runs.
4. Results are stored using the same schema.

## V1 Features

- Interview script config: title, goal, respondent type, required questions, optional probes.
- Natural interviewer behavior: greet, explain consent, ask one question at a time, probe briefly, recover from unclear answers, close politely.
- Turn-taking: interruption support and short endpointing delays.
- Transcript capture: user utterances, agent utterances, timestamps, confidence where available.
- Structured extraction: themes, pain points, quotes, sentiment, location/role metadata, action items.
- Dashboard-lite: table of sessions and a detail page for transcript plus summary.
- Deployment: Dockerized FastAPI/Pipecat service; LiveKit Cloud or Pipecat Cloud for managed scaling.

## Scaling Shape

For a prototype, scale by one agent process per active interview. Keep the application stateless except session metadata and transcripts. Use a queue or managed deployment pool later.

Minimum viable scaling:

- One process per call/session.
- Store all durable state outside the agent process.
- Cap max concurrent sessions to control spend.
- Keep one warm worker only when demo latency matters.
- Use cloud logs/traces/transcripts for debugging.

## Build Milestones

1. Browser voice demo.
   - Local Pipecat bot.
   - Deepgram STT.
   - ElevenLabs TTS.
   - Simple interview prompt.
   - Save transcript JSON.

2. Structured interview engine.
   - Interview plan schema.
   - State machine for intro, questions, probes, close.
   - End-of-call summary.

3. LiveKit integration.
   - LiveKit room creation.
   - Agent joins room.
   - Browser client joins room.

4. Twilio phone path.
   - Inbound phone call webhook.
   - Bidirectional media stream or LiveKit telephony bridge.
   - Same interview pipeline reused.

5. Deployable demo.
   - Dockerfile.
   - Environment variable template.
   - Health endpoint.
   - Minimal dashboard.

## Why This Is A Good Application Prototype

This maps directly onto real Arbor-style work: real-time voice agents, interviews at scale, frontline/customer research, transcription, synthesis, guardrails, deployment, and observability. It is credible without needing to clone their product.
