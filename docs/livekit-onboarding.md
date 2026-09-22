# LiveKit adapter onboarding

Install the optional adapter in an existing LiveKit Agents application:

```bash
pip install "voker-voice[livekit]"
export VOKER_API_KEY="..."
```

Attach the observer immediately after creating the LiveKit ``AgentSession``. The
observer creates the Voker session, derives the external session ID and participant
metadata from the job context, and completes and flushes the trace when LiveKit emits
its public ``close`` event.

```python
from livekit.agents import AgentSession
from voker_voice.livekit import observe

agent_session = AgentSession(stt=stt, llm=llm, tts=tts)

observe(
    agent_session,
    context=ctx,
    agent="support-agent",
    version="2026-09-20.1",  # optional
)

await agent_session.start(room=ctx.room, agent=SupportAgent())
```

The adapter is fail-open and observes only public ``AgentSession.on(...)`` events.
Removing the ``observe(...)`` call restores the unmodified LiveKit application
behavior. An application that already owns a Voker session may continue to pass it as
the second positional argument.

## Optional metadata

```python
observe(
    agent_session,
    context=ctx,
    agent="support-agent",
    metadata={"deployment": "canary"},
    recording={
        "source": "livekit",
        "external_id": recording_id,
        "status": "processing",
    },
)
```

Recording metadata is optional and does not affect trace creation. It is retained as
session metadata; recording availability can later be updated through
``POST /v1/recordings``.

## What the adapter can observe

| Signal | LiveKit source | Canonical result |
| --- | --- | --- |
| Session lifecycle | Observer attachment and ``close`` | ``session.started``, ``session.ended``, and errors |
| Room and participants | Job context | Session metadata with room and participant external IDs |
| User speech boundaries | ``user_state_changed`` | ``speech.started`` and ``speech.stopped`` |
| Final/interim transcript | ``user_input_transcribed`` | STT span plus transcript |
| Per-request model metrics | ``metrics_collected`` | STT/LLM/TTS spans, provider/model, duration, first-token/audio timing, and usage |
| Tool lifecycle | ``tool_execution_updated`` and ``function_tools_executed`` | Nested tool spans and errors |
| Semantic agent transfer | ``AgentHandoff`` conversation item | Explicit handoff and parent/child agent runs |
| Generated speech | ``speech_created`` | TTS span correlated by LiveKit speech ID |
| Playback | Agent speaking state and speech handle | Playback span and interruption status |
| Talk-over | ``overlapping_speech`` | Evidence-linked talk-over observation |
| Genuine interruption | User speech during active playback or confirmed overlap | ``voice.interruption`` |
| False interruption | ``agent_false_interruption`` | Namespaced diagnostic event, never a real interruption |
| Provider errors | ``error`` | STT/LLM/TTS error where the source identifies the stage |

LiveKit does not expose every signal in every pipeline. Unknown values remain absent:

- Streaming STT can report a zero request duration; the final transcript still closes
  the transcript span.
- Token counts, model names, provider names, TTFT, and TTFB appear only when the selected
  plugin reports them.
- TTS TTFB measures generated first audio. It is not presented as physical speaker
  playback latency.
- A text-only or realtime pipeline may omit standalone STT or TTS stages.
- A recording is never assumed to exist and is not discovered from an unrelated event.
- False-interruption recovery is recorded diagnostically and is not counted as caller
  interruption.

## Development verification checklist

1. Start one conversation and confirm the external session ID matches the LiveKit room.
2. Speak once and verify speech boundaries, final transcript, one turn ID, and an STT
   span.
3. Confirm the LLM and TTS spans contain only metrics the configured plugins expose.
4. Execute one tool and verify its start and terminal events share a span ID.
5. Trigger a tool or provider failure and verify its canonical error is attached.
6. Speak while audio is playing and verify one interruption plus an interrupted playback
   span; if the pipeline does not expose overlap, record that limitation instead.
7. End the LiveKit session and verify the Voker session and active agent run complete.
8. Repeat with ``VOKER_VOICE_ENABLED=false``; the LiveKit conversation must still finish.
