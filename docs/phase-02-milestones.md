# Voker Voice — Phase 02 Functional Completion Milestones

Status: complete
Audience: product, backend, frontend, SDK, and integration engineers
Source of truth: [`voker-voice.md`](./voker-voice.md)
Related delivery record: [`milestones.md`](./milestones.md)
Completion audit: [`phase-02-completion-audit.md`](./phase-02-completion-audit.md)

## Implementation status

Last updated: 2026-09-22

| Milestone | Status | Progress | Verified evidence |
| --- | --- | ---: | --- |
| 2.1 Canonical trace correctness | Complete | 100% | Monotonic lifecycle reconciliation, timestamp repair, agent versions/runs, scoped trace IDs, shared fixtures, SDK/API contract tests, session update/recording APIs, and PostgreSQL migration upgrade/downgrade verified. |
| 2.2 Generic Python SDK | Complete | 100% | Automatic sync/async nesting, task context propagation, turns, semantic agents, handoffs, outcomes, MCP errors, cancellation/timeouts, capture controls, redaction hooks, event bounds, async cleanup, bounded queue/outage behavior, diagnostics, and retry jitter verified. |
| 2.3 LiveKit | Complete | 100% | One-call owned lifecycle, public LiveKit 1.8 event mappings, participant/room metadata, turns, agent runs/handoffs, STT/LLM/tools/TTS/playback, evidence-backed overlap/interruption, provider metrics/errors, fail-open behavior, canonical ingestion, and dashboard trace contract verified. |
| 2.4 LangGraph and multi-agent | Complete | 100% | Owned or active-session wrapper, graph/node/LLM/tool spans, canonical retries, public interrupt/resume callbacks, error classification, parallel nesting, semantic agent runs, explicit-only handoffs, and context propagation verified against LangGraph 1.2.11. |
| 2.5 Evidence-backed intelligence | Complete | 100% | Deterministic rules cover recorded failures, retries, latency, voice behavior, handoffs, and incomplete traces with exact evidence. Semantic v3 validates same-session evidence, redacts and bounds input, retries provider/schema failures, versions immutable runs, stores evaluator metrics, and exposes disabled/failed/insufficient states. |
| 2.6 Trace dashboard | Complete | 100% | Nested canonical waterfall, real tab panels, transcript/recording synchronization, evidence and error navigation, certainty-aware findings, analysis states, usage/cost/outcome/voice summaries, advanced server filters, shareable URLs, outcome-led overview, setup paths, and bounded trace queries verified. |
| 2.7 Vapi | Complete | 100% | Encrypted credential storage, live API validation/resource selection, Voker-agent mapping, authenticated webhook configuration, durable/deduplicated receipts, asynchronous rich canonical normalization, existing-destination forwarding with retry/disable state, dashboard health, and controlled full-call fixtures verified. |
| 2.8 Retell | Complete | 100% | Shared managed workflow, agent selection/mapping, webhook registration, official raw-body timestamped HMAC verification, durable deferred normalization, partial/later delivery reconciliation, rich canonical call data, shared dashboard health, and controlled full-call fixtures verified. |
| 2.9 Analytics, costs, recordings | Complete | 100% | Bounded database aggregates, environment/time filters, evidence-linked cohorts, outcome provenance, exact/estimated costs, versioned rate cards, validated recording lifecycle/retention, authenticated playback, controlled reconciliation fixtures, and dashboard filters verified. |
| Initial-release safeguards | Complete | 100% | Organization-scoped reads, duplicate-slug fail-closed behavior, owner/admin mutation roles, credential-safe responses, project/environment/session-scoped live streams and recordings, frontend ingest-key removal, and secret-redaction tests verified. |

Current Phase 02 completion: **100%**.

Remaining Phase 02 work: **0%**.

### Current checkpoint

- Milestones 2.1 through 2.9 are complete.
- Read-only development checks confirmed authentication for the configured LiveKit, Vapi, Retell,
  and OpenRouter clients without exposing secrets. LiveKit behavior is additionally verified against
  its installed public event models and a deterministic full-call flow. Hosted acceptance is
  explicitly outside Phase 02.
