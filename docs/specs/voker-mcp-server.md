# Voker MCP Server for Session Logs and Analytics

## Problem Statement

Voker users can instrument voice agents, send canonical telemetry, inspect sessions in the dashboard, and observe local or MCP tool calls inside a trace. However, they cannot connect an MCP-capable client such as Codex, ChatGPT, Claude, Cursor, or another agent host directly to Voker and query their project data conversationally.

Today, Voker API keys are ingestion credentials. They accept session and event data but do not provide read access to session traces, transcripts, findings, or analytics. Dashboard reads require a browser-authenticated user session, and Voker does not expose a remote MCP endpoint. The repository contains a local demonstration MCP server and MCP observability support, but neither makes Voker itself an MCP server.

As a result, a developer cannot configure Voker once in their preferred MCP host and ask questions such as:

- Which production sessions failed in the last 24 hours?
- Why did this conversation fail?
- Show the transcript and tool errors for a specific session.
- Which agent version has the highest p95 response latency?
- Find calls where an MCP tool failed or timed out.

Voker needs a secure, read-only, project-scoped MCP server that exposes its existing session evidence and analytics through stable tools. The conversational AI host will interpret natural-language requests, select tools, and synthesize answers; Voker will remain the authoritative source of structured, evidence-backed data.

## Solution

Add a production remote MCP server to the Voker API using the MCP Streamable HTTP transport. A Voker project administrator can create a read-scoped MCP access key, copy a project-specific connection configuration, and connect an MCP client to Voker over HTTPS.

The server will expose a deliberately small set of read-only tools for project identity, agents, sessions, transcripts, traces, canonical events, analyses, error search, and project-level analytics. Tool results will reuse Voker's canonical observability vocabulary and existing authorization, filtering, redaction, evidence, and analytics rules.

The first release will provide these tools:

1. `get_project` — return the authenticated project and environment context.
2. `list_agents` — list observable agents and versions within the authenticated scope.
3. `list_sessions` — find sessions using bounded filters and stable pagination.
4. `get_session` — return one session's summary and collection status.
5. `get_session_transcript` — return ordered turns for one session.
6. `get_session_trace` — return the nested agent-run and span timeline, including tool/MCP activity and errors.
7. `get_session_events` — return paginated canonical events for detailed investigation.
8. `get_session_analysis` — return deterministic and semantic findings with resolvable evidence references.
9. `search_errors` — find error occurrences and affected sessions using structured filters.
10. `get_project_overview` — return aggregate volume, outcome, latency, error, and cost summaries for a bounded time range.
11. `compare_agents` — compare agents or agent versions over the same cohort and metric definitions.

The MCP server will never generate unsupported conclusions. It will return canonical facts, existing findings, certainty labels, and evidence identifiers. The connected AI host may summarize that information, but Voker's tool descriptions will instruct it to distinguish observed evidence, deterministic findings, semantic findings, and inference.

Administrators will manage MCP access from project settings. This is a connection-management surface only: it will show the MCP endpoint, create and revoke read-scoped keys, display a secret only once, and provide ready-to-copy configuration examples. Voker will not provide an embedded chat experience; users will talk to their data through whichever MCP-capable host they connect.

## User Stories

