# AGENTS.md

## Project

This repo is a prototype for a real-time interview voice agent inspired by enterprise frontline/customer research systems. The goal is to show a deployable, lightweight version of the core interaction pattern:

1. A respondent joins by browser voice first, then phone later.
2. An AI interviewer conducts a natural structured interview.
3. The system captures transcript turns and interview state.
4. A post-call synthesis extracts themes, quotes, risks, and suggested actions.

This is a prototype, so favor small, working vertical slices over broad platform work.

## Build Principles

- Keep the first version lightweight, scalable, and deployable.
- Build browser voice before phone voice.
- Keep provider integrations behind small interfaces so Deepgram, ElevenLabs, LiveKit, Pipecat, and Twilio can be swapped or mocked.
- Store durable state outside the agent runtime.
- Avoid building a generic chatbot; every feature should support structured research interviews.
- Prefer boring, inspectable components: FastAPI, Pydantic, SQLite/Postgres-ready storage, Docker, and clear environment variables.

## Stack Direction

- FastAPI for the prototype API.
- Pipecat for the voice pipeline orchestration.
- LiveKit for browser/WebRTC rooms and agent participation.
- Deepgram for streaming speech-to-text.
- ElevenLabs for streaming text-to-speech.
- Twilio for inbound/outbound phone calls after browser voice works.
- SQLite for local prototype storage, with a path to Postgres.

## Implementation Order

1. Session/interview engine with text turns.
2. Transcript persistence and post-interview synthesis.
3. Browser voice transport.
4. LiveKit room/session integration.
5. Pipecat pipeline integration.
6. Deepgram STT and ElevenLabs TTS.
7. Twilio phone entry.
8. Deployment and concurrency controls.

## Coding Guidance

- Keep modules focused and names plain.
- Use Pydantic models for API boundaries and structured interview artifacts.
- Do not hardcode secrets or API keys.
- Include mock/fake modes for provider-dependent code.
- Add tests around interview state transitions and synthesis logic before changing behavior.
- Do not introduce databases, queues, or frontend frameworks before the current step needs them.

## Demo Bar

A strong demo should prove:

- The interviewer asks one clear question at a time.
- The agent can probe based on the respondent's answer.
- The transcript is saved.
- The final output has useful operational themes, representative quotes, and suggested actions.
- The architecture can support real-time audio and multiple concurrent sessions.