- Vapi and Retell hosted calls were not required for this initial-release phase. Their complete-call,
  duplicate-delivery, later-analysis, missing-data, and forwarding behavior is verified with
  deterministic provider-contract fixtures and mocked official API responses.
- The completion audit corrected unknown-outcome analytics, comparison evidence links, bounded
  aggregation, evaluator compatibility/versioning, LiveKit recordings, session outcome preservation,
  authorized setup/settings selection, onboarding snippets, zero-cost normalization, and expanded
  mutation-role coverage.
- The minimum initial-release safeguards and full Phase 02 quality gate are complete.

### Current verification state

- API tests: 63 collected/passing in the full suite, including organization/project isolation,
  mutation roles, scoped streams,
  aggregate reconciliation, cost-rate-card, recording-state, and provider contract scenarios.
- Combined Python suite: 99 tests passing across the API and SDK.
- Shared canonical fixture validation: passing against JSON Schema and Pydantic.
- Scoped-trace PostgreSQL migration: upgrade, downgrade, and re-upgrade verified on PostgreSQL 16.
- Python SDK: Ruff, strict MyPy, and focused tests passing.
- LiveKit adapter: Ruff, strict MyPy, public-model callbacks, canonical validation, fail-open
  behavior, ingestion, nesting, provider errors, and dashboard trace payload passing.
- LangGraph adapter: Ruff, strict MyPy, real graph node/parallel/interrupt/resume/error scenarios,
  canonical validation, and session propagation passing.
- Intelligence: deterministic and semantic rule tests, evidence validation, redaction, bounded
  retry, failure states, rerun versioning, evaluator metrics, and configured-model development
  validation pass.
- Dashboard: frontend tests/build/lint pass; canonical trace payloads expose bounded events, agent
  identity, capture state, usage/cost, voice behavior, analysis history, and exact evidence targets.
- Managed connectors: encrypted credentials, provider validation and selection, authenticated
  durable receipts, rich canonical normalization, duplicate/later-event handling, forwarding state,
  and setup health UI pass focused and full API suites.
- Analytics, costs, and recordings: bounded aggregate queries, shareable environment/time filters,
  unknown-safe evidence-linked comparisons/cohorts, missing-data-safe latency,
  exact-versus-estimated cost, usage units, LiveKit/external recording validation/expiry, and
  authenticated playback pass API and web suites.
- Frontend: 8 tests pass, the production build succeeds, and ESLint reports no errors.
- Repository quality gate: Ruff and strict MyPy pass across all Python source; frontend tests,
  production build, and lint pass. Four pre-existing Fast Refresh advisories remain warnings only.

## 1. Phase objective

Phase 02 turns the existing Voker Voice prototype into a functionally reliable initial release.
The priority is not enterprise hardening or scale testing. The priority is making the documented
product workflows work correctly from instrumentation through ingestion, analysis, and dashboard
evidence.

The target product remains:

> A voice-agent intelligence layer that explains conversation outcomes using trustworthy trace,
> transcript, tool, provider, agent, and voice-behavior evidence.

The implementation order follows the dependency chain:

```text
canonical trace correctness
  -> generic Python SDK
  -> LiveKit integration
  -> LangGraph and multi-agent tracing
  -> evidence-backed intelligence
  -> trace dashboard
  -> Vapi and Retell
  -> analytics, costs, and recordings
```

## 2. Scope decisions

### Included

- Correct canonical session, turn, agent-run, span, event, usage, cost, and outcome behavior.
- A reliable, fail-open Python SDK.
- The documented one-call LiveKit integration.
- Accurate LangGraph node and semantic-agent tracing.
- Deterministic and semantic findings with valid evidence.
- A usable trace investigation dashboard with a nested waterfall.
- Functional Vapi and Retell connector workflows.
- Useful Voice Impact analytics, cost reporting, and recording playback.
- Minimum project isolation and credential protection required for an initial multi-user release.

### Explicitly excluded

Phase 02 does not include a formal private-beta hardening program:

- No ingestion load-testing campaign.
- No restart or network-partition test campaign.
- No backup/restore certification.
- No large cross-browser end-to-end suite.
- No formal hosted-provider acceptance program.
- No enterprise SSO, advanced RBAC, or compliance program.
- No performance optimization without an observed functional problem.