1. As a Voker project administrator, I want to create an MCP access key, so that I can connect an approved AI client to my project.
2. As a Voker project administrator, I want MCP keys to be separate from ingestion-only keys, so that granting read access does not silently expand an existing credential's privileges.
3. As a Voker project administrator, I want to choose the environment associated with an MCP key, so that development credentials cannot read production evidence.
4. As a Voker project administrator, I want the MCP key secret shown only once, so that Voker does not retain recoverable plaintext credentials.
5. As a Voker project administrator, I want to label each MCP key, so that I can identify the client or teammate using it.
6. As a Voker project administrator, I want to see a key's prefix, scope, environment, creation time, last-used time, and revocation state, so that I can audit access.
7. As a Voker project administrator, I want to revoke an MCP key immediately, so that a lost or retired credential stops working.
8. As a Voker project administrator, I want copyable connection instructions for common MCP clients, so that setup does not require protocol knowledge or a Voker-hosted chat UI.
9. As an MCP client, I want to authenticate using a standard bearer token over HTTPS, so that I can connect without a custom authentication flow.
10. As an MCP client, I want to discover Voker's tools and their input schemas during initialization, so that I can call them safely.
11. As a developer, I want to confirm which project and environment my connection can access, so that I do not investigate the wrong dataset.
12. As a developer, I want to list sessions from a time window, so that I can investigate recent activity.
13. As a developer, I want to filter sessions by status, outcome, source, agent, agent version, intent, and error presence, so that I can narrow an investigation quickly.
14. As a developer, I want to search by internal session ID, external session ID, or trace ID, so that I can move from another system's identifier to Voker evidence.
15. As a developer, I want session lists to be paginated and consistently ordered, so that large projects return deterministic results.
16. As a developer, I want to see whether a session is live, complete, failed, abandoned, or incomplete, so that I understand the reliability of its evidence.
17. As a developer, I want to fetch a session summary, so that I can understand its identity, timing, agent, outcome, source, usage, cost, and error count.
18. As a developer, I want to fetch the ordered transcript turns, so that I can inspect what the user and agent said.
19. As a developer, I want transcripts to preserve omission, truncation, and redaction indicators, so that hidden content is not mistaken for missing instrumentation.
20. As a developer, I want to fetch the nested trace, so that I can see where latency and failure entered the conversation pipeline.
21. As a developer, I want local tools and MCP tools represented consistently as tool spans, so that investigations do not depend on integration type.
22. As a developer, I want MCP spans to include server, tool name, status, duration, retry count, and safe arguments/results, so that I can diagnose tool behavior.
23. As a developer, I want MCP protocol responses with `isError: true` represented as failures, so that transport success does not hide tool failure.
24. As a developer, I want trace results to preserve parent-child relationships between sessions, agent runs, spans, turns, and events, so that multi-agent behavior remains understandable.
25. As a developer, I want canonical events available with pagination, so that I can perform a detailed audit without receiving an unbounded payload.
26. As a developer, I want to retrieve the existing session analysis, so that I can ask why a conversation succeeded, failed, escalated, or remained uncertain.
27. As a developer, I want each finding to include certainty, severity, and exact evidence references, so that I can verify the conclusion.
28. As a developer, I want evidence references to resolve to session turns, spans, or events returned by other tools, so that an AI host can follow the evidence trail.
29. As a developer, I want analysis state reported as pending, complete, failed, unavailable, or disabled, so that absence of findings is not misrepresented.
30. As a developer, I want to search errors by type, code, stage, tool, MCP server, agent, and time range, so that recurring operational problems are discoverable.
31. As a developer, I want error search results to identify affected sessions and evidence locations, so that I can open representative examples.
32. As an AI/product engineer, I want aggregate outcome and error metrics for a bounded cohort, so that I can evaluate agent quality.
33. As an AI/product engineer, I want latency distributions and percentiles calculated only from comparable available measurements, so that missing data is not treated as zero.
34. As an AI/product engineer, I want usage and estimated cost summaries, so that I can evaluate operational tradeoffs.
35. As an AI/product engineer, I want to compare agents and versions using identical filters, so that regressions are visible.
36. As an AI/product engineer, I want aggregate results to include cohort definitions and sample counts, so that I can judge whether comparisons are meaningful.
37. As an operator, I want read operations constrained to the key's project and environment, so that one credential cannot cross tenant boundaries.
38. As an operator, I want unknown or inaccessible identifiers to return the same not-found behavior, so that resource existence is not leaked across projects.
39. As an operator, I want every MCP tool invocation audited, so that I can investigate access without logging sensitive tool results.
40. As an operator, I want rate limits and bounded result sizes, so that one MCP client cannot exhaust the API or database.
41. As an operator, I want malformed filters rejected with actionable validation errors, so that clients can correct calls safely.
42. As an operator, I want tool failures returned as structured MCP errors, so that clients can distinguish authentication, validation, not-found, rate-limit, and server failures.
43. As a privacy-conscious customer, I want Voker's existing redaction and content-exclusion rules applied to MCP results, so that MCP cannot bypass dashboard privacy controls.
44. As a privacy-conscious customer, I want authorization headers, keys, cookies, and known secret fields removed from all MCP output, so that credentials do not leak into AI-host conversations.
45. As a privacy-conscious customer, I want raw provider credentials, webhook secrets, and recording storage credentials excluded from every MCP tool, so that observability access does not expose operational secrets.
46. As a compliance reviewer, I want MCP access logs to record who or which key accessed which tool and project, so that read access is reviewable.
47. As a compliance reviewer, I want access logs to avoid transcripts, prompts, tool outputs, and credentials, so that auditing does not create a second sensitive-data store.
48. As an MCP client, I want response metadata to state when results were truncated or when more pages exist, so that I do not treat partial evidence as complete.
49. As an MCP client, I want timestamps returned in UTC ISO 8601 format, so that time comparisons are unambiguous.
50. As an MCP client, I want stable identifiers and schema versions in responses, so that integrations remain compatible as Voker evolves.
51. As an MCP client, I want empty cohorts and missing optional fields represented explicitly, so that I do not infer fabricated values.
52. As a developer, I want live sessions queryable as a point-in-time snapshot, so that I can investigate an active call while recognizing that evidence may still arrive.
53. As a developer, I want a connected AI host to answer follow-up questions using its own conversation context, so that Voker does not need to persist a separate MCP chat history.
54. As a Voker maintainer, I want dashboard and MCP reads to use the same project-scoped query services, so that their metrics and evidence do not drift.
55. As a Voker maintainer, I want the MCP layer to remain thin and transport-focused, so that business rules stay reusable and testable.
56. As a Voker maintainer, I want protocol-level integration tests against seeded canonical data, so that compatibility is validated from a client's perspective.
57. As a Voker maintainer, I want the MCP service to fail without affecting telemetry ingestion, so that observability collection remains fail-open and reliable.
58. As a Voker maintainer, I want MCP usage visible in service metrics, so that latency, error rates, authentication failures, and rate-limit events can be operated in production.

