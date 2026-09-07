import logging
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
    HospitalityInterviewer,
    POST_SHIFT_GUEST_EXPERIENCE,
    TranscriptRecorder,
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
        respondent_context = respondent_context_from_job_metadata(ctx.job.metadata)
    except ValueError as exc:
        logger.warning("Ignoring invalid respondent context metadata: %s", exc)
        respondent_context = respondent_context_from_job_metadata(None)
    recorder = TranscriptRecorder(
        plan=POST_SHIFT_GUEST_EXPERIENCE,
        session_id=ctx.job.id or None,
        respondent_context=respondent_context,
    )
    interviewer = HospitalityInterviewer(
        plan=POST_SHIFT_GUEST_EXPERIENCE,
        recorder=recorder,
    )
    # Configure the voice pipeline with STT, LLM, TTS, and VAD providers
    session = AgentSession(
        # LLM with fallback: OpenAI primary, Gemini backup
        llm=llm.FallbackAdapter(
            [
                inference.LLM(model="openai/gpt-4.1-mini"),
                inference.LLM(model="google/gemini-2.5-flash"),
            ]
        ),
        # LiveKit Inference uses existing LiveKit credentials; no Deepgram key needed.
        # STT with fallback: Deepgram primary, AssemblyAI backup
        stt=stt.FallbackAdapter(
            [
                inference.STT.from_model_string("deepgram/nova-3:en"),
                inference.STT.from_model_string("assemblyai/universal-streaming:en"),
            ]
        ),
        # ElevenLabs retired from LiveKit Inference on 2026-08-31 and now needs
        # a separate provider key. Keep TTS on LiveKit Inference for key-free setup.
        # TTS with fallback: Cartesia primary, Inworld backup
        tts=tts.FallbackAdapter(
            [
                inference.TTS.from_model_string("cartesia/sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"),
                inference.TTS.from_model_string("inworld/inworld-tts-1"),
            ]
        ),
        vad=vad,
        turn_detection=MultilingualModel(),
        preemptive_generation=True,
    )
    # Aggregate data across all conversation turns
    usage_collector = metrics.UsageCollector()

    # Track End of Utterance timing (when turn detector decides user finished speaking)
    last_eou_metrics: metrics.EOUMetrics | None = None

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent) -> None:
        nonlocal last_eou_metrics
        # Capture EOU metrics for TTFA calculation
        if ev.metrics.type == "eou_metrics":
            last_eou_metrics = ev.metrics

        # Log each metric as it arrives and add to usage collector
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def persist_session() -> None:
        summary = usage_collector.get_summary()
        logger.info("Usage summary: %s", summary)
        try:
            path = recorder.finalize(interviewer.interview_state, usage=vars(summary))
        except ArtifactWriteError:
            logger.exception("Session ended but its artifact could not be written")
            return
        logger.info("Session artifact written: %s", path)

    ctx.add_shutdown_callback(persist_session)

    @session.on("conversation_item_added")
    def _on_conversation_item_added(ev: ConversationItemAddedEvent) -> None:
        if isinstance(ev.item, llm.ChatMessage):
            recorder.record_chat_message(ev.item)

    @session.on("close")
    def _on_close(ev: CloseEvent) -> None:
        recorder.set_close(ev.reason, created_at=ev.created_at)

    @session.on("agent_state_changed")
    def _on_agent_state_changed(ev: AgentStateChangedEvent) -> None:
        if ev.new_state == "speaking":
            if last_eou_metrics:
                # Calculate time since user finished speaking
                elapsed = time.time() - last_eou_metrics.timestamp
                logger.info(f"Time to first audio: {elapsed:.3f}s")

    # Start the session with noise cancellation enabled
    await session.start(
        agent=interviewer,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=noise_cancellation.BVC(),  # Background voice cancellation
            ),
        ),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agents.cli.run_app(server)