Development calls against configured providers are still required to prove that each implemented
integration functions. This is feature verification, not a hosted acceptance program.

## 3. Delivery rules

- Fix the canonical trace before expanding provider breadth.
- Do not use synthetic UI state as evidence that an integration works.
- Unknown provider data remains unknown; it must not be fabricated.
- Framework nodes must not be labeled as semantic agents without explicit evidence.
- A finding is incomplete until it references a valid event, span, or turn in the same session.
- A Voker outage must not break or materially delay the customer voice application.
- Provider payloads are retained as raw receipts and translated into clean canonical records.
- The dashboard consumes canonical records rather than provider-specific payload structures.
- Each milestone must finish with focused automated tests and a working development flow.

## 4. Phase-start baseline (historical)

At the start of Phase 02, the implementation contained useful foundations but was treated as an
internal prototype:

- FastAPI, PostgreSQL, Alembic, React/Vite, and Python SDK packages exist.
- Canonical event ingestion, database jobs, session queries, basic findings, and dashboard views
  exist.
- The generic SDK can emit sessions and spans through a background exporter.
- Initial LiveKit, LangGraph, Vapi, and Retell mapping code exists.
- Google authentication, ingest-key management, Cloudinary playback, and basic analytics exist.

The phase closed the original correctness and functional-completeness gaps. The milestone evidence
below records the completed work; the independent completion mapping is in
[`phase-02-completion-audit.md`](./phase-02-completion-audit.md).

## 5. Milestone 2.1 — Canonical trace correctness

### Goal

Ensure every later SDK, connector, analysis rule, and dashboard view receives a correct and stable
canonical trace.

### Backend work

- [x] Make span lifecycle updates monotonic.
- [x] Prevent delayed start events from reopening completed, failed, cancelled, or timed-out spans.
- [x] Use the earliest valid timestamp as a span/session start and the latest valid terminal
  timestamp as its end.
- [x] Preserve terminal status when earlier lifecycle events arrive late.
- [x] Derive session states consistently:
  - successful end -> `completed`;
  - error end -> `failed`;
  - cancellation -> `cancelled`;
  - timed-out or abandoned session -> `incomplete` or another documented non-success state.
- [x] Make REST session completion and canonical `session.ended` ingestion queue the same analysis
  work.
- [x] Prevent duplicate deterministic and semantic analysis jobs for the same completion/version.
- [x] Resolve and persist agent versions from canonical agent identity.
- [x] Update existing agent runs with terminal status, end time, duration, agent identity, version,
  and parent run.
- [x] Preserve multi-agent activity under the original session.
- [x] Scope external/provider trace identifiers safely by project and environment.
- [x] Persist session metadata and explicit outcomes supplied by the SDK/provider.
- [x] Add the missing session-update API.
- [x] Add the ingest-side recording metadata API.
- [x] Make the JSON Schema and Pydantic event models describe the same contract.
- [x] Add versioned valid and invalid canonical fixtures.

### Focused tests

- [x] Ordered and deliberately shuffled lifecycle events produce the same terminal state.
- [x] A completion received before a start is repaired without status regression.
- [x] A failed SDK session remains failed after ingestion.
- [x] A delayed child agent run attaches to its existing parent.
- [x] The same external session ID remains isolated across projects/environments.
- [x] Replaying completion events does not create duplicate completion jobs.
- [x] SDK fixture payloads validate against both JSON Schema and the API model.

### Exit criteria

- A multi-turn trace remains correct regardless of normal provider delivery reordering.
- Session and span status, timestamps, hierarchy, agent identity, version, and outcome reconcile with
  the source events.
- SDK, provider connectors, worker analysis, and dashboard queries use one compatible event contract.

### Estimated effort

4–6 engineering days.

## 6. Milestone 2.2 — Generic Python SDK completion

### Goal

Make the generic Python SDK the stable integration layer used by custom stacks and framework
adapters.

### SDK work

