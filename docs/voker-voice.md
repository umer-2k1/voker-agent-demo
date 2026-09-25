# Voker Voice — Voice-Agent Intelligence Platform

Status: implementation source of truth for the MVP
Audience: product, design, backend, frontend, SDK, and integration engineers

## 1. Product definition

Voker Voice is a developer-first voice-agent intelligence platform built on a trustworthy observability foundation. It connects to an existing voice-agent application, reconstructs the complete path of a conversation, and turns that evidence into explanations of agent outcomes and failures:

```text
caller speech
  -> speech-to-text
  -> agent/LLM reasoning
  -> tools and MCP servers
  -> agent handoffs
  -> text-to-speech
  -> audio playback
```

The product answers three questions, in priority order:

1. Why did this conversation succeed, fail, escalate, or get abandoned?
2. What exact transcript turns, events, tools, handoffs, and provider operations support that conclusion?
3. Where did latency, cost, error, or undesirable agent behavior enter the pipeline, and what patterns recur across sessions?

The canonical trace is the evidence foundation, not the final product experience. Voker’s primary value is the intelligence layer that explains outcomes, finds likely contributing factors, connects technical behavior to agent performance, and directs developers to the exact evidence.

> **Positioning:** Voice-agent intelligence built on top of a proper observability foundation.

Voker Voice is not a voice runtime. It does not replace LiveKit, Vapi, Retell, an STT provider, an LLM provider, a TTS provider, or a telephony service. It observes these systems, presents their activity as one coherent trace, and analyzes that trace without entering the customer’s critical execution path.

The integration promise is:

> Install the Python SDK, set `VOKER_API_KEY`, attach Voker to the agent session, and make a call. The trace should appear without restructuring the application.

## 2. Product principles

### Intelligence is the USP; observability makes it trustworthy

Tracing alone is not the differentiator. The product must transform runtime evidence into useful intelligence:

- Explain why an individual conversation likely failed or succeeded.
- Connect every conclusion to exact supporting evidence.
- Identify recurring failure patterns across sessions, agents, versions, providers, and intents.
- Distinguish technical failure, agent behavior, voice friction, and uncertain causes.
- Help a developer decide what to investigate or improve next.

Observability remains non-negotiable because intelligence without reliable evidence becomes an unsupported score or summary. Product planning should therefore treat trace capture as foundational infrastructure and the intelligence experience as the customer-facing value.

### Minimal integration effort

- One required credential: `VOKER_API_KEY`.
- One attachment call for supported Python frameworks.
- Dashboard-managed connections for hosted platforms.
- A small generic event API for unsupported frameworks.
- Existing application behavior must not depend on Voker being available.

### One canonical trace

SDK events, provider webhooks, imported calls, agent graphs, and custom events must normalize into the same internal model. The dashboard should not need provider-specific rendering logic for the normal trace experience.

### Multi-agent by design

An agent is not assumed to be the entire conversation. A session may contain multiple agent runs, routing decisions, subgraphs, and handoffs. Agent identity and parent-child relationships are first-class fields.

### Evidence before conclusions

Voker may identify correlations and likely contributing factors, but it must not present correlation as causation. Product copy should use language such as “associated with,” “strongest observed signal,” and “pattern found in similar sessions.”

### Fail open

Telemetry failure must not break, block, or materially slow the customer’s voice agent. Export runs asynchronously, uses bounded queues and timeouts, and degrades safely.

## 3. Users and primary workflows

### Voice-agent developer

- Add observability to an existing agent.
- Inspect a failed call and its exact error path.
- Compare latency across STT, LLM, tools, and TTS.
- Verify tool arguments and results.
- Debug an agent handoff or LangGraph route.

### AI/product engineer

- Measure resolution, correction, escalation, and abandonment.
- Find voice issues associated with unsuccessful outcomes.
- Compare agents, versions, providers, models, and deployments.
- Open representative sessions as evidence.

### Engineering lead/operator

- Track error rate, latency percentiles, token usage, and cost.
- Identify regressions after an agent release.
- Confirm that integrations are healthy and data is arriving.

## 4. Confirmed MVP scope

### Supported voice platforms and frameworks

| Platform or stack | MVP integration | Support level |
| --- | --- | --- |
| LiveKit Agents | Native Python SDK adapter | Production-ready target |
| Vapi | Dashboard connection and automatic webhook ingestion | Production-ready target |
| Retell AI | Dashboard connection and automatic webhook ingestion | Production-ready target |
| Custom Python stack | Generic session, span, and event API | Production-ready target |
| LangGraph | Python callback/wrapper for graphs, nodes, tools, and handoffs | Production-ready target |

Pipecat is deliberately excluded from the MVP. It will be considered after the canonical model and first integrations are stable.

### Provider coverage

The MVP must understand activity from these pipeline categories:

