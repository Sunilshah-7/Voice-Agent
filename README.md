# Interview Voice Agent

A lightweight prototype for real-time AI interview agents that can conduct structured frontline/customer research conversations, save transcripts, and produce operational summaries.

The first version starts with a text-mode interview engine and API. The voice stack will then plug in step by step:

- LiveKit for browser/WebRTC rooms
- Pipecat for real-time voice pipeline orchestration
- Deepgram for streaming speech-to-text
- ElevenLabs for streaming text-to-speech
- Twilio for phone interviews

## Why This Exists

Cold applications are weak. A working prototype is a stronger signal.

This project demonstrates the core pattern behind scaled AI research interviews:

1. Create an interview plan.
2. Start a respondent session.
3. Ask natural questions and follow-up probes.
4. Capture a clean transcript.
5. Synthesize themes, quotes, risks, and suggested actions.

## Current Status

Phase 1 is a deployable local web app and interview engine:

- create a session
- submit respondent answers
- receive the next interviewer prompt
- save transcript turns in memory
- generate a lightweight structured summary
- use a browser console for session creation, transcript review, and summary generation

Voice providers are intentionally not wired yet. The current slice makes the interview behavior testable before adding real-time audio.

## Project Layout

```text
.
├── AGENTS.md
├── ARCHITECTURE.md
├── README.md
├── prototype-plan.md
├── report-source.md
├── pyproject.toml
├── Dockerfile
└── src/
    └── interview_agent/
        ├── __init__.py
        ├── config.py
        ├── engine.py
        ├── main.py
        ├── models.py
        ├── static/
        ├── store.py
        └── synthesis.py
```

## Run Locally

Install dependencies:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Start the API:

```bash
uvicorn interview_agent.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

API docs are available at:

```text
http://127.0.0.1:8000/docs
```

## Example API Flow

Create a session:

```bash
curl -X POST http://127.0.0.1:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "respondent_label": "Warehouse shift lead",
    "plan": {
      "title": "Frontline operations interview",
      "goal": "Understand recurring workflow blockers and improvement ideas.",
      "questions": [
        "What part of your shift creates the most avoidable delay?",
        "What workaround do experienced teammates use that new people miss?",
        "If leadership fixed one thing this month, what should it be?"
      ]
    }
  }'
```

Submit an answer:

```bash
curl -X POST http://127.0.0.1:8000/sessions/{session_id}/turns \
  -H "Content-Type: application/json" \
  -d '{"text": "The biggest delay is waiting for inventory checks before loading."}'
```

Get a summary:

```bash
curl http://127.0.0.1:8000/sessions/{session_id}/summary
```

## Docker

Build the image:

```bash
docker build -t interview-voice-agent .
```

Run the container:

```bash
docker run --rm -p 8000:8000 --env-file .env interview-voice-agent
```

Then open:

```text
http://127.0.0.1:8000
```

## Environment

The first slice does not require provider keys.

Future voice integration will use:

```text
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
DEEPGRAM_API_KEY=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
```

## Roadmap

1. Text-mode interview engine and API.
2. Tests for state transitions and summary generation.
3. Browser voice path with LiveKit/Pipecat.
4. Deepgram STT and ElevenLabs TTS.
5. Twilio phone path.
6. Docker deployment.
7. Minimal dashboard for sessions, transcripts, and summaries.