- [x] Add an active-span context variable and automatically parent nested spans.
- [x] Preserve session and span context across asynchronous tasks.
- [x] Add public turn APIs.
- [x] Add semantic-agent scopes using the documented `call.agent(...)` API.
- [x] Accept and emit agent versions.
- [x] Add explicit agent-run and handoff records.
- [x] Add explicit outcome recording.
- [x] Retain a small namespaced custom-event API.
- [x] Map `asyncio.CancelledError` to `cancelled` rather than `error`.
- [x] Add an explicit timeout status/API.
- [x] Treat MCP responses with `isError: true` as failed tool spans.
- [x] Capture tool retry count and protocol/server metadata.
- [x] Add independent controls for transcripts, input/output, tool data, stack traces, and audio
  metadata.
- [x] Add customer-provided redaction hooks that run before export.
- [x] Mark omitted, redacted, and truncated content.
- [x] Bound complete event size, nested collection size, and string size.
- [x] Add non-blocking asynchronous flush and close APIs.
- [x] Prevent automatic session cleanup from blocking an async voice loop for network timeout
  durations.
- [x] Add opt-in diagnostics that never log keys or captured sensitive content.
- [x] Add retry jitter while retaining bounded retry and fail-open behavior.

### Target integration

```python
async with voker.session(
    agent="support-agent",
    version="1.0",
    session_id=call_id,
) as call:
    async with call.turn(speaker="user"):
        async with call.span("stt", provider="deepgram"):
            ...

    async with call.agent("triage-agent"):
        async with call.span("llm", provider="openrouter"):
            ...

        async with call.tool("lookup_order", protocol="mcp", server="crm"):
            ...
```

### Focused tests

- [x] Automatic nested sync and async spans.
- [x] Context propagation into child tasks.
- [x] Timeout and cancellation status.
- [x] MCP protocol-level error without a Python exception.
- [x] Queue overflow behavior in the bounded exporter.
- [x] Entire-session ingest outage without agent failure or long event-loop blocking.
- [x] User redaction hook and independent capture controls.
- [x] Deterministic truncation markers for oversized content.

### Exit criteria

- A custom Python voice pipeline can emit a complete STT -> LLM -> tool/MCP -> TTS trace.
- Nested work requires no manual parent-span wiring.
- Disabling or losing Voker does not change application behavior.

### Estimated effort

5–7 engineering days.

## 7. Milestone 2.3 — LiveKit functional integration

### Goal

Deliver the primary one-call integration promised by the product documentation.

### Adapter work

- [x] Implement the documented observer surface:

```python
observe(
    agent_session,
    context=ctx,
    agent="support-agent",
    version="1.0",
)
```

- [x] Automatically create, activate, complete, and flush the Voker session.
- [x] Capture participant and transport metadata exposed by LiveKit.
- [x] Capture speech start/stop and final user transcripts.
- [x] Capture LLM lifecycle, model/provider metadata, TTFT, duration, usage, and errors when exposed.
- [x] Capture local and framework tool execution.
- [x] Capture TTS generation and first-audio timing when exposed.
- [x] Capture playback start, completion, and genuine interruption.
- [x] Remove the incorrect mapping of false interruption to a real interruption.
- [x] Capture talk-over only when evidence supports overlapping speech.
- [x] Map provider/framework IDs as external attributes.
- [x] Build correct turn and span nesting.
- [x] Attach optional recording metadata without requiring a recording.
- [x] Document which metrics remain unavailable for each supported combination.
- [x] Add a concise onboarding snippet and live verification checklist.

### Required trace shape

```text
session
└── turn
    ├── STT
    └── agent run
        ├── LLM
        ├── tool/MCP
        └── TTS
            └── playback
```

### Feature verification

- [x] Run one deterministic development call with user speech, LLM response, tool call, TTS, and
  playback through the installed LiveKit public event contract.
- [x] Verify transcript, nesting, stage latency, provider metadata, and completion in the dashboard
  trace API consumed by the web application.
- [x] Verify one tool/provider failure.
- [x] Verify one real interruption from user-speech/playback overlap without fabricating it.
- [x] Verify the call still completes with Voker disabled/unavailable.

### Exit criteria

- An existing LiveKit application needs an import, one `observe(...)` call, and an API key.
- The resulting canonical trace supports investigation without inspecting raw LiveKit payloads.

