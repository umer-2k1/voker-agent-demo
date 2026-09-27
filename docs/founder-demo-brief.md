# Voker Voice — Founder Demo Brief

## One-line pitch

> Voker is an evidence-backed intelligence platform for voice agents. It reconstructs the full conversation pipeline and explains why calls succeeded, failed, escalated, or were abandoned.

Voker observes existing runtimes such as LiveKit, Vapi, Retell, STT providers, LLMs, TTS providers, telephony systems, local tools, and MCP tools.

```text
Caller speech → STT → agent/LLM → tools/MCP → handoffs → TTS → playback → outcome
```

The USP is not just tracing. It is:

```text
Runtime evidence → measurements → failure detection → analysis → explanation with evidence
```

## What the application tracks

### Sessions

One conversation or call: agent, version, environment, source, start/end time, status, outcome, trace ID, external ID, metadata, event count, and error count.

### Turns

Speaker, sequence, timestamps, transcript, interruption, and abandonment information.

### Agent runs

Multiple agents, graph runs, parent/child relationships, versions, statuses, and handoffs.

### Spans

Timed STT, LLM, tool/MCP, TTS, playback, graph-node, and agent operations. Each span can include provider, model, input, output, duration, status, usage, and errors.

### Events

Individual observations such as:

```text
session.started, speech.stopped, stt.completed, llm.first_token,
tool.started, tool.completed, tts.first_audio, playback.started,
voice.interruption, voice.talk_over, outcome.recorded, session.ended
```

### Errors, usage, and cost

Errors include type, code, message, retryability, retry count, provider request ID, and evidence links. Usage can include tokens, audio seconds, TTS characters, provider/model, and exact or estimated cost.

## Metrics

### Pipeline metrics

- STT first interim and finalization
- LLM time to first token and total duration
- Tool/MCP duration and failures
- TTS time to first audio and total duration
- Response gap and turn latency
- Provider/model latency, usage, and cost

### Voice behavior

- Interruptions
- Talk-over
- Corrections
- Abandoned turns
- Dead-air observations
- Agent handoffs

### Business and quality

- Resolution rate
- Escalation rate
- Abandonment rate
- Error rate
- Intent distribution
- Outcome by intent, agent, version, provider, or model
- Tool failure patterns
- Cost per session

## Are the numbers random?

No. Voker has three evidence levels.

### Direct observations

Facts emitted by the runtime or provider:

```text
The tool returned an error.
TTS first audio arrived at 920 ms.
The caller interrupted playback.
The session ended with outcome "resolved".
```

### Deterministic findings

Versioned rules compare observed values with explicit thresholds. Current thresholds include:

```text
STT finalization: 1200 ms
LLM TTFT:          1500 ms
Tool duration:     5000 ms
TTS first audio:   1200 ms
Response gap:      2500 ms
```

These are Voker operational thresholds, not universal industry laws. A finding stores the rule/version, observed value, threshold, severity, and exact evidence IDs.

### Semantic findings

After a call, a controlled evaluator LLM can analyze bounded evidence for intent, resolution, misunderstanding, unsupported answers, incorrect tool use, frustration, and failure category.

Semantic findings are labeled inferred, versioned by model/prompt/schema, schema-validated, and required to cite existing transcript turns, events, or spans.

The product distinguishes:

```text
Confirmed fact | Detected condition | Inferred finding | Unknown
```

## Intent and conversion

Intent may be explicitly emitted by the agent/provider:

```json
{
  "event_type": "intent.detected",
  "attributes": {
    "intent": "reschedule appointment",
    "confidence": 0.92,
    "source": "agent-router"
  }
}
```

Voker normalizes intents into stable categories such as:

```text
appointment_booking
appointment_reschedule
appointment_cancellation
billing_refund
technical_support
unknown
```

The strongest conversion signal is explicit application instrumentation:

```python
call.record_outcome("resolved")
```

Other sources can be provider analysis, agent business logic, escalation/abandonment events, or semantic inference. Voker stores `outcome_source` and does not treat missing outcomes as failures.

Founder-safe wording:

