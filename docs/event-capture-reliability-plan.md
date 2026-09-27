# Event Capture Reliability Plan

Status: proposed

Scope: LiveKit adapter, Python SDK exporter, ingestion API, PostgreSQL projections,
analysis scheduling, and session UX.

Reference incident:
`2cde5948-0f08-45c5-a0a1-04457fce532e` / `console-f60c5d05`.

## 1. Incident conclusion

The LiveKit observer did not stop producing events after 53 seconds. The terminal
event has sequence `427`, proving that the SDK sequence generator continued after
the last normally persisted event, sequence `117`.

The detailed event stream was lost between SDK production and durable database
persistence:

- The API persisted ordinary events through sequence `117`.
- Sequences `118` through `426` are absent.
- The API log contains PostgreSQL deadlocks, statement timeouts, duplicate-key
  races, and rejected events during the same session.
- The SDK exporter uses a process-memory queue, a 10-second HTTP timeout, one
  retry, and then acknowledges failed queue items locally without durable replay.
- On session shutdown, the SDK only waits a bounded period for the queue.
- `session.ended` is also sent through a separate synchronous delivery path, so
  sequence `427` reached the API even though the normal exporter was backlogged.

This also explains the misleading application state: the early terminal event
marked the session complete and started analysis before the missing sequences had
arrived. Analysis therefore saw an incomplete transcript and no later tool calls
or user frustration.

### Causal chain

```text
LiveKit produced callbacks normally
        |
        v
SDK assigned sequences through 427
        |
        v
Process-memory exporter batched 10 events
        |
        v
API projected every event synchronously before acknowledging the batch
        |
        v
Remote PostgreSQL work exceeded the SDK's 10-second timeout
        |
        v
SDK retried while the original API request was still running
        |
        v
Concurrent requests updated the same turn/run/span rows
        |
        v
Deadlocks, statement timeouts, uniqueness races, and rejected items
        |
        v
SDK exhausted one retry and removed failed items from its memory queue
        |
        v
Sequences 118-426 became unrecoverable
        |
        +--> session.ended used direct delivery and arrived as sequence 427
```

## 2. Reliability contract

The new system must offer **at-least-once delivery with idempotent persistence**.
It must never silently describe an incomplete capture as complete.

The contract is:

1. Every generated event receives a stable `event_id` and monotonically
   increasing session `sequence` before export.
2. An event remains in a durable outbox until the server acknowledges that exact
   `event_id` as persisted or already present.
3. The ingestion response is sent only after raw events are committed, not after
   turns, spans, analysis, or UI projections are built.
4. Duplicate delivery is normal and must never be treated as an error.
5. Projection is asynchronous, idempotent, and ordered per session.
6. `session.ended` means the call ended. It does not mean capture is complete.
7. Capture is complete only when all expected sequence numbers are durably stored.
8. Missing sequences are visible, retried, and recoverable from the SDK outbox or
   provider artifacts.

Absolute losslessness cannot be guaranteed if both the worker and every upstream
recording disappear simultaneously. The practical guarantee is that every event
is persisted, retried, recovered, or explicitly reported as missing.

## 3. Target architecture

```text
LiveKit public callbacks
        |
        v
LiveKitEventAdapter
  normalize + correlate + sequence
        |
        v
DurableEventOutbox (SDK)
  SQLite WAL / persistent append-only spool
        |
        v
EventDeliveryWorker
  batch + retry + ACK + replay
        |
        v
POST /v1/events/batch
        |
        v
RawEventInbox (PostgreSQL)
  INSERT ... ON CONFLICT DO NOTHING
        |
        +------ immediate durable ACK ------> SDK removes ACKed rows
        |
        v
SessionProjectionWorker
  one ordered projector per session
        |
        +--> sessions / turns / agent_runs / spans / tool calls
        |
        v
CompletenessGate
  expected last sequence + missing ranges
        |
        +--> analysis jobs only when complete
        +--> recovery job when incomplete
        v
Dashboard and MCP queries
```

## 4. Deep modules and interfaces

### 4.1 `DurableEventOutbox`

This is the SDK reliability seam. Callers should not know about SQLite, batching,
retry timing, or ACK bookkeeping.