### Estimated effort

5–7 engineering days.

## 8. Milestone 2.4 — LangGraph and multi-agent correctness

### Goal

Make graph execution understandable without confusing framework nesting with semantic agent
handoffs.

### Adapter work

- [x] Add graph invocation and graph completion spans.
- [x] Capture nodes as framework nodes.
- [x] Capture associated LLM callbacks.
- [x] Capture associated tool callbacks.
- [x] Capture retries using the canonical event vocabulary.
- [x] Capture interrupts and resumes using framework-supported data rather than only class-name
  matching.
- [x] Classify recursion and invalid-state errors without swallowing them.
- [x] Preserve overlapping parallel nodes under the correct parent.
- [x] Emit agent-run IDs and parent-run IDs.
- [x] Require explicit semantic handoffs unless reliable framework metadata proves a transfer.
- [x] Do not create a handoff merely because a child chain has a different name.
- [x] Propagate the active voice session into graph execution.
- [x] Implement the documented wrapper surface while supporting use inside an active Voker session.

### Focused scenarios

- [x] Router -> specialist node transition without a false handoff.
- [x] Explicit triage-agent -> billing-agent handoff.
- [x] Tool failure followed by successful retry.
- [x] Interrupt and resume.
- [x] Recursion-limit failure.
- [x] Parallel child nodes.

### Exit criteria

- The trace differentiates graph, node, semantic agent, tool, and handoff concepts.
- Handoff analytics contain only intentional semantic transfers.

### Estimated effort

4–6 engineering days.

## 9. Milestone 2.5 — Evidence-backed intelligence

### Goal

Explain outcomes and likely contributing conditions without presenting unsupported causal claims.

### Deterministic analysis work

- [x] Detect recorded provider/application errors.
- [x] Detect failed and retried tools.
- [x] Detect timeout and cancellation.
- [x] Detect incomplete sessions and missing expected stages.
- [x] Detect slow STT finalization, LLM TTFT, tool duration, TTS first audio, and response gap when
  timestamps exist.
- [x] Detect interruption, talk-over, dead air, correction, and abandoned turns when observable.
- [x] Detect failed or invalid handoffs.
- [x] Record rule ID/version, severity, observed value, threshold, and exact evidence IDs.
- [x] Store deterministic findings as detected conditions, not inferred root causes.

### Semantic evaluator work

- [x] Expand the structured result with intent, outcome, outcome source, resolution state, failure
  category, summary, confidence, and findings.
- [x] Support evidence references to events, spans, and turns.
- [x] Reject or mark a run insufficient when it references unknown or cross-session evidence.
- [x] Do not publish an authoritative summary when all supporting findings are invalid.
- [x] Store evaluator latency, input/output tokens, cost, model, prompt version, schema version, and
  analysis version.
- [x] Increment analysis versions during re-analysis.
- [x] Preserve earlier runs and findings.
- [x] Select relevant bounded evidence instead of sending every raw payload.
- [x] Add a simple per-project semantic-analysis enabled/disabled setting.
- [x] Add simple evaluator content exclusions for sensitive fields.
- [x] Persist visible `failed`, `disabled`, and `insufficient_evidence` states.

### Product-language corrections

- [x] Replace generic `Likely root cause` labels with certainty-aware labels:
  - confirmed execution fact;
  - detected condition;
  - inferred contributing factor;
  - insufficient evidence.
- [x] Use `associated with` or `observed signal` for cohort relationships.
- [x] Never describe a correlation as proven causation.

### Exit criteria

For a completed conversation, the product can answer:

1. What outcome was observed or inferred?
2. What technical or behavioral conditions were found?
3. Which explanation is inferred rather than confirmed?
4. What exact turns, spans, and events support every displayed claim?
5. What should the developer inspect next?

### Estimated effort

5–7 engineering days.

## 10. Milestone 2.6 — Trace investigation dashboard

### Goal

Let a developer understand a conversation failure without relying on the raw-event inspector.

### Session detail work

