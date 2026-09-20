# Voker Voice — Implementation Milestones

This plan turns the scope in [`voker-voice.md`](./voker-voice.md) into an executable build sequence. Milestones are ordered by dependency, not by calendar date. Voker Voice’s USP is the intelligence layer; the observability milestones exist to make that intelligence accurate, explainable, and evidence-backed. Do not begin another platform adapter until the shared canonical path is working end to end.

## Delivery rules

- `docs/voker-voice.md` is the product and architecture source of truth.
- Product decisions prioritize actionable voice-agent intelligence over adding tracing breadth for its own sake.
- No analysis finding is complete until it links back to canonical trace evidence.
- Python is the only SDK language in the MVP.
- Pipecat is not part of the MVP.
- Provider payloads are translated at the ingestion boundary; they do not become the database or UI model.
- Every milestone ends with tested, reviewable software rather than disconnected scaffolding.
- New scope must be placed in the future roadmap unless it is required to satisfy an existing MVP completion criterion.
- Preserve the current demo until equivalent failure scenarios are available in the new development environment.

## Implementation status — 2026-09-20

This is a live delivery record, not a projected status report. A checked item has been
implemented, verified locally, and committed to `main`; an unchecked item remains work.

| Milestone | Status | Verified implementation |
| --- | --- | --- |
| 0 — Foundation | Complete | pnpm/Vite workspace, FastAPI, CI, Python package structure and checks. |
| 1 — Schema | Complete | PostgreSQL schema, Alembic migrations, canonical JSON/Pydantic contract. |
| 2 — Ingestion | Complete vertical slice | API-key auth, gzip batches, idempotency, out-of-order span repair, durable PostgreSQL jobs and SSE broker. |
| 3 — Python SDK | Complete vertical slice | Fail-open queued exporter, redaction, nested spans, tools/MCP and handoffs. |
| 4 — Trace dashboard | Complete | Live trace refresh, transcript projection, normalized-event inspector, bounded session queries, filters, and pagination are implemented. |
| 5 — LiveKit | In progress | Public AgentSession observer maps lifecycle, transcript, interruption, talk-over, metrics, and playback events with regression coverage; hosted voice E2E remains. |
| 6 — LangGraph | Complete vertical slice | Public callback tracing covers nodes, handoffs, retries, interrupts, resumes, and parallel child spans; the dashboard filters graph/agent and handoff activity. |
| 7 — Intelligence | Complete vertical slice | Deterministic evidence-linked worker covers errors, cancellation/timeouts, slow stages, interruptions, and talk-over; the evaluator records immutable completed/disabled runs, the dashboard exposes analysis history plus controlled re-analysis, and rollback-only live OpenRouter E2E is verified. |
| 8 — Vapi | In progress — hosted E2E skipped | Payload normalizer, canonical error mapping, authenticated durable webhook intake, and the configured Vapi assistant webhook connection are implemented. The real test-call verification was skipped because the assistant could not be connected; provider delivery and canonical trace creation remain unverified. |
| 9 — Retell | In progress — hosted E2E unavailable | Payload normalizer, canonical error mapping, one-time integration token setup, authenticated integration-specific webhook intake, durable receipts, duplicate protection, and deferred normalization are implemented. Retell credentials authenticate, but the account currently has no agents for provider E2E. |
| 10 — Analytics/costs | Complete vertical slice | Versioned rate-card estimates materialize cost records during ingestion; project outcome/source/cost aggregates, dashboard cost display, minimum-sample interruption/STT cohorts, and stage-specific p50/p95/max latency cards are implemented. Additional cohorts remain future work. |
| 11 — Recordings | Complete vertical slice | Optional provider/private recording metadata can be attached without copying audio, returned with the canonical trace, deleted without affecting that trace, and expired by maintenance command. Cloudinary-backed audio uses a trace-scoped API redirect to a five-minute authenticated URL; the dashboard plays available audio and seeks/highlights transcript turns by trace-relative timestamp. |
| 12 — Private beta hardening | In progress | Readiness reports database/queue state and an operational deployment/incident runbook is included; load, security, backup, and hosted acceptance coverage remain. |