- STT providers such as Deepgram and OpenAI.
- OpenAI-compatible LLM APIs, including OpenAI and OpenRouter.
- LLM providers exposed through LiveKit or custom instrumentation.
- TTS providers such as ElevenLabs, Cartesia, Deepgram, and OpenAI.
- Local function tools and remotely executed MCP tools.
- Telephony/transport metadata supplied by LiveKit, Vapi, or Retell.

Provider-specific native adapters are not required for every provider in the MVP. LiveKit and the generic SDK can capture the common lifecycle. Rich provider adapters can later add request IDs, provider routing, exact pricing, and provider-specific failure data.

### MVP capabilities

- Organizations, projects, and environments.
- Project-scoped ingest API keys.
- Agent registration and agent versions.
- Sessions/conversations with stable external IDs.
- Turns, transcripts, spans, events, errors, and usage records.
- STT, LLM, tool/MCP, TTS, playback, and custom spans.
- Multi-agent runs and explicit handoffs.
- Latency waterfall and full chronological timeline.
- Error details and failed-span navigation.
- Token and cost summaries when usage/pricing is available.
- Interruptions, corrections, dead air, talk-over, and outcome metadata when observable.
- Optional recording metadata and playback.
- Vapi and Retell setup screens and webhook health.
- Live ingestion status during onboarding.
- Basic aggregate dashboard and Voice Impact cohort comparisons.

### Explicitly outside the MVP

- TypeScript SDK.
- Pipecat adapter.
- Native adapters for every STT, LLM, and TTS vendor.
- Running telephony, SIP, STT, LLM, or TTS workloads for customers.
- S3-based storage infrastructure.
- Redis as a required system dependency.
- Full OpenTelemetry ingestion/export compatibility.
- Prompt management, datasets, and automated regression suites.
- Advanced evaluation-builder and no-code scoring product.
- Enterprise SSO and complex enterprise access controls.
- Claims that observed technical factors caused a business outcome.

## 5. Integration experience

The following examples describe the intended SDK surface. They are the contract the implementation should work toward; they do not imply that the package already exists.

### 5.1 Installation and configuration

Generic/custom stack:

```bash
pip install voker-voice
```

LiveKit extra:

```bash
pip install "voker-voice[livekit]"
```

Environment:

```env
VOKER_API_KEY=vkr_live_xxxxxxxxx
```

The API key identifies the project and environment. The SDK resolves or creates agents by stable slug/name, so separate workspace and remote-agent IDs are not required for normal setup.

#### Platform development environment

The repository root `.env` contains development credentials for building and testing the Voker Voice platform. Developers and implementation agents are authorized to load and use those credentials for local development and approved live integration tests. They must not print, return, copy, commit, or otherwise expose secret values. The file is ignored by Git and its values must never be sent to the frontend.

The application and test runner may load these variables directly from the repository-root `.env`. Documentation, fixtures, snapshots, error messages, and test output must use variable names or redacted placeholders only:

```env
# PostgreSQL; local development can use the Docker Compose default
DATABASE_URL=postgresql+psycopg://voker:voker_dev@localhost:5432/voker_voice

# Structured post-call intelligence
SEMANTIC_EVALUATOR_PROVIDER=openrouter
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-flash

# LiveKit development project
LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=

# Hosted voice-platform connectors
VAPI_PRIVATE_API_KEY=
RETELL_API_KEY=

# Real voice-pipeline providers used by LiveKit E2E tests
DEEPGRAM_API_KEY=
ELEVENLABS_API_KEY=

# Optional alternative providers
OPENAI_API_KEY=
CARTESIA_API_KEY=

# Authenticated/private recording assets
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=

# Public callback origin used for provider webhook tests
PUBLIC_BASE_URL=

# Generated locally; never shared or hardcoded
APP_SECRET_KEY=
JWT_SECRET_KEY=
CREDENTIAL_ENCRYPTION_KEY=
```

Credential requirements by workflow:

| Workflow | Required configuration |
| --- | --- |
| Unit, schema, and fixture tests | No external provider credentials |
| API/database development | `DATABASE_URL` |
| Semantic intelligence E2E | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` |
| LiveKit adapter E2E | LiveKit credentials plus configured STT/TTS credentials |
| Vapi connector E2E | `VAPI_PRIVATE_API_KEY`, `PUBLIC_BASE_URL` |
| Retell connector E2E | `RETELL_API_KEY`, `PUBLIC_BASE_URL` |
| Private recording E2E | Cloudinary credentials |

`DEEPGRAM_API_KEY` plus `ELEVENLABS_API_KEY` is the default development STT/TTS combination. OpenAI or Cartesia may be used as alternatives when the corresponding adapter/test is enabled.

`VOKER_API_KEY` in the existing demo environment belongs to the older Voker test-agent integration. It is not a server credential for the new Voker Voice platform and must not be used to authenticate platform internals. Customer-facing Voker Voice ingest keys are created by the platform and supplied to customer applications as `VOKER_API_KEY`.

Application secrets may be generated locally. A hosted PostgreSQL deployment supplies its own secure `DATABASE_URL`; local development does not require a third-party database API key.

### 5.2 LiveKit integration

Target integration:

```python
from livekit.agents import AgentSession
from voker_voice.livekit import observe

