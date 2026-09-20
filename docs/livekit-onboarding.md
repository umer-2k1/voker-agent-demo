# LiveKit adapter onboarding

Install the optional adapter into an existing LiveKit Agents application:

```bash
pip install "voker-voice[livekit]"
```

Create the Voker client with an ingest key, then observe the public `AgentSession`
event emitter immediately after constructing the session:

```python
from livekit.agents import AgentSession
from voker_voice import VokerVoice
from voker_voice.livekit import observe

voker = VokerVoice(api_key=os.environ["VOKER_API_KEY"])
agent_session = AgentSession(...)

with voker.session(agent="appointment-agent", session_id=room.name) as trace:
    observe(agent_session, trace)
    await agent_session.start(room=room, agent=agent)
```

The adapter observes only public `AgentSession.on(...)` events. Removing the
`observe(...)` call restores the unmodified LiveKit application behavior.

## Verification

1. Run one conversation and confirm a session appears in the dashboard.
2. Confirm a user utterance produces `stt.completed`; transcript capture depends
   on the provider event exposing text.
3. Confirm the trace contains any exposed tool, TTS/playback, metric, interruption,
   and error events.
4. Trigger a tool/provider failure and verify the canonical error and linked finding.
5. Run the hosted multi-turn acceptance script only with configured LiveKit plus
   STT/TTS provider credentials; missing provider metrics must remain unknown.