Latest verified commit checkpoints include `64c93c2` (semantic evaluator), `c5fa954`
(finding evidence in trace API), and `ea2df73` (Vapi/Retell normalization).

## GitHub repository and commit workflow

Repository: <https://github.com/umer-2k1/voker-agent-demo>

GitHub authentication may use the existing `GH_TOKEN` environment variable already configured in the terminal. Check only whether it is present; never print its value:

```bash
if [ -n "${GH_TOKEN:-}" ]; then
  echo "GH_TOKEN is configured"
else
  echo "GH_TOKEN is not configured"
fi
```

Use the existing token only when GitHub authentication is required. Never add or copy it into the codebase, documentation, `.env` files, command output, test output, commits, or logs.

Commit and push progress frequently instead of waiting for the entire implementation to finish. Each commit should represent a meaningful milestone or completed, tested piece of work, such as:

- Repository/application foundation.
- Canonical schema and migrations.
- Ingestion API vertical slice.
- Generic Python SDK.
- Trace dashboard.
- LiveKit adapter.
- LangGraph and multi-agent tracing.
- Conversation intelligence and failure analysis.
- Vapi or Retell connector.
- Analytics or recording support.
- Hardening fixes and release readiness.

Before each commit:

1. Review `git status` and the staged diff so unrelated or user-owned changes are not included.
2. Run the relevant formatter, type checker, unit tests, and integration/contract tests for that change.
3. Confirm no secret, generated credential, local `.env`, recording, or sensitive provider payload is staged.
4. Use a concise commit message describing the completed outcome.
5. Push the commit to the current project branch after it passes its applicable checks.

Do not create one large final commit for the entire product. Keep the remote repository continuously updated so its history shows the implementation sequence and preserves working recovery points. Never rewrite or discard existing user history to simplify the commit timeline.

## Milestone 0 — Repository and engineering foundation

### Goal

Create a maintainable application structure and a reproducible local development environment without implementing product features prematurely.

### Work

- Create the target monorepo directories:
  - `apps/api` for FastAPI.
  - `apps/web` for React/Vite.
  - `packages/python-sdk` for `voker-voice`.
  - `packages/event-schema` for versioned schemas and fixtures.
- Add Python project configuration, linting, formatting, type checking, and tests.
- Add frontend TypeScript, linting, formatting, and test configuration.
- Add local PostgreSQL configuration and documented startup commands.
- Add root developer commands for API, web, SDK tests, migrations, and all checks.
- Add CI for backend tests, SDK tests, frontend checks, and schema compatibility.
- Decide and document dashboard authentication implementation while preserving organization/project roles.
- Define environment-variable conventions and safe `.env.example` files.
- Validate configuration by variable presence without printing secret values.
- Load approved local and live-test credentials from the repository-root `.env`; never reproduce their values in source, logs, fixtures, snapshots, documentation, or task output.
- Document which live integration tests are enabled by LiveKit, OpenRouter, Vapi, Retell, voice-provider, and Cloudinary credentials.
- Generate local application/JWT/encryption secrets and use local PostgreSQL credentials for development; never hardcode production secrets.
- Do not modify or delete unrelated current demo/reference files.

### Exit criteria

- A new developer can install dependencies inside the repository virtual environment and start PostgreSQL, API, and web locally.
- One backend health test and one frontend render test pass in CI.
- No secret is committed.
- Missing optional provider credentials cause explicit test skips with reasons, not false passes or import-time failures.
- The intended package boundaries match `docs/voker-voice.md`.

## Milestone 1 — Canonical schema and database foundation

### Goal

Make the event contract and multi-tenant persistence model stable enough for SDK and connector work.

### Work

- Define JSON Schema/Pydantic models for:
  - Canonical event envelope.
  - Span status and error.
  - Agent identity/version.
  - Usage and cost.
  - Session start/update/end.
  - Batch ingestion request/response.