## Implementation Decisions

- Voker will act as the MCP server. External clients connect to Voker; this feature does not make the Voker dashboard a generic client for arbitrary third-party MCP servers.
- The first release will use MCP Streamable HTTP over the existing public HTTPS API deployment. The endpoint will be `/mcp`; it will not use local `stdio` transport in production.
- The MCP implementation will use the official MCP SDK supported by the backend language rather than a custom protocol implementation. Initialization, tool discovery, tool calls, protocol errors, and transport behavior must conform to the SDK's supported MCP protocol version.
- The server will be read-only. All advertised tools will have read-only annotations where supported. No session mutation, event ingestion, re-analysis trigger, integration configuration, key management, or provider action will be exposed as an MCP tool.
- Voker will expose tools rather than MCP resources or prompts in the first release. Session and analytics data are dynamic, filtered, and project-scoped, making tools the clearest initial contract.
- Natural-language conversation belongs entirely to the MCP host. Voker will not add a chat interface, chat API, LLM invocation, conversation thread, or message store. It will return structured evidence for the connected host to interpret.
- MCP access will use explicit least-privilege scopes. Existing ingestion keys retain `ingest:write` only and will not automatically gain read access. New MCP keys receive `mcp:read` and cannot submit telemetry unless separately granted a write scope in a future design.
- API-key persistence will be extended to record credential kind/scopes. Secrets remain high-entropy, are stored only as hashes, and are displayed only once. Prefixes must distinguish MCP credentials from ingestion credentials for safe operator recognition.
- MCP keys remain project- and environment-scoped. Every tool derives project and environment identity from the authenticated credential; clients cannot supply a different project or environment in tool arguments.
- Only organization owners and admins can create or revoke MCP keys. Project members may use a key provided to them but cannot mint credentials through the dashboard unless their role permits it.
- Authentication uses `Authorization: Bearer <key>`. Credentials in query strings are forbidden. Missing, malformed, expired, revoked, or incorrectly scoped credentials fail before tool execution.
- Authentication failures return an HTTP authentication error appropriate to the transport. Authenticated tool calls return MCP-compliant structured success or error results.
- Revocation takes effect on the next request. No long-lived server session may continue authorizing calls solely from initialization-time state after its key has been revoked.
- Key `last_used_at` updates must be decoupled from the hot telemetry-ingestion path. MCP access may update usage asynchronously or with bounded write frequency so concurrent calls do not contend on one key row.
- The current dashboard query logic will be extracted into project-scoped read services shared by the dashboard API and MCP tools. MCP handlers must not call dashboard HTTP routes internally or duplicate metric calculations.
- Shared services accept an authorization context containing project and environment identity. They never accept an unrestricted project identifier from MCP input.
- All functional queries enforce project and environment boundaries in the database query. Filtering an already-loaded cross-project result in application memory is not sufficient.
- Session lookup accepts Voker's internal session ID, external session ID, or trace ID through explicitly named inputs. Ambiguous matches return a validation error rather than choosing silently.
- A resource outside the authenticated scope is reported as not found. Responses must not confirm that an inaccessible project, session, agent, span, event, or finding exists.
- `get_project` returns non-sensitive project/environment identity, enabled analysis state, server schema version, and current UTC time. It never returns organization membership, keys, secrets, or provider credentials.
- `list_agents` returns stable agent identity, source, available versions, last observed time, session count for the requested bounded time range, and pagination metadata.
- `list_sessions` supports start/end time, status, outcome, source/platform, agent, version, intent, `has_error`, minimum duration, maximum duration, and identifier search filters. Unsupported free-form SQL-like filters are rejected.
- Time-bounded aggregate tools default to the previous 24 hours and reject ranges longer than 90 days in the first release. Session identity lookups are not subject to the aggregate time-range limit.
- List limits default to 25 and cannot exceed 100. Stable cursor pagination is preferred for MCP contracts even if an existing dashboard route uses offset pagination internally.
- Session ordering defaults to `started_at` descending with a stable ID tie-breaker. Cursor contents are opaque to clients and validated before use.
- `get_session` returns the session summary, agent/version identity, collection status, outcome, usage, estimated cost, voice-behavior summary, error count, finding count, and links between returned identifiers. It does not embed the entire trace.
- `get_session_transcript` returns ordered turns with speaker, start/end timestamps, transcript, and safe attributes. It supports pagination or bounded chunks for long conversations.
- `get_session_trace` returns the nested structure needed to reconstruct session, agent-run, and span relationships. It includes tool/MCP metadata, latency, status, retries, and errors but excludes unbounded raw event payloads.
- `get_session_events` provides canonical events separately with type/status filters and cursor pagination. Event payloads pass through the same output sanitation policy as dashboard evidence.
- `get_session_analysis` returns the latest authoritative deterministic and semantic analysis states, findings, certainty, severity, rule/prompt versions, and validated evidence references. It never starts or retries an analysis.
- `search_errors` uses structured indexed filters and returns error summaries, counts, session identifiers, evidence identifiers, and safe messages. It does not implement arbitrary full-database text search in the first release.
- `get_project_overview` reuses canonical dashboard analytics definitions for volume, outcomes, error rate, stage latency, usage, estimated cost, and voice behavior. Every result includes cohort filters, sample counts, and missing-data semantics.
- `compare_agents` compares at least two agent or agent-version cohorts using the same project, environment, time range, and metric definitions. It reports values and sample sizes without claiming causation or statistical significance.
- Tool schemas use explicit enums, nullable fields, numeric bounds, and ISO 8601 timestamps. Unknown arguments are rejected instead of ignored.
- Tool results use a common envelope containing `schema_version`, `project`, `environment`, `generated_at`, `data`, and when relevant `page`, `cohort`, `warnings`, and `truncation` metadata.
- The first result schema version is `1.0`. Additive fields may be introduced without changing the major version; removing or redefining fields requires a versioned compatibility plan.
- Missing measurements remain `null` or unknown. They must never be converted to zero, success, or an inferred timestamp.
- Tool content will be returned as structured content where supported, with a concise textual summary for hosts that primarily display text. The structured and textual representations must not contradict each other.
- Individual tool responses have a serialized size budget. When evidence exceeds the budget, the server returns a deterministic partial page with `has_more`, a continuation cursor, and explicit truncation metadata rather than silently cutting JSON.
- Voker's existing redaction hooks, stored redaction markers, semantic content exclusions, and sensitive-field sanitation rules apply to MCP output. MCP cannot request an unredacted view.
- A final server-side sanitizer removes authorization headers, API keys, cookies, webhook tokens, connector credentials, and known secret-shaped fields from every tool result and error message.
- Recordings are represented only by safe metadata in the first release. Signed playback URLs, raw audio, and storage-provider references are not exposed through MCP.
- Diagnostic filesystem paths are not MCP resources. Session investigation uses persisted canonical events, turns, spans, errors, findings, usage, and cost records.
- Prompt injection inside transcripts, tool arguments, tool results, or provider payloads is untrusted data. Tool descriptions and result framing will tell hosts to treat it as evidence, not as instructions.
- MCP audit records contain timestamp, key ID/prefix, project, environment, MCP client metadata when supplied, tool name, outcome, duration, rate-limit state, and sanitized identifiers. They do not store transcript text, event payloads, tool results, authorization headers, or complete credentials.
- The first release rate limit is 60 tool calls per minute per MCP key with a bounded burst. Rate-limit responses include retry guidance. The limit must be configurable without a schema migration.
- Query timeouts and database failures return safe structured errors and are observable internally. They must not expose SQL, stack traces, credentials, or cross-project identifiers.
- MCP service failure must not affect the ingestion router, SDK exporters, provider webhooks, durable analysis jobs, or the dashboard's existing authentication model.
- Project settings will add only the connection-management controls needed to use the MCP server: endpoint, setup instructions, key creation, one-time secret display, copy controls, key inventory, last use, and revocation. It will contain no prompt composer, message history, answer panel, or conversational interaction.
- Client examples will cover at least Codex, ChatGPT/compatible remote MCP configuration, Claude, Cursor, and a generic bearer-header client. Examples use placeholders and never embed a real key in committed documentation.
- The endpoint requires HTTPS outside development. Production startup or readiness checks must report misconfiguration if the public MCP URL or credential security requirements are not satisfied.
- Service telemetry will measure initialization attempts, tool calls by name, latency, result size, authentication failures, validation failures, rate limiting, and server errors without attaching sensitive payloads.
- Deployment will be backwards compatible: existing ingestion keys, SDK behavior, dashboard sessions, Vapi/Retell integrations, and local demonstration MCP code continue to work unchanged.