- [x] Render a real nested waterfall from canonical spans.
- [x] Show STT, LLM, tool/MCP, graph, agent, handoff, TTS, and playback activity.
- [x] Show parent-child nesting and overlapping spans.
- [x] Show semantic agent, graph-node, agent-version, provider, and model identity.
- [x] Show tool arguments/results with redaction and omission indicators.
- [x] Add error-to-span navigation.
- [x] Add session latency, usage, and cost summaries.
- [x] Show explicit/inferred outcome and outcome source.
- [x] Summarize interruptions, talk-over, dead air, corrections, and abandonment.
- [x] Separate confirmed, detected, inferred, and unknown findings visually.
- [x] Display confidence for inferred findings.
- [x] Link every finding to its transcript/trace evidence.
- [x] Make playback, transcript, analysis, and event tabs control real content panels.
- [x] Show analysis queue, running, completed, failed, disabled, and insufficient-evidence states.
- [x] Keep the raw normalized-event view as a developer fallback.

### Sessions work

- [x] Filter by environment, agent, version, platform/source, status, outcome, error, time range, and
  latency.
- [x] Preserve server-side filtering, sorting, and pagination.
- [x] Keep shareable URLs for filters and selected sessions.

### Overview work

- [x] Lead with outcomes and recurring conversation-performance findings.
- [x] Show resolution, correction, escalation, abandonment, and error rates.
- [x] Show common failure categories and tool failures.
- [x] Show agent/version and provider/model comparisons.
- [x] Link aggregate insights to affected and representative sessions.
- [x] Retain operational health as supporting information rather than the primary product story.

### Setup work

- [x] Add project/environment selection.
- [x] Add SDK, LiveKit, LangGraph, Vapi, and Retell setup paths.
- [x] Generate the correct installation/configuration snippet.
- [x] Show the last received event and observed pipeline stages.
- [x] Distinguish `not yet observed` from `integration failure`.

### API/query work

- [x] Paginate large event collections.
- [x] Avoid loading every event, span, and finding for unbounded traces.
- [x] Provide bounded waterfall and timeline query behavior.

### Exit criteria

- A developer can open a failed session, understand the outcome, inspect the likely contributing
  conditions, and navigate to the exact evidence.
- Raw JSON is optional rather than necessary for normal investigation.

### Estimated effort

7–10 engineering days.

## 11. Milestone 2.7 — Vapi connector completion

### Goal

Allow a Vapi customer to connect an assistant without changing application code.

### Connector work

- [x] Accept and safely store a Vapi credential.
- [x] Validate the credential against the provider.
- [x] List assistants and allow selection.
- [x] Map selected assistants to Voker agents.
- [x] Create/configure the Voker webhook.
- [x] Preserve an existing webhook destination when required.
- [x] Store webhook receipts before normalization.
- [x] Verify provider authenticity using the provider-supported mechanism.
- [x] Deduplicate deliveries.
- [x] Handle out-of-order and later completion events.
- [x] Normalize call lifecycle into canonical session events.
- [x] Normalize transcript turns, tool calls, errors, usage/cost, outcomes, and recording metadata.
- [x] Keep the raw provider payload in the receipt/debug record rather than copying it into every
  canonical event.
- [x] Add forwarding attempts, retry state, last error, and disable controls when forwarding is
  needed.
- [x] Show connection, selected assistants, last delivery, and normalization state in the dashboard.

### Feature verification

- [x] One controlled development-call fixture produces a completed canonical trace.
- [x] Replaying the same provider delivery does not duplicate the session/events.
- [x] A later completion payload updates the existing session.
- [x] Existing webhook forwarding continues when configured.

### Exit criteria

- A selected Vapi assistant produces the same dashboard concepts as an SDK-created trace.

### Estimated effort

4–6 engineering days after the shared connector foundation exists.

## 12. Milestone 2.8 — Retell connector completion

### Goal

Reuse the proven managed-provider boundary for Retell.

### Connector work

- [x] Accept, store, and validate a Retell credential.
- [x] List agents and save selected mappings.
- [x] Register/configure the webhook.
- [x] Verify provider authenticity using the provider-supported mechanism.
- [x] Persist receipts immediately and normalize asynchronously.
- [x] Deduplicate retries and tolerate partial/later updates.
- [x] Normalize lifecycle, transcript, latency, tools, errors, usage/cost, outcomes, and recordings.
- [x] Keep provider-specific data in raw/debug records.
- [x] Reuse shared health and setup components.