- Create versioned valid and invalid fixtures.
- Implement SQLAlchemy models and Alembic migrations for:
  - Organizations and memberships.
  - Projects and environments.
  - Hashed API keys.
  - Agents and versions.
  - Sessions, turns, agent runs, spans, and events.
  - Errors, usage, costs, and recordings.
  - Integrations, webhook receipts/deliveries, and jobs.
- Add project-scoped indexes and uniqueness constraints for idempotency.
- Define retention fields and redaction/omission markers.
- Seed a local organization, project, environment, and sample agent.

### Exit criteria

- Migrations apply to an empty database and downgrade safely during development.
- Canonical examples validate in both SDK-side and API-side tests.
- A multi-agent trace with nested spans can be stored and retrieved without provider-specific tables.
- Cross-project access tests fail as expected.

## Milestone 2 — Ingestion API and durable processing

### Goal

Accept canonical telemetry reliably before building an SDK adapter.

### Work

- Implement ingest-key authentication and project/environment resolution.
- Implement session create/update/end endpoints.
- Implement `POST /v1/events/batch` with:
  - Gzip support.
  - Request and item size limits.
  - Schema-version validation.
  - Per-item accepted/duplicate/rejected results.
  - Event-ID idempotency.
  - Out-of-order event tolerance.
- Store raw accepted events and upsert derived session/span state transactionally.
- Implement PostgreSQL-backed jobs using `FOR UPDATE SKIP LOCKED`.
- Use `LISTEN/NOTIFY` only to wake workers; PostgreSQL rows remain the durable queue.
- Add retry/dead-letter states and an operator-visible failure reason.
- Implement SSE notifications for setup verification and live sessions.
- Add rate and payload protections appropriate for an ingest endpoint.

### Test scenarios

- Duplicate complete batch.
- Partial duplicate batch.
- Malformed item among valid items.
- Events received out of order.
- Session end received before a delayed child span.
- Same external session ID in two different projects.
- Worker restart while a job is leased.

### Exit criteria

- A script can send a multi-turn canonical trace and retrieve the same ordered/nested trace.
- Replaying the batch produces no duplicate trace records.
- Raw trace data becomes queryable before aggregate jobs finish.
- Worker and SSE processes can restart without losing durable state.

## Milestone 3 — Generic Python SDK

### Goal

Deliver the universal integration path that every later framework adapter builds upon.

### Work

- Create the `voker-voice` package with:
  - `VokerVoice` client.
  - Sync and async session contexts.
  - Span, agent, tool/MCP, handoff, event, usage, and outcome APIs.
  - Context propagation for nested async tasks.
  - Canonical ID and sequence generation.
- Implement a bounded exporter queue, batching, gzip, timeouts, retry/backoff, flush, and shutdown.
- Implement fail-open behavior and opt-in diagnostic logging.
- Implement content size limits and deterministic truncation markers.
- Implement built-in secret redaction and user redaction hooks.
- Support capture controls for transcripts, inputs/outputs, tool data, stack traces, and audio metadata.
- Add `enabled=False` and environment-controlled disabling.
- Publish a local package install workflow from the repository.
- Write a five-minute custom-stack quickstart.

### Test scenarios

- Successful nested spans.
- Application exception recorded and re-raised unchanged.
- Timeout and cancellation.
- MCP `isError: true` mapped to error status.
- Export endpoint unavailable for an entire session.
- Queue overflow under a deliberately slow exporter.
- Process shutdown with pending events.
- Secrets present inside nested dictionaries and headers.

### Exit criteria

- The existing imperfect agent can be instrumented using the new generic SDK.
- A multi-turn conversation with local and MCP tools appears as one trace.
- Turning off the ingest API does not prevent the agent from completing its work.
- SDK/API contract tests run from the same versioned fixtures.

## Milestone 4 — Trace query API and first dashboard slice

### Goal

Make ingested data useful before adding more integrations.

### Work