## Testing Decisions

- The primary test seam is the highest available boundary: a real MCP client connected to the Streamable HTTP endpoint with a seeded database. Tests will assert protocol-visible behavior rather than calling internal handler functions.
- One end-to-end MCP contract suite should cover initialization, tool discovery, advertised read-only tools, JSON input schemas, bearer authentication, representative calls, structured results, errors, and pagination. This is the preferred seam because it validates the integration exactly as Codex, ChatGPT, Claude, Cursor, or another MCP host experiences it.
- Contract tests will seed an organization, project, two environments, users with different roles, scoped keys, agents, versions, sessions, turns, nested spans, canonical events, MCP tool errors, analyses, findings, and evidence. Assertions will use canonical identifiers and external behavior only.
- Authentication tests will cover missing tokens, malformed bearer headers, unknown keys, wrong scopes, expired keys, revoked keys, immediate post-revocation denial, and valid `mcp:read` access.
- Authorization tests will create two projects and two environments with intentionally similar identifiers. Every session and analytics tool must prove that cross-project and cross-environment data is neither returned nor acknowledged.
- Key-management API tests will verify owner/admin creation and revocation, member denial, one-time secret display, hashed persistence, scope reporting, prefix reporting, environment binding, and backwards-compatible ingestion-key defaults.
- Tool-discovery tests will snapshot only the public tool names, descriptions, annotations, and input schemas. They will not snapshot SDK-generated transport noise or internal implementation details.
- `list_sessions` tests will cover every supported filter, combined filters, empty results, deterministic ordering, default limit, maximum limit, cursor continuation, invalid cursor, invalid time range, and live-session snapshots.
- Session-lookup tests will cover internal ID, external ID, trace ID, ambiguity, invalid identifier format, missing session, and out-of-scope session behavior.
- Transcript tests will verify turn ordering, pagination, speaker identity, nullable content, omitted content, truncation markers, redaction markers, and protection against secret-shaped attributes.
- Trace tests will verify nested agent runs and spans, parent-child identity, stage timing, local tool calls, MCP server/tool metadata, retries, timeout/cancelled states, exceptions, and protocol-level `isError` failures.
- Event tests will verify canonical ordering, event-type/status filtering, stable pagination, bounded payloads, and sanitation of nested sensitive fields.
- Analysis tests will cover disabled, pending, complete, failed, and unavailable analysis states; deterministic and semantic findings; certainty labels; schema/prompt versions; and evidence references that resolve only within the same session.
- Error-search tests will cover type, code, stage, tool, MCP server, agent, and time filters; aggregation counts; representative session references; pagination; and safe error messages.
- Analytics tests will reuse the repository's prior art for latency, cost, outcome, provider, agent, and version calculations. They will assert identical results between the dashboard-facing shared service and MCP-facing output for the same cohort.
- Missing-data tests will verify that absent timings, usage, costs, outcomes, and analysis are returned as null/unknown and excluded from denominators where the canonical metric requires it.
- Response-budget tests will seed oversized transcripts, events, arguments, results, and error messages. They will assert deterministic pagination/truncation metadata and valid JSON rather than silent clipping.
- Redaction tests will inject authorization headers, bearer tokens, Voker key patterns, cookies, provider credentials, webhook tokens, nested secret fields, and prompt-injection text. No tool result, text summary, protocol error, audit record, or application log may expose the secret values.
- Rate-limit tests will verify the configured per-key limit, key isolation, retry metadata, and recovery after the window while avoiding timing-sensitive sleeps through a controllable clock/rate-limit store.
- Audit tests will verify that successful, failed, rejected, and rate-limited calls record safe metadata while never recording input/output content or full credentials.
- Reliability tests will force MCP query and transport failures and verify that ingestion, webhook receipt, session creation, and dashboard health remain available.
- UI tests will cover creating an MCP key, choosing an environment, one-time secret presentation, copying configuration, loading key metadata, revoking a key, permission-restricted controls, accessible labels, keyboard interaction, and responsive layout.
- Existing repository patterns should be reused: FastAPI `TestClient` with dependency overrides for HTTP boundaries, isolated SQLite/PostgreSQL-compatible model fixtures for project scoping, canonical event fixtures for trace behavior, and frontend Testing Library tests for settings flows.
- Tests should avoid asserting private function calls, ORM query shapes, MCP SDK internals, or exact prose beyond stable public error codes and contracts.
- A production-readiness smoke test will connect a standard MCP inspector/client to a deployed HTTPS endpoint, initialize, list tools, authenticate with a temporary key, query a seeded session, revoke the key, and confirm the next call is denied.