```python
class DurableEventOutbox(Protocol):
    def append(self, event: CanonicalEvent) -> None: ...
    def lease(self, *, limit: int, lease_seconds: float) -> EventBatch: ...
    def acknowledge(self, event_ids: set[str]) -> None: ...
    def retry(self, event_ids: set[str], reason: str) -> None: ...
    def health(self, session_id: str) -> OutboxHealth: ...
```

Required implementation behavior:

- Use SQLite WAL mode or an append-only persistent spool.
- Retain rows across SDK and worker restarts.
- Lease rather than delete before network delivery.
- Delete only server-acknowledged `accepted` or `duplicate` event IDs.
- Apply exponential backoff with jitter and no fixed retry limit.
- Quarantine permanent schema rejections and expose them as capture failures.
- Put a hard disk-size policy in configuration. Reaching the limit must raise a
  visible critical health condition; it must not silently evict recent events.

For an ephemeral container, mount the spool on a persistent volume. If that is
not possible, retain LiveKit recording/session artifacts as the recovery source.

### 4.2 `RawEventInbox`

This is the ingestion durability seam. Its interface accepts validated events and
returns durable per-event acknowledgements.

```python
class RawEventInbox(Protocol):
    def persist(self, context: IngestContext, events: list[CanonicalEvent]) -> BatchAck: ...
```

Its implementation performs a bulk PostgreSQL insert and no projection work.

The response must distinguish:

- `accepted`: newly committed;
- `duplicate`: already committed and safe to remove from the SDK outbox;
- `rejected_permanent`: invalid schema or forbidden payload;
- `retryable`: storage unavailable; retain the whole unacknowledged set.

### 4.3 `SessionProjector`

This module consumes raw events in sequence order and owns all changes to session,
turn, run, span, tool-call, transcript, and usage projections.

```python
class SessionProjector(Protocol):
    def project_available(self, session_key: SessionKey) -> ProjectionResult: ...
```

Only one worker may project a particular session at a time. Parallelism is across
sessions, never within one session.

### 4.4 `CaptureCompleteness`

This module determines whether analysis is safe to run.

```python
class CaptureCompleteness(Protocol):
    def inspect(self, session_key: SessionKey) -> CaptureReport: ...
```

The report contains:

- `highest_seen_sequence`;
- `highest_contiguous_sequence`;
- `expected_last_sequence` from the completion manifest;
- `missing_ranges`;
- raw, projected, rejected, and quarantined counts;
- `capture_state`: `receiving`, `draining`, `complete`, `incomplete`, or
  `recovering`.

## 5. Database changes

Add an immutable `raw_events` table:

```text
id UUID primary key
project_id UUID not null
environment_id UUID not null
external_session_id TEXT not null
event_id TEXT not null
sequence INTEGER not null
event_type TEXT not null
occurred_at TIMESTAMPTZ not null
payload JSONB not null
received_at TIMESTAMPTZ not null
projected_at TIMESTAMPTZ null
projection_attempts INTEGER not null default 0
projection_error TEXT null
```

Constraints and indexes:

- unique `(project_id, event_id)`;
- unique `(project_id, environment_id, external_session_id, sequence)`;
- index unprojected rows by session and sequence;
- index session/event type for reconciliation and debugging.

Add `session_capture_state`:

```text
session_id UUID primary key
highest_seen_sequence INTEGER
highest_contiguous_sequence INTEGER
expected_last_sequence INTEGER null
missing_ranges JSONB
raw_event_count INTEGER
projected_event_count INTEGER
permanent_rejection_count INTEGER
state TEXT
last_received_at TIMESTAMPTZ
completed_at TIMESTAMPTZ null
```

Store tool calls as a dedicated projection or expose a stable projection over tool
spans. Each record needs `call_id`, name, started/ended timestamps, status, input,
output/error, latency, turn, and agent run.

## 6. Protocol changes

### Event batch request

Retain canonical events but add batch metadata:

```json
{
  "schema_version": "1.0",
  "delivery_id": "uuid",
  "events": []
}
```

### Event batch response

```json
{
  "accepted_event_ids": ["evt_1"],
  "duplicate_event_ids": ["evt_2"],
  "permanent_rejections": [],
  "highest_contiguous_sequence": 117,
  "missing_ranges": []
}
```