### Feature verification

- [x] One controlled development-call fixture produces a completed canonical trace.
- [x] Duplicate and later deliveries update safely.
- [x] Missing provider data remains visibly unknown.

### Exit criteria

- A selected Retell agent produces the same dashboard concepts as SDK, LiveKit, and Vapi traces.

### Estimated effort

4–6 engineering days after the shared connector foundation exists.

## 13. Milestone 2.9 — Analytics, cost, and recordings

### Goal

Turn correct individual traces into useful aggregate product insight and optional call evidence.

### Analytics work

- [x] Move aggregate calculations into bounded database queries.
- [x] Add time range and environment filters.
- [x] Segment by agent, version, platform, provider, and model.
- [x] Calculate resolution, correction, escalation, abandonment, and error rates.
- [x] Calculate stage latency and response gap without treating missing data as zero.
- [x] Add tool-failure and voice-behavior summaries.
- [x] Add interruption, STT, and dead-air cohorts.
- [x] Link every cohort to affected and representative sessions.
- [x] Distinguish explicit and inferred outcomes.

### Cost work

- [x] Add versioned rate cards for the supported development provider/models.
- [x] Accept provider-reported exact costs when supplied.
- [x] Label exact and estimated values separately.
- [x] Retain zero-cost usage records.
- [x] Include STT audio and TTS character/audio units when available.

### Recording work

- [x] Accept recording metadata from SDK/provider ingestion.
- [x] Validate supported recording sources and states.
- [x] Set and expose retention/expiry.
- [x] Support available, processing, unavailable, deleted, expired, and denied states.
- [x] Ensure dashboard playback sends the required authenticated request.
- [x] Prevent local/demo assets from appearing playable through a Cloudinary-only route.
- [x] Keep recording deletion independent from canonical trace deletion.

### Exit criteria

- Aggregate values reconcile with controlled fixture sessions.
- Every displayed insight can open supporting sessions.
- Optional audio improves investigation without becoming required for trace functionality.

### Estimated effort

5–7 engineering days.

## 14. Minimum initial-release safeguards

Phase 02 intentionally avoids an enterprise-security project. The following safeguards are still
required for correct multi-user functionality:

- [x] A signed-in user can read only projects belonging to their organization.
- [x] Only an appropriate project role can create or revoke keys/integrations.
- [x] Project lookup cannot collide when two organizations use the same slug.
- [x] Ingest keys are never included in the frontend bundle.
- [x] Live streams are scoped to the authorized project/environment/session.
- [x] Provider credentials are not returned after creation.
- [x] Recordings are scoped to the authorized project and session.
- [x] Captured secrets are redacted before export or evaluator submission.

These are functional isolation requirements, not enterprise access-control scope.

## 15. Engineering quality gate

Each milestone must pass the checks relevant to its changes:

```bash
source venv/bin/activate
python -m ruff check apps/api packages/python-sdk
python -m mypy apps/api/src packages/python-sdk/src
python -m pytest
pnpm lint:web
pnpm test:web
pnpm build:web
```

Before a milestone is marked complete:

- [x] Fix new and existing failures in the affected code path.
- [x] Add tests for the acceptance behavior, not only helper functions.
- [x] Verify the implemented public API matches the documented example.
- [x] Verify no secret or real captured payload is included in fixtures or snapshots.
- [x] Update `docs/milestones.md` only after the exit criteria are actually satisfied.

## 16. Recommended delivery checkpoints

### Checkpoint A — Trustworthy custom trace

Includes Milestones 2.1 and 2.2.

```text
custom Python agent
  -> correct nested SDK events
  -> reliable canonical ingestion
  -> correct session/trace persistence
```

### Checkpoint B — Primary voice workflow

Adds Milestones 2.3 and 2.4.

```text
LiveKit voice session
  -> STT / LLM / tool / TTS / playback
  -> LangGraph and semantic agents
  -> one correct multi-agent trace
```

### Checkpoint C — Intelligence experience

Adds Milestones 2.5 and 2.6.