## Out of Scope

- Allowing Voker users to register arbitrary external MCP servers for Voker to consume.
- Write or destructive MCP tools, including ending sessions, changing outcomes, modifying agents, configuring providers, retrying analysis, creating API keys, or deleting data.
- Any conversational UI inside Voker, including a prompt composer, message thread, answer panel, suggested questions, or stored chat history.
- Server-side conversation memory or storage of the user's MCP-host chat history.
- Having Voker's MCP server invoke an LLM to compose natural-language answers.
- OAuth, dynamic client registration, enterprise identity federation, or delegated user authorization; the first release uses scoped project API keys.
- Organization-wide or cross-project analytics from one credential.
- Access to raw recordings, signed playback URLs, raw diagnostic files, database queries, SQL, provider credentials, webhook secrets, or other operational secrets.
- Real-time subscription or push streaming of newly arriving events. Live sessions are available as point-in-time snapshots.
- MCP prompts, static MCP resources, custom MCP Apps UI widgets, or client-specific rich interfaces.
- Statistical causality claims, automated remediation, alert creation, or production actions based on findings.
- Changing the existing local demonstration MCP server or the ability to observe MCP calls made by customer agents.

## Further Notes

- The repository already models the required canonical evidence: project, environment, session, turn, agent run, span, event, error, finding, evidence reference, usage, cost, and outcome. The main architectural work is a secure read credential, shared project-scoped query layer, MCP transport adapter, and setup experience—not a second observability model.
- The existing roadmap identifies a Voker MCP server for querying traces and analytics as a future capability. This specification promotes that capability into an implementation-ready release while preserving current MVP principles: one canonical trace, evidence before conclusions, project-scoped ownership, privacy by default, and fail-open telemetry collection.
- “Talk to Voker” means connecting Voker's MCP server to an external MCP-capable AI host. Voker provides authoritative tools and evidence only; the external host supplies the chat UI, model inference, and conversational continuity.
- The recommended implementation sequence is: scoped credentials and migrations; shared read/query services; MCP authentication and transport; session/evidence tools; aggregate tools; audit/rate limiting/observability; settings UI and documentation; deployed-client smoke testing.
- GitHub issue publication requires an authenticated project-tracker session. The specification is complete and can be published with the single `ready-for-agent` label once repository authentication is restored.
