# Voker Voice — Phase 02 Completion Audit

Status: complete after functional remediation and full quality-gate verification

Audit date: 2026-09-22

Scope: functional initial release defined by [`voker-voice.md`](./voker-voice.md) and
[`phase-02-milestones.md`](./phase-02-milestones.md)

## 1. Audit conclusion

Phase 02 is functionally complete. All nine delivery milestones and the minimum initial-release
safeguards have implementation and automated acceptance evidence. The completion audit also found
and corrected gaps that were hidden by the earlier aggregate status:

- comparison rates treated unknown outcomes as failures and comparison cards had no representative
  session target;
- one overview calculation loaded all span durations instead of aggregating in the database;
- the configured OpenRouter model rejected the evaluator's provider-specific response-format
  option, and the evaluator did not retry malformed model output;
- the changed semantic prompt was still recorded as `semantic-v2` instead of a new immutable
  version;
- public recording ingestion did not recognize LiveKit as an external recording source;
- ending a session without an outcome could erase an earlier explicit outcome;
- setup and API-key workflows could keep an unauthorized build-time project/environment default;
- generated Python snippets omitted required imports, and the LangGraph snippet referenced an
  uninitialized client;
- Vapi normalization discarded legitimate zero cost/token values because it used truthiness
  fallbacks;
- member-role mutation coverage did not exercise all key and integration write operations.

These issues are fixed and covered by regression tests. Formal load, restart, outage, backup,
browser-matrix, and hosted-provider acceptance campaigns remain deliberately excluded.

## 2. Completion score

| Area | Weight | Result | Evidence summary |
| --- | ---: | ---: | --- |
| Canonical trace correctness | 12% | 12% | Ordered/reordered lifecycle reconciliation, scoped identities, outcomes, recordings, completion jobs, shared contracts. |
| Generic Python SDK | 12% | 12% | Nested sync/async scopes, turns, agents, handoffs, controls, redaction, bounds, fail-open export. |
| LiveKit integration | 11% | 11% | Owned lifecycle, public callbacks, full pipeline mapping, voice evidence, canonical ingestion. |
| LangGraph and multi-agent | 9% | 9% | Graph/node/tool/LLM spans, parallelism, retries, interrupts, explicit semantic handoffs. |
| Evidence-backed intelligence | 13% | 13% | Deterministic rules, bounded semantic evaluation, valid evidence, visible states, immutable versions. |
| Investigation dashboard | 13% | 13% | Nested trace, real panels, evidence navigation, filters, setup workflows, bounded queries. |
| Vapi connector | 8% | 8% | Validated managed connection, durable receipts, normalization, forwarding, health state. |
| Retell connector | 7% | 7% | Signed durable webhook path, reconciliation, normalization, shared setup/health experience. |
| Analytics, costs, recordings | 10% | 10% | Database aggregates, unknown-safe cohorts, rate cards, exact zero values, scoped playback. |
| Initial-release safeguards | 5% | 5% | Organization isolation, mutation roles, scoped streams/assets, credential-safe responses. |
| **Phase 02 total** | **100%** | **100%** | **All in-scope functional criteria pass.** |

Remaining in-scope Phase 02 work: **0%**.

## 3. Milestone evidence

### 2.1 Canonical trace correctness

Implementation is centered in
[`ingestion.py`](../apps/api/src/voker_voice_api/ingestion.py),
[`routers/ingest.py`](../apps/api/src/voker_voice_api/routers/ingest.py), and the canonical models.
The public HTTP acceptance path creates a LiveKit session, records an explicit outcome, attaches a
recording, ends the session twice, preserves the explicit outcome, and queues exactly one
deterministic and one semantic analysis run. Analysis jobs record `deterministic-v2` and
`semantic-v3`, so results remain tied to immutable implementations.

Evidence: `test_ingestion.py`, canonical fixture/schema tests, lifecycle reconciliation tests, and
scoped-trace migration checks.

### 2.2 Generic Python SDK