session = AgentSession(
    stt=stt,
    llm=llm,
    tts=tts,
)

observe(
    session,
    context=ctx,
    agent="support-agent",
    version="2026-09-20.1",  # optional
)

await session.start(
    room=ctx.room,
    agent=SupportAgent(),
)
```

The adapter should automatically capture session lifecycle, participant metadata, speech boundaries, STT results, LLM activity, tools, TTS, playback, interruptions, errors, and completion where LiveKit exposes them. Missing provider data must remain `null`/unknown rather than being fabricated.

### 5.3 Generic Python integration

Unsupported or custom pipelines use explicit spans:

```python
from voker_voice import VokerVoice

voker = VokerVoice()

async with voker.session(
    agent="appointment-agent",
    session_id=call_id,
    metadata={"tenant_id": tenant_id},
) as call:
    async with call.span("stt", provider="deepgram") as span:
        transcript = await transcribe(audio)
        span.set_output({"text": transcript})

    async with call.span(
        "llm",
        provider="openrouter",
        model="provider/model-name",
    ) as span:
        response = await generate_response(transcript)
        span.set_usage(input_tokens=420, output_tokens=96)

    async with call.span("tool", name="lookup_appointment") as span:
        appointment = await lookup_appointment(customer_id)
        span.set_output(appointment)

    async with call.span("tts", provider="elevenlabs"):
        response_audio = await synthesize(response)
```

Context managers automatically set timing and status and record exceptions before re-raising them. Customers may redact or omit inputs and outputs.

### 5.4 LangGraph and multi-agent integration

Target wrapper:

```python
from voker_voice.langgraph import observe

observed_graph = observe(
    graph,
    agent="customer-service",
)

result = await observed_graph.ainvoke(
    {"messages": messages},
    config={"configurable": {"thread_id": call_id}},
)
```

The adapter records graph invocation, nodes, routing decisions, retries, tools, errors, interrupts/resumes, and graph completion. It propagates the active Voker session so graph work appears inside the voice call rather than as an unrelated trace.

Applications can mark semantic agents and handoffs explicitly:

```python
async with call.agent("triage-agent"):
    route = await triage(request)

call.handoff(
    from_agent="triage-agent",
    to_agent="billing-agent",
    reason="billing_question",
)

async with call.agent("billing-agent"):
    answer = await handle_billing(request)
```

### 5.5 Tool and MCP observability

Both local tools and MCP tools normalize to `tool` spans. MCP-specific fields extend the common record:

```python
async with call.tool(
    name="search_orders",
    protocol="mcp",
    server="crm-mcp",
    arguments={"customer_id": "cus_123"},
) as tool_span:
    result = await mcp_session.call_tool(
        "search_orders",
        {"customer_id": "cus_123"},
    )
    tool_span.set_output(result)
```

The trace must show tool name, server, arguments subject to redaction, result, duration, retry count, status, and error. An MCP result containing `isError: true` is a failed tool span even if the transport call itself completed successfully.

### 5.6 Vapi and Retell workflow

Hosted platforms use a no-code dashboard flow:

1. User creates or selects a Voker project.
2. User selects Vapi or Retell.
3. User supplies the provider API key using a secure backend form.
4. Voker lists the provider’s assistants/agents.
5. User selects the agents to observe.
6. Voker creates/configures the required webhook.
7. Voker verifies receipt of a test or real call.
8. The completed call is normalized into the canonical trace.

If a provider supports only one webhook URL, Voker must preserve the customer’s existing automation by recording and forwarding to the prior URL. Forwarding must have delivery logs, retries, signatures where possible, and a visible health state.

### 5.7 Setup verification

The onboarding page should update as real data arrives:

```text
✓ API key authenticated
✓ Agent registered
✓ Voice session detected
✓ STT event received
✓ LLM event received
✓ Tool event received
✓ TTS event received
✓ Session completed
```

Not every call contains every stage. The verifier must distinguish “not yet observed” from “integration broken.” A raw trace should become visible immediately; aggregate analytics may process afterward.

## 6. Canonical observability model

### 6.1 Trace hierarchy

```text
project
└── session (root trace / one conversation)
    ├── participant and transport events
    ├── turn
    │   ├── STT span
    │   ├── agent run
    │   │   ├── LLM span
    │   │   ├── tool or MCP span
    │   │   └── handoff event / child agent run
    │   ├── TTS span
    │   └── playback events
    ├── turn
    └── session outcome