- Implement application authentication selected in Milestone 0.
- Implement organizations, projects, environments, agents, and API-key management.
- Implement session list, session detail, ordered events, and nested trace APIs.
- Scaffold React/Vite using the existing `voker-voice-design` tokens and assets.
- Build:
  - Project/environment selector.
  - Sessions table and filters.
  - Session header and status.
  - Transcript panel.
  - Nested timeline/waterfall.
  - Error details and jump-to-span.
  - Usage/cost summary.
  - Raw normalized event inspector.
- Add SSE updates for an in-progress session.
- Paginate large event collections and avoid loading unbounded payloads.

### Exit criteria

- A developer can open the trace created in Milestone 3 and explain its execution from the UI.
- Parent-child relationships, agent identity, errors, missing data, and redaction are rendered correctly.
- Live events appear without refreshing the page.
- The implementation visibly follows the provided design package.

## Milestone 5 — LiveKit native adapter

### Goal

Provide the primary one-call framework integration.

### Work

- Add the optional `livekit` package extra without making LiveKit a core dependency.
- Implement `voker_voice.livekit.observe(session, context, agent, ...)`.
- Subscribe to stable LiveKit lifecycle/metrics hooks instead of patching application internals where possible.
- Map session lifecycle, participants, speech, STT, LLM, tools, TTS, playback, interruptions, and errors to canonical events.
- Preserve framework/provider IDs as external attributes.
- Resolve optional recording metadata without requiring a recording.
- Detect and document metrics not exposed by a given LiveKit/provider combination.
- Add version compatibility tests for supported LiveKit versions.
- Build the LiveKit onboarding snippet and verification checklist.

### Exit criteria

- An existing LiveKit sample requires only import, `observe(...)`, API key, and restart.
- A real multi-turn test produces STT -> LLM -> tool -> TTS trace nesting.
- Barge-in/interruption and a provider/tool failure are visible.
- Removing or disabling Voker restores the original application with no structural changes.

## Milestone 6 — LangGraph and multi-agent tracing

### Goal

Make agent routing and handoffs understandable inside the voice trace.

### Work

- Implement the LangGraph callback/wrapper integration.
- Propagate the active Voker session/turn across graph execution.
- Capture graph invocation, node boundaries, retries, interrupt/resume, errors, and completion.
- Associate LangChain/OpenAI-compatible model and tool callbacks where available.
- Implement explicit agent scopes and handoff events.
- Represent subgraphs and child agent runs using parent-child span relationships.
- Detect graph recursion and invalid-state errors without hiding framework exceptions.
- Add agent/handoff filters and visualization to the session detail page.

### Test scenarios

- Router -> specialist -> response.
- Specialist -> second specialist handoff.
- Tool failure followed by successful retry.
- Graph interrupt and resume.
- Recursion-limit failure.
- Parallel nodes with overlapping timestamps.

### Exit criteria

- The dashboard differentiates framework nodes from semantic agents.
- Each handoff shows source, destination, time, reason, and outcome.
- All activity remains under the original voice session trace.
- The current multi-agent test workflow can generate intentional observable failures.

## Milestone 7 — Conversation intelligence and failure analysis

### Goal

Explain why a conversation succeeded, failed, escalated, was abandoned, or remains uncertain using deterministic facts and bounded, evidence-backed semantic analysis while keeping observability independent of the analyzer.

This milestone delivers the primary product differentiator. Milestones 0–6 provide its required evidence foundation; completing traces without this intelligence experience is not completion of the Voker Voice MVP.

### Work

- Implement a versioned deterministic rule engine for:
  - Provider, span, tool/MCP, graph, and session errors.
  - Timeouts, cancellations, retries, and incomplete/missing stages.
  - Configurable STT, LLM, tool, TTS, response-gap, and turn-latency thresholds.
  - Interruptions, talk-over, dead air, abandoned turns, and failed handoffs when observable.