The SDK must retain any event ID absent from `accepted_event_ids` and
`duplicate_event_ids`.

### Completion manifest

The terminal event includes:

```json
{
  "expected_last_sequence": 427,
  "generated_event_count": 427,
  "final_transcript_items": 12,
  "tool_call_count": 3,
  "outbox_pending_count": 309
}
```

The server may store the call as ended immediately, but it must not schedule final
analysis or show `Capture complete` until sequences `1..427` are present.

## 7. Implementation sequence

### PR 1: Lock down the incident with tests and visibility

- Add a sanitized replay fixture representing the observed `1..117, 427` gap.
- Add an integration test that fails if `session.ended` schedules analysis while
  earlier sequences are missing.
- Add exporter counters: generated, durable, pending, leased, acknowledged,
  retried, permanently rejected, oldest pending age, and disk bytes.
- Log callback exceptions and exporter failures without requiring a debug flag.
- Add a capture-health banner to the session page.
- Stop using `Completed` as a synonym for `Capture complete`.

Exit criteria:

- The fixture deterministically produces `capture_state=incomplete`.
- The dashboard reports missing range `118-426`.
- Analysis is not scheduled for the incomplete fixture.

### PR 2: Make ingestion fast and idempotent

- Add `raw_events` and `session_capture_state` migrations.
- Replace select-then-insert duplicate handling with PostgreSQL
  `INSERT ... ON CONFLICT DO NOTHING`.
- Make `/v1/events/batch` commit raw rows only.
- Return ACKs immediately after commit.
- Remove turn/run/span mutation from the request path.
- Ensure a timed-out/disconnected client request can be retried without creating
  another conflicting projection transaction.

Exit criteria:

- Duplicate concurrent batches return accepted/duplicate results without a
  deadlock or `UniqueViolation`.
- A ten-event batch is durably acknowledged within the agreed ingestion SLO.
- Killing the API after commit but before response is harmless on retry.

### PR 3: Add ordered asynchronous projection

- Insert or mark a unique projection job in the same transaction as raw events.
- Claim sessions using PostgreSQL `FOR UPDATE SKIP LOCKED` or a session advisory
  lock.
- Process each session by sequence; do not project past a known gap.
- Convert projection writes to atomic upserts.
- Mark each raw event projected only after projection commit.
- Retry transient failures; quarantine deterministic bad payloads.

Exit criteria:

- Multiple workers can process different sessions concurrently.
- Two workers cannot mutate the same session concurrently.
- Restarting a worker resumes from the first unprojected sequence.
- Replaying all events produces the same projections.

### PR 4: Replace the SDK memory queue with a durable outbox

- Implement SQLite WAL outbox and delivery leases.
- Append before network delivery.
- Remove fixed retry exhaustion as a deletion condition.
- ACK only exact accepted/duplicate IDs.
- Resume pending delivery when a worker or process restarts.
- Make queue capacity and disk health visible.
- Keep network and disk work off audio-frame processing; only semantic callbacks
  use the outbox.

Exit criteria:

- Force API downtime for five minutes, restart it, and recover every event.
- Kill the agent process with pending events, restart it against the same spool,
  and recover every event.
- Duplicates may occur, but missing sequence count remains zero.

### PR 5: Add completeness gating and recovery

- Add expected sequence/count metadata to `session.ended`.
- Compute missing ranges incrementally.
- Separate `call_status` from `capture_state` and `analysis_status`.
- Queue analysis only when capture is complete or after an explicit partial-data
  override.
- Add a recovery job that requests SDK replay while the outbox is reachable.
- Add a provider-reconciliation adapter for LiveKit recording/session artifacts.
- Mark reconstructed transcript/tool evidence with its recovery source.

Exit criteria:

- An out-of-order terminal event cannot finalize analysis.
- A late missing batch automatically moves a session from `incomplete` to
  `complete` and then schedules analysis once.
- An unrecoverable gap remains visibly incomplete rather than silently complete.

### PR 6: Correct projections and session UX

- Model tool calls separately with count, name, input, output/error, latency, and
  linked turn/span evidence.
- Hide lifecycle-only turns from the transcript while retaining them in trace
  evidence.