```

A `session` is the trace root. A `span` is a timed operation and can contain child spans. An `event` is an instantaneous observation. A `turn` groups related user and agent activity but does not replace parent-child span relationships.

### 6.2 Canonical event envelope

All SDK and provider events normalize to this logical envelope:

```json
{
  "schema_version": "1.0",
  "event_id": "evt_01...",
  "event_type": "llm.completed",
  "occurred_at": "2026-09-20T10:15:30.123Z",
  "received_at": "2026-09-20T10:15:30.420Z",
  "sequence": 18,
  "project_id": "prj_01...",
  "environment": "production",
  "session_id": "ses_01...",
  "external_session_id": "call_abc123",
  "trace_id": "trc_01...",
  "span_id": "spn_01...",
  "parent_span_id": "spn_parent...",
  "turn_id": "turn_01...",
  "agent": {
    "id": "agt_01...",
    "name": "billing-agent",
    "version": "2026-09-20.1"
  },
  "source": {
    "integration": "livekit",
    "provider": "openrouter",
    "sdk": "voker-voice-python",
    "sdk_version": "0.1.0"
  },
  "status": "ok",
  "duration_ms": 842.6,
  "attributes": {},
  "input": {},
  "output": {},
  "usage": {},
  "error": null
}
```

Requirements:

- `event_id` is globally unique and is the idempotency key.
- `occurred_at` is producer time; `received_at` is server time.
- `sequence` is monotonic within one SDK process/session when available.
- IDs supplied by customers are stored as external IDs, not trusted as internal primary keys.
- Unknown fields are preserved in provider/raw payload storage but do not change canonical behavior.
- Schema changes are versioned and backward compatible within a major version.

### 6.3 Event types

Minimum canonical vocabulary:

| Category | Events/spans |
| --- | --- |
| Session | `session.started`, `session.updated`, `session.ended`, `session.error` |
| Participant/audio | `speech.started`, `speech.stopped`, `audio.received`, `audio.sent` |
| Turn | `turn.started`, `turn.completed`, `turn.abandoned` |
| STT | `stt.started`, `stt.interim`, `stt.final`, `stt.completed`, `stt.error` |
| Agent | `agent.started`, `agent.completed`, `agent.error`, `agent.handoff` |
| Graph | `graph.started`, `graph.node.started`, `graph.node.completed`, `graph.retry`, `graph.interrupted`, `graph.resumed`, `graph.error`, `graph.completed` |
| LLM | `llm.started`, `llm.first_token`, `llm.completed`, `llm.error` |
| Tool/MCP | `tool.started`, `tool.completed`, `tool.error` |
| TTS | `tts.started`, `tts.first_audio`, `tts.completed`, `tts.error` |
| Playback | `playback.started`, `playback.interrupted`, `playback.completed` |
| Outcome | `outcome.recorded`, `correction.detected`, `escalation.detected`, `abandonment.detected` |
| Extension | `custom` with a namespaced custom name |

### 6.4 Span status and errors

Span status is one of:

- `unset`: operation has not finished or no outcome was supplied.
- `ok`: operation completed successfully.
- `error`: operation failed or returned a protocol-level error.
- `cancelled`: operation was cancelled, including interruption-induced cancellation.
- `timeout`: operation exceeded its deadline.

Canonical error fields:

```json
{
  "type": "RateLimitError",
  "code": "rate_limit_exceeded",
  "message": "Provider rejected the request",
  "retryable": true,
  "retry_count": 1,
  "provider_request_id": "req_...",
  "stacktrace": null
}
```

Stack traces and raw provider bodies are sensitive and should be configurable. Secrets must always be removed.

## 7. Metrics and calculations

### Latency

Store raw timestamps and durations; derive summaries server-side.

| Metric | Definition |
| --- | --- |
| STT first interim | First audio/speech input to first interim transcript |
| STT finalization | End of user speech to final transcript |
| LLM TTFT | LLM request start to first output token/chunk |
| LLM total | LLM request start to final response |
| Tool latency | Tool invocation start to result/error |
| TTS first audio | TTS request start to first audio chunk |
| TTS total | TTS request start to synthesis completion |
| Response gap | End of user speech to first agent audio playback |
| Turn latency | Turn start to turn completion |

Percentiles should be calculated for comparable cohorts by project, environment, agent, version, provider, model, and time range. Missing stage timestamps must not be treated as zero.

### Usage and cost

Usage records may include:

- Input, output, cached, reasoning, and total LLM tokens.
- STT audio seconds/minutes.
- TTS characters or generated audio seconds.
- Tool-specific billable units.
- Provider-reported cost.
- Voker-calculated estimated cost.

Money must use a decimal or integer micro-unit representation, never binary floating point. Each cost stores currency, calculation source, rate-card version, and whether it is exact or estimated.

OpenRouter is OpenAI-compatible, but provider/model routing details should be retained when the response exposes them. Free models may correctly produce a zero cost while still recording token usage and latency.

### Voice behavior and outcomes

- Interruption: user speech begins while agent audio is playing, or the platform reports a barge-in.
- Talk-over: user and agent speech overlap for a configured minimum duration.
- Dead air: an unexplained silence interval above a configured threshold.
- Correction: user corrects a prior transcription or agent action; may be explicitly reported or derived later.
- Handoff: control moves between semantic agents.
- Resolution/escalation/abandonment: explicit application outcome where possible; inferred outcomes must be labeled as inferred.

## 8. Post-call conversation intelligence

Voker Voice supports a two-layer analysis pipeline. Trace collection and technical observability never depend on an LLM.

```text
1. Voice conversation starts
        ↓