- Persist findings with rule/version, severity, observed value, threshold, and exact evidence IDs.
- Enqueue semantic analysis only after the session reaches a terminal state or is closed as incomplete.
- Implement the structured-output LLM evaluator with:
  - Fixed versioned prompt and Pydantic output schema.
  - Configurable provider/model and low-variance generation settings.
  - Intent, outcome, failure category, summary, confidence, and findings.
  - Mandatory event/span/turn evidence references.
  - Server validation that evidence exists and belongs to the analyzed session.
  - Bounded retry for provider and schema failures.
  - Separate analyzer latency, token, and cost tracking.
- Persist immutable/versioned analysis runs and support controlled re-analysis.
- Add per-project enable/disable and evaluator content controls.
- Build the dynamic session-analysis panel:
  - Queued, running, completed, failed, disabled, and insufficient-evidence states.
  - Separate confirmed facts, detected conditions, inferred findings, and unknowns.
  - Confidence and clickable evidence that seeks to transcript turns/timeline spans.
  - Analyzer model/prompt/analysis version metadata for authorized users.
- Ensure the panel never blocks or replaces the canonical trace.

### Test scenarios

- Explicit tool exception with deterministic finding.
- Slow response without semantic failure.
- Wrong tool argument followed by user correction.
- Agent response contradicts successful tool output.
- Failed multi-agent handoff.
- Analyzer returns an unknown or cross-session evidence ID.
- Invalid structured output followed by successful bounded retry.
- Analyzer provider outage and retry exhaustion.
- Semantic analysis disabled at project level.
- Re-analysis after a prompt/model version change.

### Exit criteria

- A completed failed session automatically queues analysis.
- The dashboard explains the likely failure and every semantic claim links to valid trace evidence.
- Deterministic facts and LLM inferences are visually and structurally distinct.
- The trace and deterministic findings remain fully usable when the analyzer is disabled or unavailable.
- Previous analysis versions remain auditable after re-analysis.

## Milestone 8 — Vapi connector

### Goal

Allow Vapi customers to connect without modifying their application.

### Work

- Implement secure Vapi credential storage and validation.
- List available assistants and save selected mappings to Voker agents.
- Create/configure the Voker webhook through the provider API.
- Preserve an existing customer webhook and configure forwarding when required.
- Verify incoming signatures where supported.
- Persist webhook receipt before asynchronous normalization.
- Map call lifecycle, transcript, messages, tools, errors, cost/usage, and recording metadata to canonical records.
- Implement delivery idempotency and handle out-of-order lifecycle events.
- Add forwarding delivery logs, retries, timeout, and disable controls.
- Build connection, agent selection, test-call verification, and health UI.

### Exit criteria

- Connecting a Vapi agent requires only provider credentials and agent selection.
- One real/test call appears as a canonical trace.
- Duplicate provider delivery does not duplicate the call.
- Existing webhook behavior continues through verified forwarding.

## Milestone 9 — Retell connector

### Goal

Deliver the second no-code managed-platform integration using the established connector boundary.

### Work

- Implement secure Retell credentials and agent discovery.
- Register/configure the provider webhook.
- Verify signatures where supported and persist receipts immediately.
- Map call, transcript, latency, tool, error, usage/cost, outcome, and recording data to canonical records.
- Handle provider retries, duplicate events, partial payloads, and later completion updates.
- Add connection and webhook health UI using shared integration components.
- Add fixture-based contract tests so provider payload changes are detectable.

### Exit criteria

- Connecting a Retell agent requires no customer code changes.
- A completed call produces the same dashboard concepts as SDK and Vapi traces.
- Provider-specific data remains available in raw/debug views without leaking into core UI contracts.

## Milestone 10 — Analytics, costs, and Voice Impact

### Goal

Turn individual traces into useful operational and product insights.

### Work

