import logging

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, room_io
from livekit.plugins import noise_cancellation, silero
# Import the multilingual turn detection model
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents import llm, stt, tts, inference
from livekit.agents import AgentStateChangedEvent, MetricsCollectedEvent, metrics
import time

logger = logging.getLogger(__name__)
load_dotenv()


# Define your agent's behavior by extending the Agent class
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            # Define personality: tone, style, and constraints
            instructions=(
                "You are an upbeat, slightly sarcastic voice AI for tech support. "
                "Help the caller fix issues without rambling, and keep replies under 3 sentences."
            ),
        )


server = AgentServer()
vad = silero.VAD.load()

# The entrypoint function runs when a participant joins the room
@server.rtc_session()
async def entrypoint(ctx: JobContext):
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
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        nonlocal last_eou_metrics
        # Capture EOU metrics for TTFA calculation
        if ev.metrics.type == "eou_metrics":
            last_eou_metrics = ev.metrics

        # Log each metric as it arrives and add to usage collector
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)


    async def log_usage():
        # Print per-session summary (tokens, audio duration, costs)
        summary = usage_collector.get_summary()
        logger.info("Usage summary: %s", summary)


    # Fire log_usage when worker shuts down
    ctx.add_shutdown_callback(log_usage)
    

    @session.on("agent_state_changed")
    def _on_agent_state_changed(ev: AgentStateChangedEvent):
        if ev.new_state == "speaking":
            if last_eou_metrics:
                # Calculate time since user finished speaking
                elapsed = time.time() - last_eou_metrics.timestamp
                logger.info(f"Time to first audio: {elapsed:.3f}s")

    # Start the session with noise cancellation enabled
    await session.start(
        agent=Assistant(),
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