The SDK owns session, turn, agent, span, tool/MCP, outcome, and handoff emission. Context variables
provide automatic nesting across synchronous, asynchronous, and child-task work. Export is bounded,
timed, retried with jitter, redacted before transmission, and fail-open. Cancellation, timeout,
protocol errors, omitted content, and truncation are canonical states rather than incidental logs.

Evidence: the full `packages/python-sdk/tests` suite and strict type/lint checks.

### 2.3 LiveKit

The adapter owns the documented one-call observer lifecycle and maps installed LiveKit 1.8 public
events into turns, agent runs, STT, LLM, tool, TTS, playback, provider error, interruption, and
overlap evidence. It does not fabricate interruption or talk-over. LiveKit recording references are
now accepted as authenticated external HTTPS assets by the recording API.

Evidence: LiveKit adapter contract tests, full-call fixture ingestion, dashboard trace assertions,
fail-open tests, and recording-source regression tests.

### 2.4 LangGraph and multi-agent behavior

The callback/wrapper path differentiates graph invocations, nodes, semantic agents, tools, retries,
interrupt/resume, and explicit handoffs. Parallel branches retain correct parents, and framework
names alone do not manufacture semantic transfers.

Evidence: real graph execution tests covering routing, parallel nodes, retry, interrupt/resume,
recursion failure, nested session propagation, and explicit handoffs.

### 2.5 Evidence-backed intelligence

Deterministic analysis emits detected conditions with exact evidence and versioned rules. Semantic
analysis selects bounded evidence, removes excluded fields, requests a strict schema, validates
same-session IDs, and exposes completed, failed, disabled, and insufficient-evidence states. The
configured evaluator is retried at most twice for provider or schema failure; latency, token, and
cost metrics include all attempts. The schema-constrained prompt is recorded as `semantic-v3`.

Evidence: `test_analysis.py`, `test_semantic.py`, worker tests, re-analysis history tests, and a
redacted live OpenRouter development check that returned a valid schema on the configured model.

### 2.6 Trace investigation dashboard

The dashboard renders canonical nested activity, transcript, recording, analysis, errors, evidence,
usage, cost, voice behavior, and outcome provenance. Evidence links select the exact turn/span/event.
Setup and settings now derive a valid authorized project/environment when build-time defaults are
stale, and create keys/integrations in the selected scope. SDK, LiveKit, and LangGraph snippets are
self-contained Python examples.

Evidence: dashboard component tests, `SetupPage.test.tsx`, `SettingsPage.test.tsx`, trace API tests,
frontend production build, and lint.

### 2.7 Vapi

Vapi uses encrypted server-side credentials, live credential/resource validation, assistant
mapping, authenticated durable receipts, asynchronous canonical normalization, deduplication, later
update reconciliation, optional existing-destination forwarding, and dashboard health. Exact zero
cost and token values are preserved rather than replaced by fallback fields.

Evidence: connector setup tests, webhook/normalization fixtures, forwarding tests, zero-value
regression coverage, and a redacted live read-only credential/resource check.

### 2.8 Retell

Retell uses the shared managed-connector boundary with encrypted credentials, agent mapping,
timestamped raw-body HMAC verification, durable receipts, deferred normalization, duplicate/later
delivery reconciliation, forwarding, and setup health.

Evidence: signed webhook tests, controlled full-call fixtures, missing-data tests, and a redacted
live read-only authentication check. The configured account currently exposes no agents, so no
hosted call was attempted; hosted-provider acceptance is outside this phase.

### 2.9 Analytics, costs, and recordings

Overview and comparison calculations execute as bounded database aggregates. Rates use known
outcomes as their denominator and display unknown samples separately. Agent, version, platform,
provider, and model comparisons include representative session IDs. Findings and cohort samples are
bounded. Exact and estimated costs are distinguished, zero-value usage survives normalization, and
recording access remains project/session scoped.