> Voker reports resolution based on observed outcome signals. It does not fabricate success when the application did not provide one.

Cohort comparisons require enough data and show association, not causation. The current Voice Impact calculation uses a minimum cohort size of five sessions.

## Dead air and response gap

The current deterministic response-gap measurement is:

```text
speech.stopped → playback.started
```

Example:

```text
speech.stopped:    10:00:05.200
playback.started:  10:00:07.200
response gap:      2,000 ms
```

The source is the two event timestamps for the same turn. Voker can show their event IDs, turn ID, and surrounding STT/LLM/TTS spans.

This is an evidence-backed response gap, not necessarily two seconds of acoustic silence. It can include STT finalization, LLM generation, tool execution, TTS startup, network delay, and playback scheduling.

The current dead-air rule triggers above 2,500 ms. Therefore, a 2,000 ms response gap is latency evidence but does not trigger the deterministic dead-air finding unless an explicit `voice.dead_air` event exists.

To make a stronger acoustic claim, we need waveform silence, VAD intervals, playback-buffer data, or transport-level timing.

## Event capture and storage flow

Voker does not write audio samples every millisecond into PostgreSQL. Integrations listen to meaningful lifecycle callbacks:

```text
speech starts/stops
transcript arrives
LLM starts / first token arrives
tool starts / finishes
TTS starts / first audio arrives
playback starts
caller interrupts
session ends
```

High-frequency VAD, turn-detector, and speaking-rate samples are filtered rather than exported individually, so they do not fill the queue before the terminal session event.

```text
Voice callback
  ↓
Canonical SDK event
  ↓
Bounded in-memory queue
  ↓
Background exporter thread
  ↓
Small gzip batch
  ↓
POST /v1/events/batch
  ↓
FastAPI validation
  ↓
PostgreSQL transaction
  ↓
Events + sessions + spans + errors + usage
```

The SDK exporter currently uses a queue of up to 2,000 events, batches up to 10 events, flushes every 250 ms, compresses with gzip, retries transient failures once, and avoids blocking the real-time voice path.

Each event has an `event_id`. PostgreSQL deduplicates retries using project/event ID uniqueness. Ingestion accepts partial batches and reports accepted, duplicate, and rejected items. Out-of-order events are supported by reconciling parent/child spans and preserving producer time separately from server receive time.

## Is telemetry lossless?

Not completely. The current design is fail-open so Voker cannot break a live voice call.

Telemetry can be lost if the in-memory queue fills, the exporter process crashes, the network request fails permanently, or the process exits before delivery. The system mitigates this with bounded queues, retries, flushes, terminal-event delivery during shutdown, diagnostics, event IDs, and server deduplication.

The accurate statement is:

> PostgreSQL is the source of truth for events accepted by Voker. The provider or agent runtime is the source of truth for events that actually occurred. Current export is best-effort and fail-open, not mathematically lossless.

If guaranteed delivery becomes a requirement, the next step is a durable local outbox or disk-backed spool with replay and dead-letter handling.

## Queue and job processing

There are two queues.

### SDK telemetry queue

An in-memory Python queue moves export off the voice-agent request path. It is not durable.

### PostgreSQL analysis queue

After a terminal session event, Voker creates jobs such as:

```text
run_deterministic_analysis
run_semantic_analysis
```

The `jobs` table stores state, attempts, schedule time, lock owner, and errors. Workers claim rows using PostgreSQL `FOR UPDATE SKIP LOCKED`, allowing multiple workers without double-processing.

States are:

```text
pending → running → completed
                 ↘ retry → running
                 ↘ dead
```

SQS and Redis are not required in the current MVP because PostgreSQL provides durable storage and worker coordination.

## Post-call analysis flow

```text
1. Terminal session event arrives
2. Session is marked completed, failed, cancelled, or incomplete
3. Trace is persisted
4. Deterministic and semantic jobs are created
5. Worker claims each job
6. Rules inspect events and spans
7. Evaluator LLM inspects bounded evidence
8. Findings are stored with evidence references
9. Dashboard displays results and analysis status
```

