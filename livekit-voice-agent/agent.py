import logging
import os
import time

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    AgentServer,
    AgentSession,
    AgentStateChangedEvent,
    CloseEvent,
    ConversationItemAddedEvent,
    JobContext,
    MetricsCollectedEvent,
    room_io,
)
from livekit.agents import inference, llm, metrics, stt, tts
from livekit.plugins import noise_cancellation, silero

# Import the multilingual turn detection model
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from hospitality_agent import (
    ArtifactWriteError,
    DEFAULT_INTERVIEW_PLAN,
    HospitalityInterviewer,
    IntelligenceStore,
    IntelligenceStoreError,
    LiveKitTextGenerator,
    TranscriptRecorder,
    SynthesisError,
    SynthesisService,
    interview_plan_from_job_metadata,
    respondent_context_from_job_metadata,
)

logger = logging.getLogger(__name__)
load_dotenv()


server = AgentServer()
vad = silero.VAD.load()

# The entrypoint function runs when a participant joins the room
@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    try:
        interview_plan = interview_plan_from_job_metadata(ctx.job.metadata)
    except ValueError as exc:
        logger.warning("Using default interview plan after invalid metadata: %s", exc)
        interview_plan = DEFAULT_INTERVIEW_PLAN
    try:
        respondent_context = respondent_context_from_job_metadata(ctx.job.metadata)
    except ValueError as exc:
        logger.warning("Ignoring invalid respondent context metadata: %s", exc)
        respondent_context = respondent_context_from_job_metadata(None)
    recorder = TranscriptRecorder(
        plan=interview_plan,
        session_id=ctx.job.id or None,
        respondent_context=respondent_context,
    )
    interviewer = HospitalityInterviewer(
        plan=interview_plan,
        recorder=recorder,
    )