Evidence: `test_analytics.py`, `test_access.py`, connector cost tests, recording lifecycle/playback
tests, and overview UI tests.

## 4. Phase completion-criteria matrix

| # | Required developer outcome | Result | Acceptance evidence |
| ---: | --- | --- | --- |
| 1 | Select project/environment and create an ingest key | Pass | Setup/settings selection tests and role-scoped key API tests. |
| 2 | Add Voker to custom Python or LiveKit quickly | Pass | Public SDK/observer APIs and self-contained onboarding snippets. |
| 3 | Run STT → LLM → tool/MCP → TTS → playback | Pass | SDK and LiveKit full-pipeline fixtures through canonical ingestion. |
| 4 | See correct nesting and identities | Pass | Trace contract tests for parentage, agents, graph nodes, providers, models. |
| 5 | Inspect errors, latency, usage, cost, voice behavior, outcomes | Pass | Trace panels and API projection/aggregate tests. |
| 6 | Open evidence-backed outcome explanations | Pass | Semantic/deterministic findings plus analysis-state UI. |
| 7 | Distinguish certainty and unknowns | Pass | Certainty enums/copy and unknown-safe analytics. |
| 8 | Navigate every finding to evidence | Pass | Same-session evidence validation and trace/transcript navigation tests. |
| 9 | Keep the voice app running if Voker is unavailable | Pass | Bounded exporter outage and adapter fail-open tests. |
| 10 | Connect Vapi or Retell into the canonical experience | Pass | Managed setup, webhook, normalization, and full-call contract fixtures. |
| 11 | Compare performance and open representative sessions | Pass | Evidence-linked comparison API and Overview links. |
| 12 | Use optional scoped recording playback | Pass | Recording state/source validation and authenticated playback tests. |

## 5. Initial-release safeguards

- Reads are organization/project scoped, including duplicate-slug fail-closed behavior.
- Key and integration mutations require owner/admin roles; member denial covers create, update,
  disable, and revoke paths.
- Browser code does not contain ingest/provider secrets, and managed credentials are never returned.
- Live streams, trace lookup, comparison evidence, and recordings remain in their authorized scope.
- Exporter/evaluator content passes through capture controls and redaction.

These are the functional safeguards needed for the initial release. Enterprise identity, advanced
RBAC, compliance programs, and general security hardening are not Phase 02 deliverables.

## 6. Provider and migration verification boundary

Read-only live checks on 2026-09-22 confirmed that the configured Vapi, Retell, LiveKit, and
OpenRouter credentials authenticate without exposing secret values. Vapi returned two selectable
resources, Retell returned zero, LiveKit returned zero active rooms, and OpenRouter returned a
schema-valid semantic result using the configured model after its bounded retry. These checks prove
the live client/authentication boundaries; deterministic fixtures prove call normalization and
reconciliation without mutating hosted agents or placing paid calls.

All five Alembic revisions compile in order for PostgreSQL upgrade and reverse downgrade SQL. The
current audit did not claim SQLite migration compatibility: revision 2 uses PostgreSQL constraint
operations unsupported by SQLite. No schema change was introduced by the audit.

## 7. Explicit exclusions

The following remain intentionally unimplemented as requested, and do not reduce the Phase 02
functional completion score:

- ingestion load or soak campaigns;
- process-restart and network-partition campaigns;
- backup/restore certification;
- large cross-browser E2E matrices;
- formal hosted-provider call acceptance;
- enterprise SSO, advanced RBAC, or compliance certification;
- speculative performance work without an observed functional defect.

## 8. Final quality gate

The authoritative commands are:

```bash
venv/bin/python -m ruff check apps/api packages/python-sdk
venv/bin/python -m mypy apps/api/src packages/python-sdk/src
venv/bin/python -m pytest
pnpm lint:web
pnpm test:web
pnpm build:web
```

All commands pass at the audited commit. ESLint reports four existing non-blocking Fast Refresh
advisories and no errors. See the live tracker for exact test counts and commit identifier.