Analysis never runs in the real-time voice path. If the evaluator fails, the trace, transcript, errors, latency, usage, cost, and deterministic findings remain available.

## Real-life example: appointment failure

Caller:

> “Move my appointment from Monday to Thursday.”

The agent sends Wednesday to the appointment tool.

```text
user.message       Caller requested Thursday
stt.completed      Transcript captured
llm.completed      Agent chose appointment tool
tool.started       Arguments: { "date": "Wednesday" }
tool.completed     Appointment changed to Wednesday
assistant.message  Agent confirmed Wednesday
correction.detected Caller corrected the agent
outcome.recorded   failed
```

Deterministic facts show what happened. Semantic analysis may conclude:

> The agent likely misunderstood the requested appointment date.

The finding links to the caller transcript, tool input, agent response, and correction event.

## Real-life example: slow response

```text
speech.stopped:   10:10:05.000
stt.final:         10:10:05.700
llm.started:       10:10:05.720
llm.first_token:   10:10:07.100
tts.started:       10:10:07.200
tts.first_audio:   10:10:07.900
playback.started:  10:10:08.000
```

Voker can report:

```text
STT finalization: 700 ms
LLM TTFT:          1,380 ms
TTS first audio:   700 ms
Response gap:      3,000 ms
```

The explanation is:

> Playback began 3,000 ms after the caller stopped speaking. The largest visible contributor was LLM time-to-first-token at 1,380 ms, followed by TTS startup at 700 ms. The calculation links to the STT, LLM, TTS, and playback evidence.

## Founder questions and answers

### “Are you just collecting logs?”

No. Voker normalizes runtime activity into sessions, turns, agent runs, spans, events, errors, usage, costs, and outcomes. That enables latency measurement, failure detection, cohort comparison, and evidence-linked explanations.

### “How do you know latency is real?”

We store producer timestamps and calculate durations from lifecycle boundaries or provider metrics. For response gap, we subtract `speech.stopped` from `playback.started`, preserving the IDs used in the calculation.

### “How do you know it was dead air?”

Currently, we know it was a response gap, not necessarily acoustic silence. A stronger dead-air claim requires audio-level or VAD evidence.

### “What happens if Voker goes down?”

The voice agent continues because export is asynchronous and fail-open. Some telemetry may be lost if the local queue fills or the process exits before delivery. Guaranteed delivery requires a durable local outbox.

### “What if the evaluator LLM is wrong?”

Semantic findings are labeled inferred, versioned, schema-validated, and required to cite existing evidence. Deterministic facts remain available when semantic analysis fails.

### “Can you prove interruptions caused lower conversion?”

Not from observational data alone. We can report an association between interruption-heavy calls and observed resolution rates. Causation requires controlled experiments or stronger causal methodology.

### “What is the most valuable feature?”

The session intelligence view: one failed call, one explanation, and direct links to the transcript, failed tool, latency waterfall, errors, and outcome.

## Honest product caveats

The current system is strong at canonical trace capture, stage-level latency, technical failure detection, evidence-linked findings, post-call semantic analysis, outcome/cohort comparisons, and PostgreSQL-backed analysis jobs.

Describe these carefully:

- Dead air is currently primarily a response-gap measurement.
- Telemetry delivery is fail-open, not lossless.
- Semantic intent and explanations are inferences, not guaranteed facts.
- Outcome quality depends on explicit instrumentation or provider data.
- Cohort comparisons show association, not causation.
- Current thresholds are Voker operational rules, not universal benchmarks.

## Implementation references

- [Product and architecture specification](voker-voice.md)
- [Canonical ingestion](../apps/api/src/voker_voice_api/ingestion.py)
- [Deterministic analysis](../apps/api/src/voker_voice_api/analysis.py)
- [Analytics calculations](../apps/api/src/voker_voice_api/analytics.py)
- [PostgreSQL jobs](../apps/api/src/voker_voice_api/jobs.py)
- [SDK exporter](../packages/python-sdk/src/voker_voice/exporter.py)
- [Database models](../apps/api/src/voker_voice_api/models.py)
