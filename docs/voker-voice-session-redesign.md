# Voker Voice: capture repair and session-investigation redesign

## Why the supplied call failed

**Observed session:** `422bcca9-6801-49fd-b81d-8d8e08d6b087` (`console-41cee729`).

The call itself completed in LiveKit, but Voker did not durably receive the full evidence stream. This was not a presentation-only issue.

| Evidence | What it proves | Repair |
| --- | --- | --- |
| SDK log has 657 emitted events; Voker accepted only 135 | Events were lost after emission, before persistence. | Stop emitting high-frequency VAD/turn-detector samples, preserve the actual voice events, and drain after the LiveKit job ends. |
| 523 `event_rejected_before_persistence` entries | The ingestion API rejected real event batches. | Remove per-batch API-key writes that locked a shared database row. |
| `UniqueViolation: uq_session_external` during concurrent replay | Concurrent first batches raced to create the same session. | Coordinate only first-session materialization, then use row-level metadata merges so delayed batches cannot erase a later intent projection. |
| LiveKit reported a 15.034 second event-loop block at close | The close callback made synchronous HTTP requests. | Queue the terminal event, then use the documented job shutdown callback to drain the exporter after the media pipeline closes. |
| Final agent sentence appeared as a user turn | Assistant messages reused the active customer turn id. | Give each assistant message its own agent transcript turn and explicit speaker metadata. |

The first two repairs were verified against a real local API process. Four simultaneous first events for one new session now each return `200 / accepted=1 / rejected=0`.

## Product principles

1. **One investigation surface.** Intent, resolution, transcript, interruptions, latency, tools, and raw evidence belong to a session—not a separate intent destination.
2. **A call is a story, not a rainbow bar.** Render a labelled lane per speaker and overlay evidence markers; color supplements text, never carries meaning alone.
3. **Evidence before diagnosis.** Every finding must link to its specific event/span/turn and state whether the telemetry is complete.
4. **Unknown is honest.** Never label an outcome, transcript, recording, or metric as present unless it was captured.
5. **Dense but calm.** Preserve observability detail behind progressive disclosure, with a clear primary diagnosis and a compact triage queue.

## Visual direction

Reference board: [generated session-design concept](/Users/h.benterprise/.codex/generated_images/01a0d909-fcfc-7343-b3db-39167afb8aaf/exec-7fef7e10-3815-4c95-955b-531ebf9c53f5.png).

This is an original visual direction board, not a production screen or a copy of Tuner. The implementation takes the useful part of the reference—high signal hierarchy and compact evidence navigation—while using Voker’s own content model.

- Canvas: warm near-white with ink/slate text and quiet borders.
- Semantics: emerald = resolved/captured; amber = attention/partial; rose = error/true interruption; indigo = neutral agent/system evidence; all statuses also carry icons and text.
- Typography: Inter for dense operational reading; monospace only for IDs, timings, and trace fields.
- Layout: 12-column desktop grid, a single readable content column on mobile, no decorative gradients or glass effects.
- Motion: only 150–200ms focus/hover transitions; no movement that obscures timestamps or evidence.

## Session detail information architecture

```text
Breadcrumb: Sessions / console-41cee729                        [Share]

Session header  status  intent + confidence  resolution  duration  errors
Collection rail complete / partial / live + last received event + diagnostic log

Call story
  Customer lane       ███████         ███
  Agent lane                  ████          ███████
  Dead-air lane                     ░░
  Marker rail                   ▲ tool   ! interruption

Primary tabs: Transcript | Analysis | Evidence | Playback (only when a recording exists)
  Transcript: ordered speaker cards with tool/result and intent/resolution annotations
  Analysis: one key takeaway + small issue list, each with evidence links
  Evidence: filters, event count, spans, raw payload disclosure
```

### Session header contract

- **Intent:** `appointment_management` with confidence and source, otherwise `Intent not observed`.
- **Resolution:** `Resolved`, `Escalated`, `Abandoned`, `Unknown`, or error state; show its provenance.
- **Collection:** `Complete`, `Receiving`, or `Partial`. A completed call with no terminal telemetry is explicitly partial.
- **Voice behavior:** compact count chips for interruptions and dead air. Clicking one filters/highlights the corresponding timeline evidence.

### Timeline contract

The current single bar visually turns long intervals into unexplained “dead air.” The replacement uses semantic rows:

| Lane / marker | Source events | Treatment |
| --- | --- | --- |
| Customer | user `turn.started`/`turn.completed`, STT final | green row, labelled transcript anchor |
| Agent | assistant message/agent turn, playback | indigo row, labelled transcript anchor |
| Dead air | emitted `voice.dead_air` or a qualified gap between resolved activities | amber hatched segment with duration label |
| Interruption | `voice.interruption`, talk-over, false interruption | rose marker with the exact classification |
| Tool / handoff | tool/agent handoff events | neutral vertical evidence marker |

An inferred gap must say **Observed gap**, while an explicit event says **Captured dead air**. This prevents the UI from pretending it knows more than the stream contains.

## Data and telemetry work

### Canonical event set (must persist)

- Lifecycle: `session.started`, `session.ended`, `agent.started`, `agent.completed`, `agent.handoff`.
- Conversation: user and assistant message events, user and agent turns, STT final/completed, playback started/completed/interrupted.
- Operations: LLM/STT/TTS start, first token/audio, completion/cancellation/error; tools start/completion/error.
- Voice quality: interruption, false interruption, overlap/talk-over, explicit dead air, transcription timeout.
- Business state: `intent.detected`, `outcome.recorded`, with source and confidence/provenance.
- Final accounting: one session usage snapshot plus discrete provider usage attached to operational spans.

### Explicitly excluded from the call story

VAD, turn-detector, and speaking-rate samples are internal high-frequency diagnostics. They may be sampled separately in a future debug export but must not consume the delivery budget for a normal session.

### Intent and resolution lifecycle

1. Router tool recognizes the caller’s route and emits `intent.detected`.
2. Ingestion writes `intent`, `intent_confidence`, and `intent_source` into session metadata.
3. A resolving tool emits `outcome.recorded` as `resolved`; a policy/supervisor/ticket path emits `escalated`.
4. Sessions list and session header read this state directly. The standalone Intent route is removed/redirected; overview can retain aggregate intent insights that link back to session rows.

## Implementation sequence

1. **Telemetry reliability (completed in this change):** remove API-key hot-row updates, reset failed database transactions, serialize local write batches, drain after LiveKit job shutdown, make transcript speakers distinct, and reduce non-actionable metrics.
2. **Domain projection:** expose intent/confidence/source in `session_summary`, persist explicit `intent.detected`, and show intent + resolution in the session table and header.
3. **Reusable UI primitives:** add shadcn `Table`, use existing `Card`, `Badge`, `Tabs`, `Alert`, `Tooltip`, `Select`, `Sheet`, and `Skeleton`; compose them with Tailwind utilities rather than new page-scoped CSS.
4. **Session detail redesign:** replace the single visual bar with the multi-lane call story; transcript becomes the default tab when no recording exists; analysis collapses duplicate condition cards into an ordered evidence queue.
5. **Triage list redesign:** searchable, keyboard-operable table with status, intent, resolution, duration, quality signals, and collection health. Table rows link to the exact investigation.
6. **Navigation cleanup:** remove the separate Intents sidebar entry and redirect legacy `/intents` links to filtered sessions or overview intent aggregates.
7. **Responsive/accessibility QA:** check 375px, 768px, 1024px, 1440px; tab/arrow/enter navigation; visible focus; 4.5:1 text contrast; no color-only signal; reduced-motion behavior.

## Fixture plan and acceptance gates

| Fixture | Captured facts | Product assertion |
| --- | --- | --- |
| Resolved reschedule | routing intent, check-slot, reschedule, outcome resolved, terminal event | Intent and resolution appear on session row/header; all tools and both speakers appear. |
| Calendar timeout | intent, tool error, no false resolved outcome | Error links to tool span; resolution is `Unknown` or `Escalated`, never success. |
| Billing policy escalation | billing intent, refund policy error, escalated outcome | User sees policy escalation and exact evidence. |
| Support ticket | support intent, ticket tool, escalated outcome | Ticket handoff is visible in transcript and evidence. |
| True interruption | playback plus user speech overlap and interruption event | Rose marker identifies true interruption and links to it. |
| False interruption | agent false-interruption event/resume | Marked separately; does not inflate true interruption count. |
| Captured dead air | explicit dead-air event with duration | Amber hatched lane contains duration and evidence link. |
| Transcript delay | delayed STT final after commitment | Captured text remains in transcript; collection health is still clear. |
| Recording unavailable | no recording asset, full trace present | Default Transcript tab; no misleading empty playback panel. |
| Concurrent delivery | simultaneous first and terminal batches | No rejected events; exactly one session; all expected event IDs persist. |

Release gate for each fixture: persisted event IDs equal expected IDs; session terminal status/outcome matches the canonical events; transcript speaker matches the source; all issue cards navigate to an existing evidence record; no missing recording is presented as a player.