2. Agent, LLM, and tools/MCP execute
        ↓
3. Voker captures canonical events
        ↓
4. Trace appears live
        ↓
5. Deterministic failures are highlighted
        ↓
6. Session completes
        ↓
7. Asynchronous semantic analysis runs
        ↓
8. Dashboard explains why the conversation reached its outcome
        ↓
9. Every finding links to exact transcript turns/events/spans
```

LiveKit and custom Python SDK integrations can stream this trace during the conversation. Vapi and Retell are live only to the extent that their provider webhooks deliver in-call events; otherwise their normalized trace appears as provider data arrives or immediately after call completion.

### 8.1 Deterministic findings

Rules operate on canonical spans/events and produce confirmed technical findings such as:

- Provider exception, protocol error, timeout, or cancellation.
- Failed or retried local/MCP tool call.
- Missing expected stage or incomplete session.
- Slow STT finalization, LLM TTFT, tool call, TTS first audio, or response gap.
- Interruption, talk-over, excessive dead air, or abandoned turn.
- Invalid handoff destination or failed agent run.
- Usage/cost limit exceeded when a configured limit exists.

Each finding records rule ID/version, severity, observed value, threshold, and exact supporting event/span/turn IDs. Deterministic findings can appear while the session is live when enough evidence is already present.

### 8.2 Asynchronous semantic analysis

After the session completes, a PostgreSQL-backed job runs a controlled structured-output LLM evaluator. It may determine:

- User intent and explicit/inferred outcome.
- Whether the request was resolved.
- User corrections, confusion, and frustration visible in the transcript.
- Agent misunderstanding or unsupported response.
- Whether the agent ignored, contradicted, or misused a tool result.
- Whether routing or a handoff was inappropriate.
- Failure category and an evidence-based explanation.

The MVP uses a bounded evaluator, not an autonomous analysis agent. It has a fixed versioned prompt, strict Pydantic result schema, low-variance settings, limited input context, validation/retry limits, and independently tracked latency/token/cost data. The analysis provider/model is configurable: `SEMANTIC_EVALUATOR_PROVIDER=openrouter` uses the existing OpenRouter credentials and model, while `deepseek` uses the separate direct `DEEPSEEK_API_KEY` and `DEEPSEEK_MODEL`. The selected path is explicit; the service never silently falls back between paid providers.

Example result:

```json
{
  "status": "completed",
  "outcome": "failed",
  "outcome_source": "inferred",
  "intent": "reschedule_appointment",
  "failure_category": "incorrect_entity",
  "summary": "The agent changed the appointment to Thursday after the caller requested Tuesday.",
  "confidence": 0.91,
  "findings": [
    {
      "type": "agent_misunderstanding",
      "statement": "The appointment tool received a different day than the caller requested.",
      "confidence": 0.94,
      "evidence": [
        {"turn_id": "turn_04", "event_id": "evt_stt_18"},
        {"span_id": "spn_tool_22"},
        {"turn_id": "turn_06"}
      ]
    }
  ],
  "analyzer": {
    "prompt_version": "failure-analysis-v1",
    "model": "configured/model",
    "analysis_version": 1
  }
}
```

Every semantic finding must cite one or more existing event, span, or turn IDs. The server rejects unsupported evidence IDs. A summary without valid evidence is not displayed as an authoritative finding.

### 8.3 Finding certainty

The dashboard distinguishes:

- **Confirmed fact:** directly present in an event, error, transcript, or tool record.
- **Detected condition:** produced by a versioned deterministic rule.
- **Inferred finding:** produced by semantic analysis and accompanied by confidence/evidence.
- **Unknown:** available evidence is insufficient.

The analyzer identifies likely contributing factors; it does not claim that a correlated signal caused the outcome.

### 8.4 Failure and re-analysis behavior

- Analysis runs outside ingestion and outside the customer’s voice-agent process.
- An analyzer outage never affects trace collection or the customer agent.
- While queued/running, the UI shows analysis status without hiding the trace.
- Invalid, timed-out, or failed analysis is visible and retryable within configured limits.
- Technical trace, deterministic findings, transcript, errors, latency, tools, usage, and costs remain available if semantic analysis fails.
- Analysis stores model, prompt, schema, and analysis versions.
- Authorized users can request re-analysis after a prompt/model change; prior versions remain auditable rather than being silently overwritten.

## 9. Dashboard

The application follows the supplied `voker-voice-design` visual system: React implementation should use its tokens, assets, copy guidance, and component specifications rather than inventing a second visual language.

### Required screens

#### Setup and integrations

- Create/select project and environment.
- Create and revoke ingest keys.
- Choose LiveKit, Vapi, Retell, LangGraph/custom Python.
- Show exact generated install/configuration snippet.
- Display integration verification checklist and last event time.
- Display webhook forwarding and delivery health for hosted platforms.

#### Overview

- Lead with actionable intelligence and recurring agent-performance findings, not raw infrastructure charts.
- Summarize why conversations fail, succeed, escalate, or are abandoned.
- Link every aggregate finding to its cohort and representative evidence sessions.
- Total sessions and call volume trend.
- Resolution, correction, escalation, and abandonment rates.
- Error rate.
- p50/p90 response and stage latency.
- Token and cost totals.
- Top agents, versions, providers, models, and issues.
- Basic Voice Impact comparisons linking technical signals to outcomes.

#### Sessions

- Filter by project, environment, agent, version, platform, status, outcome, error, time range, and latency.
- Search by internal/external session ID and metadata fields allowed for search.
- Show live/in-progress and completed sessions distinctly.

#### Session detail

- Audio player when a recording exists.
- Speaker-separated transcript.
- Unified chronological event timeline.
- Nested waterfall for STT, LLM, tools/MCP, handoffs, TTS, and playback.
- Agent and graph-node identity.
- Tool arguments/results with redaction indicators.
- Error panel and jump-to-failed-span action.
- Latency, usage, and cost summary.
- Interruptions, dead air, talk-over, corrections, and outcome.
- A dynamic session-analysis panel explaining why the conversation succeeded, failed, escalated, was abandoned, or remains uncertain.
- Confirmed facts, detected conditions, and inferred findings shown distinctly.
- Confidence and direct links from every semantic finding to transcript turns, events, and spans.
- Analyzer version and re-analysis state for authorized users.
- Raw normalized event view for developers.

The analysis panel is the primary session-level product experience. The trace, transcript, and waterfall provide the evidence and debugging path behind it.

#### Agent detail

- Agent/version comparison.
- Session volume, success, latency, errors, cost, and common tool failures.
- Multi-agent handoff sources/destinations and handoff outcomes.

### Voice Impact language

The dashboard may say:

> Calls with more than three interruptions resolved 44 percentage points less often in this cohort.

It must not say:

> Interruptions caused a 44 percentage-point resolution loss.

## 10. API surface

Exact URL naming may be refined before implementation, but the MVP needs these capabilities:

### Ingestion

```text
POST /v1/sessions
PATCH /v1/sessions/{session_id}
POST /v1/events/batch
POST /v1/sessions/{session_id}/end
POST /v1/recordings
```

`POST /v1/events/batch` is the primary SDK endpoint. It accepts ordered batches, supports gzip, returns accepted/duplicate/rejected counts, and is idempotent by event ID.

### Application API

```text
GET/POST /api/projects
GET/POST/DELETE /api/projects/{project_id}/api-keys
GET /api/agents
GET /api/agents/{agent_id}
GET /api/sessions
GET /api/sessions/{session_id}
GET /api/sessions/{session_id}/events
GET /api/sessions/{session_id}/trace
GET /api/sessions/{session_id}/analysis
POST /api/sessions/{session_id}/analysis/retry
GET /api/analytics/overview
GET /api/analytics/latency
GET /api/analytics/costs
GET/POST/DELETE /api/integrations
```

### Provider webhooks

```text
POST /webhooks/vapi/{integration_id}
POST /webhooks/retell/{integration_id}
```

Webhook handlers verify signatures where the provider supports them, store receipt before processing, acknowledge quickly, and normalize asynchronously. Duplicate deliveries must be safe.

### Live updates

Server-Sent Events are sufficient for setup verification and live session updates in the MVP. WebSockets are not required unless a later interaction demands bidirectional communication.

## 11. Technical architecture

### Chosen stack

| Layer | Choice |
| --- | --- |
| Dashboard | React + Vite + TypeScript |
| UI | Existing Voker Voice design tokens/assets, Tailwind CSS, accessible primitives, Lucide icons |
| Charts/timeline | Recharts for aggregate charts; custom DOM/SVG timeline where required |
| Backend | Python + FastAPI |
| Validation | Pydantic |
| Database | PostgreSQL |
| ORM/migrations | SQLAlchemy 2 + Alembic |
| PostgreSQL driver | psycopg 3 |
| Python SDK | `voker-voice` package with optional extras |
| Recording/assets | Cloudinary authenticated/private assets |
| Background work | PostgreSQL-backed jobs with `FOR UPDATE SKIP LOCKED`; `LISTEN/NOTIFY` for wake-ups |
| Live UI updates | Server-Sent Events |

Next.js is not required because this is an authenticated application dashboard with no current SSR/SEO requirement. React + Vite gives a simpler independently deployed frontend and keeps the FastAPI service as the clear API boundary.

Redis is not required in the MVP. PostgreSQL can safely provide the initial job queue, durable state, idempotency, and notifications. Redis may be introduced when measured throughput, fan-out, caching, or rate-limiting requirements justify another operational dependency.

### Component flow

```text
Python SDK / LiveKit adapter ─┐
                             ├─> Ingestion API ─> canonicalize ─> PostgreSQL