- Build derived aggregates for session volume, error rate, outcomes, tokens, costs, and latency percentiles.
- Segment by project, environment, agent, version, platform, provider, model, and time.
- Implement rate-card versioning and exact-versus-estimated cost labels.
- Preserve zero-cost usage for free models rather than dropping it.
- Calculate interruption, talk-over, dead-air, correction, escalation, and abandonment metrics when data supports them.
- Build the overview and agent detail screens using the supplied design system.
- Implement basic Voice Impact cohorts:
  - Normal versus high-interruption sessions.
  - Fast versus slow STT finalization.
  - Dead-air cohorts.
  - Outcome comparison and affected-session evidence links.
- Enforce evidence-based product wording and minimum cohort sizes.

### Exit criteria

- Aggregates reconcile with underlying sessions for controlled fixtures.
- Every displayed insight links to its cohort and example sessions.
- Estimated cost is clearly distinguished from provider-reported cost.
- The dashboard never treats missing metrics as zero or inferred outcomes as explicit.

## Milestone 11 — Cloudinary recordings and playback

### Goal

Support optional secure call evidence without making audio mandatory for observability.

### Work

- Store external provider recording metadata without copying by default.
- Add controlled import/upload to authenticated/private Cloudinary assets where needed.
- Persist source, duration, format, retention, and access state.
- Generate short-lived signed playback access from the backend.
- Align transcript turns and trace markers with the audio timeline.
- Handle unavailable, deleted, processing, and access-denied recordings gracefully.
- Add retention/deletion jobs and audit records.

### Exit criteria

- Authorized users can play an available recording with synchronized transcript/timeline markers.
- Unauthorized/public access fails.
- Sessions without recordings retain the complete non-audio trace experience.
- Deleting a recording does not delete the session trace.

## Milestone 12 — Hardening and private beta

### Goal

Prove the MVP completion criteria under realistic failure and load conditions.

### Work

- Run ingestion load tests with batched concurrent sessions and large traces.
- Measure SDK CPU, memory, and event-export overhead.
- Test API/worker/database restart and network-partition scenarios.
- Add integration health, queue/job health, and internal operational metrics.
- Add retention execution, project deletion, API-key rotation, and provider-key rotation.
- Complete security review for project isolation, credential handling, webhooks, recordings, and redaction.
- Add migration/rollback and backup/restore runbooks.
- Pin and document supported Python, LiveKit, and LangGraph versions.
- Run end-to-end beta scripts for custom Python, LiveKit, LangGraph, Vapi, and Retell, including deterministic and semantic failure analysis.
- Resolve all failures that can affect customer agent execution or data isolation.

### Exit criteria

- All MVP completion criteria in `voker-voice.md` pass as end-to-end acceptance tests.
- A Voker outage does not break a test voice agent.
- Tenant-isolation and secret-handling tests pass.
- Private-beta setup docs can be completed by someone who did not build the integration.
- Known limitations are documented and visible to beta users.

## Post-MVP sequence

Do not start these until private-beta evidence validates the canonical model:

1. OpenAI Realtime native integration.
2. Deepgram Voice Agent native integration.
3. ElevenLabs Conversational AI integration.
4. Pipecat adapter.
5. Twilio Media Streams and additional telephony data.
6. TypeScript SDK generated/designed from the stable event protocol.
7. OpenTelemetry interoperability.
8. Alerts, SLOs, anomaly/regression detection, and release comparison.
9. Advanced evaluations, datasets, and scorecards.
10. Voker MCP server for querying traces and analytics.

## First implementation slice

The first useful vertical slice is Milestones 0 through 4:

```text
custom Python instrumentation
  -> canonical event batch
  -> FastAPI ingestion
  -> PostgreSQL trace
  -> session list
  -> session timeline and error detail
```

This slice should be completed before LiveKit, Vapi, or Retell integration work. It proves the product model end to end and gives every later adapter a visible, testable destination.

The first complete voice-failure intelligence path is Milestones 0 through 7:

```text
live voice session
  -> canonical capture and live trace
  -> deterministic failure findings
  -> completed session
  -> asynchronous structured semantic analysis
  -> dynamic outcome and failure explanation
  -> exact transcript/event/span evidence
```

Milestone 7 is therefore part of the MVP, not an optional analytics enhancement.