- Correlate LiveKit speech handles with provider TTS IDs so generated-but-unused
  speech does not become a false unfinished TTS failure.
- Normalize `appointment_management` or emit a supported specific intent.
- Show source and formula for dead air, interruption, talk-over, and correction
  metrics.
- Deduplicate finding labels such as `Detected condition: Detected condition:`.

Exit criteria:

- The demo transcript matches all final LiveKit transcript items.
- Tool-call count and details match LiveKit.
- Intent is no longer `unknown` for the rescheduling scenario.
- Every metric links to raw evidence and documents its calculation.

## 8. Queue technology decision

Do not use Redis Pub/Sub or an ordinary in-memory Redis list for critical capture.
They do not solve loss before enqueue and can lose data during restart or failover.

Recommended now:

- SDK: SQLite WAL outbox on persistent storage.
- Ingestion source of truth and work queue: PostgreSQL raw inbox plus jobs claimed
  with `FOR UPDATE SKIP LOCKED`.
- Analysis: existing PostgreSQL jobs after completeness gating.

Possible later evolution:

- SQS can wake projection workers at larger scale, but raw PostgreSQL persistence
  remains the source of truth. Use a transactional outbox to avoid a DB/SQS
  dual-write gap.
- Kafka is appropriate only when throughput and replay requirements justify its
  operational cost.
- Redis Streams is acceptable only with AOF persistence, replication, consumer
  groups, and tested recovery. It is not necessary for the current scale.

## 9. Required tests

### Deterministic regression tests

- Replay sequence `1..117, 427`; assert incomplete and no final analysis.
- Deliver `118..426`; assert complete and analysis scheduled exactly once.
- Deliver every event twice; assert one raw row and one projection per event.
- Deliver batches in reverse order; assert ordered final projections.
- Deliver terminal first; assert call ended but capture draining.

### Failure-injection tests

- API timeout after database commit but before HTTP response.
- API unavailable before commit.
- PostgreSQL statement timeout.
- Worker killed during projection transaction.
- SDK process killed with leased events.
- Corrupted local spool row.
- Persistent-volume full condition.
- Handoff between LiveKit agents while events are pending.

### Load tests

- Simulate expected peak concurrent calls and at least 2x projected event rate.
- Measure ingestion ACK latency independently from projection latency.
- Verify no database deadlocks and no missing sequences.
- Verify backlog drains after a controlled API outage.

## 10. Operational SLOs and alerts

Initial targets, to be validated under load:

- Raw ingestion ACK: p95 under 250 ms, p99 under 1 second.
- Silent event loss: zero.
- Duplicate events: allowed and tracked, never user-visible as errors.
- Completed-session sequence gaps: zero; otherwise capture state is incomplete.
- Projection backlog age: p95 under 5 seconds during normal operation.
- Final analysis starts only after capture completeness.

Alert on:

- SDK outbox oldest-event age;
- SDK spool disk usage;
- permanent rejections;
- API retryable error rate;
- missing sequence ranges after terminal receipt;
- projection retry count and backlog age;
- sessions ended but not capture-complete after a defined grace period.

## 11. Rollout

1. Add schema and instrumentation behind feature flags.
2. Dual-write current ingestion and raw inbox for development sessions.
3. Compare event counts, sequence ranges, transcript turns, and tool calls.
4. Enable asynchronous projection for internal demo traffic.
5. Run failure-injection and load gates.
6. Enable durable SDK outbox for the LiveKit demo.
7. Canary a small percentage of production traffic.
8. Make raw inbox/projector the only path after parity is proven.
9. Remove the old synchronous projection path and process-memory-only exporter.

Rollback is safe because the immutable raw inbox remains replayable into either
projection version.

## 12. Definition of done

The work is complete when:

- every generated event is acknowledged or remains durably pending;
- a process restart does not lose pending telemetry;
- duplicate and out-of-order delivery are harmless;
- terminal delivery cannot hide earlier gaps;
- analysis never silently runs on an incomplete session;
- transcript and tool-call projections match source evidence;
- the dashboard displays capture health, missing ranges, recovery status, and
  evidence-linked metrics;
- the exact reference incident is covered by a permanent regression fixture.