Vapi / Retell webhooks ──────┘          │                │             │
                                        │                └─> jobs ─────┤
                                        │                       │      │
                                        │             deterministic    │
                                        │                 rules        │
                                        │                       │      │
                                        │              async semantic  │
                                        │                 analyzer ────┤
                                        │                              │
                                        └─> setup/live SSE              ├─> FastAPI query API
                                                                       │
Provider/external recording ─> optional Cloudinary reference ──────────┘
                                                                       │
                                                               React/Vite dashboard
```

The ingest request should persist accepted data before triggering derived analytics. Heavy normalization, aggregation, cost enrichment, and outcome analysis run as durable jobs.

### Suggested repository layout

```text
apps/
  api/                    # FastAPI application
  web/                    # React/Vite dashboard
packages/
  python-sdk/             # voker-voice
    src/voker_voice/
      integrations/
        livekit.py
        langgraph.py
      client.py
      context.py
      exporter.py
      models.py
      redaction.py
  event-schema/           # JSON Schema/examples shared by API and SDK tests
docs/
  voker-voice.md
  milestones.md
```

The current demo application may remain during migration, but production code should move into explicit application/package boundaries rather than growing inside the demo module.

## 12. Persistence model

Core relational entities:

- `organizations` and `organization_members`
- `projects` and `environments`
- `api_keys` with hashed secrets and visible prefixes
- `agents` and `agent_versions`
- `sessions`
- `turns`
- `agent_runs`
- `spans`
- `events`
- `errors`
- `analysis_runs`, `findings`, and `finding_evidence`
- `usage_records` and `cost_records`
- `recordings`
- `integrations`
- `webhook_receipts` and `webhook_deliveries`
- `jobs`

Every functional row is project-scoped. API queries must enforce the project boundary rather than relying on IDs being difficult to guess.

Frequently filtered canonical values belong in typed/indexed columns; provider-specific and evolving attributes belong in JSONB. Raw webhook payloads may be retained for debugging according to a configurable retention policy.

Important indexes include:

- Sessions by project/environment/start time.
- Sessions by agent/version/start time.
- Sessions by status/outcome/error.
- Events by session and occurrence time/sequence.
- Spans by trace/parent/start time.
- Event ID and provider delivery ID uniqueness for idempotency.
- Jobs by state and scheduled time.

PostgreSQL table partitioning is not required on day one. Add time-based partitions only after event volume and retention behavior are measured.

Analysis runs are immutable/versioned records. `finding_evidence` references canonical sessions, turns, spans, or events and must be validated as belonging to the same project/session.

## 13. SDK and ingestion reliability

The Python SDK must:

- Use an in-memory bounded queue.
- Batch events and export on a background task/thread appropriate to sync or async use.
- Apply short connect/request timeouts.
- Retry transient failures with exponential backoff and jitter.
- Never retry invalid/authentication payloads indefinitely.
- Flush at session end and expose `flush()`/`aclose()` for controlled shutdown.
- Preserve event order where possible and include sequence numbers.
- Generate event IDs before export so retries remain idempotent.
- Avoid retaining unbounded audio, transcripts, tool results, or model payloads.
- Emit opt-in diagnostic logging without logging secrets.
- Support `enabled=False` and environment-based disabling.

The server must:

- Validate key scope and schema version.
- Cap request and individual payload size.
- Accept partial batches and report per-item failures.
- Deduplicate event IDs.
- Tolerate out-of-order events.
- Close abandoned/incomplete sessions via a visible timeout state, not a fabricated success.
- Keep raw receipt time separate from producer time for clock-skew diagnosis.

## 14. Privacy and security

- Store API key secrets only as hashes; show the secret once at creation.
- Encrypt provider credentials at rest using an application encryption key or managed secret facility.
- Never accept provider credentials in frontend logs or analytics.
- Verify webhook signatures and record verification status.
- Use Cloudinary authenticated/private delivery for recordings; never public-by-default URLs.
- Allow transcript, audio, input/output, and tool-argument capture to be independently disabled.
- Provide SDK redaction hooks that run before data leaves the customer process.
- Apply default redaction for authorization headers, API keys, cookies, and known secret fields.
- Record whether content was omitted, truncated, or redacted.
- Establish configurable retention for raw events, transcripts, recordings, and webhook payloads.
- Allow projects to disable semantic analysis or exclude selected content from evaluator input.
- Treat evaluator prompts and responses as sensitive session data governed by the same retention and access rules.
- Keep audit records for API-key and integration changes.

Authentication implementation for dashboard users is an engineering decision to finalize before the account milestone; it must support organization membership and project roles without changing project-scoped data ownership.

## 15. Testing and quality bar

### Contract tests

- Event schema validation and backward compatibility.
- SDK-generated payloads accepted by the ingest API.
- Idempotent replay of SDK batches and provider webhooks.
- Canonical traces generated from saved provider fixtures.

### SDK tests

- Sync and async contexts.
- Successful, failed, timed-out, and cancelled spans.
- Context propagation across tasks.
- Queue overflow and network outage behavior.
- Redaction and truncation.
- No application exception is swallowed or replaced.

### Integration tests

- Realistic LiveKit session fixture.
- LangGraph multi-node, retry, tool, error, and handoff workflow.
- Vapi and Retell webhook fixtures including duplicates and ordering differences.
- Webhook forwarding success, timeout, retry, and permanent failure.

### Analysis tests

- Deterministic rule results include the correct thresholds and evidence IDs.
- Structured semantic output is validated and rejects fabricated/cross-session evidence.
- Confirmed, detected, inferred, and unknown states render differently.
- Analyzer timeout, invalid JSON/schema, provider error, retry exhaustion, and disabled state.
- Re-analysis creates an auditable version and does not overwrite prior results.
- Analyzer failure leaves the trace and deterministic findings available.

### UI tests

- Trace order and nesting.
- Error-to-span navigation.
- Partial/in-progress sessions.
- Redacted and missing content.
- Audio unavailable and audio playback states.
- Project isolation and permissions.

### Performance checks

- SDK attachment adds no network hop to the provider call path.
- SDK export cannot grow memory without a fixed bound.
- Ingestion remains responsive under batched concurrent sessions.
- Timeline queries are bounded/paginated for large traces.

## 16. MVP completion criteria

The MVP is complete when a developer can:

1. Create a project and Python ingest key.
2. Add Voker to an existing LiveKit or custom Python agent in minutes.
3. Run a multi-turn session containing an LLM call, a tool/MCP call, and TTS activity.
4. See the session arrive without waiting for aggregate processing.
5. Inspect a correctly nested timeline with agent identities and handoffs.
6. Identify stage latency, errors, token usage, and cost where available.
7. Connect a Vapi or Retell agent without modifying application code.
8. Confirm webhook delivery/forwarding health.
9. Compare basic agent/session performance and open evidence sessions.
10. Continue running the voice agent normally during a simulated Voker outage.
11. Open “Why did this conversation fail?” after completion and inspect a structured analysis whose findings link to exact transcript turns/events/spans.
12. Retain the full technical trace and deterministic findings when semantic analysis is disabled or unavailable.

## 17. Future roadmap

After the MVP is stable, evaluate in this order:

1. OpenAI Realtime native integration.
2. Deepgram Voice Agent native integration.
3. ElevenLabs Conversational AI integration.
4. Pipecat adapter.
5. Twilio Media Streams and broader telephony metadata.
6. TypeScript SDK based on the stable versioned event protocol.
7. OpenTelemetry import/export compatibility.
8. Alerts, SLOs, regression detection, and deployment comparison.
9. Advanced evaluations, quality scorecards, and datasets.
10. Voker MCP server for querying traces and analytics from developer tools.
11. Additional storage/queue infrastructure only when measured scale requires it.

Future integrations must map to the canonical model rather than adding provider-specific concepts directly to the dashboard.

## 18. Related repository material

- `voker-voice-impact-project-overview.md` contains the earlier Voice Impact concept and correlation examples.
- `voker-voice-design/` is the required visual/design handoff for dashboard implementation.
- `example/` contains the imperfect LangGraph/OpenRouter/Voker test agent and can provide failure fixtures during early development.
- `reference/` contains open-source implementation references. Reference code should be reviewed for ideas and license compatibility; it is not the Voker architecture source of truth.