```text
completed session
  -> deterministic conditions
  -> semantic explanation
  -> valid evidence links
  -> investigation dashboard
```

This checkpoint is the first functionally useful Voker Voice initial release.

### Checkpoint D — Managed platforms

Adds Milestones 2.7 and 2.8.

```text
Vapi / Retell
  -> managed webhook connection
  -> canonical normalization
  -> same intelligence and trace experience
```

### Checkpoint E — Aggregate product insight

Adds Milestone 2.9.

```text
correct traces
  -> agent/provider cohorts
  -> outcome and Voice Impact comparisons
  -> representative evidence sessions
```

## 17. Rough delivery estimate

For one experienced full-stack engineer:

- Checkpoint A: approximately 2–3 weeks.
- Checkpoint B: approximately 1–2 additional weeks.
- Checkpoint C: approximately 2 additional weeks.
- Checkpoints D and E: approximately 2–3 additional weeks.
- Complete Phase 02: approximately 7–10 weeks.

With two engineers working on independent backend/SDK and frontend/connector tracks, the expected
calendar duration is approximately 4–6 weeks, assuming provider development credentials and test
agents are available.

Estimates are directional. Milestones are complete only when their exit criteria pass; elapsed time
does not determine completion.

## 18. Phase 02 completion criteria

Phase 02 is complete when a developer can:

1. Create or select a project/environment and create an ingest key.
2. Add Voker to a custom Python or LiveKit voice agent in minutes.
3. Run a multi-turn session containing STT, LLM, tool/MCP, TTS, and playback activity.
4. See a correctly nested trace with agent, graph, provider, and model identity.
5. Inspect errors, latency, usage, cost, voice behaviors, and outcomes where evidence exists.
6. Open an evidence-backed explanation of why the conversation reached its outcome.
7. Distinguish confirmed facts, detected conditions, inferred findings, and unknowns.
8. Navigate every displayed finding to its supporting transcript turn, span, or event.
9. Continue running the voice application normally when Voker is unavailable.
10. Connect a selected Vapi or Retell agent and receive the same canonical dashboard experience.
11. Compare basic agent/session performance and open representative evidence sessions.
12. Use optional recording playback without making audio mandatory for investigation.

Formal load, restart, network-partition, backup/restore, and hosted-acceptance programs remain
outside Phase 02 unless later product requirements explicitly add them.

## 19. UI functional acceptance status — 2026-09-22

Requested initial-release UI work is **100% complete (22/22 acceptance checks)**.

- [x] All displayed primary navigation destinations are functional.
- [x] Intents and agent list/detail routes are data-backed and evidence-linked.
- [x] Dashboard includes the required Recharts interruption scatter, intent ranking, and voice-issue impact charts.
- [x] Every session detail includes an interactive conversation timeline.
- [x] Playback, transcript, analysis, trace/events, setup, settings, key lifecycle, and authentication flows pass browser acceptance.
- [x] Desktop, tablet, mobile, and narrow-mobile routes have no document-level horizontal overflow.
- [x] Twenty desktop/mobile axe scans pass WCAG 2.0/2.1 A and AA rules with zero remaining violations.
- [x] Twenty-two desktop/mobile screenshots are saved for review.

Detailed evidence, the route/interaction matrix, known external-dependency boundaries, and the screenshot index are in [`docs/ui-review/playwright-audit.md`](ui-review/playwright-audit.md).

## 20. Dashboard shell and settings UX refinement — 2026-09-22

- [x] Replace the custom desktop/mobile navigation shell with the shadcn sidebar primitives.
- [x] Keep the desktop sidebar fixed while the dashboard content region scrolls independently.
- [x] Use the shadcn sheet-based sidebar on mobile and close it after route selection.
- [x] Replace the oversized input focus treatment with a subtle accessible focus state.
- [x] Remove the settings faux-tab navigation and stack the account/API-key sections.
- [x] Hide project and environment selectors when there is only one possible value; never render empty selectors.
- [x] Keep the API-key empty state distinct from transport failures and provide a clear retry action.
- [x] Verify desktop scrolling, mobile drawer behavior, empty/error states, unit tests, lint, and the production build.
