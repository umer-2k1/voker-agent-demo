import { useEffect, useRef, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { SettingsPage } from "@/pages/SettingsPage";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001";
const projectSlug = import.meta.env.VITE_PROJECT_SLUG ?? "voker-voice";
const ingestKey = import.meta.env.VITE_INGEST_KEY as string | undefined;

type Overview = {
  project: { name: string; slug: string };
  metrics: {
    total_sessions: number;
    active_sessions: number;
    error_count: number;
    average_span_duration_ms: number | null;
  };
};
type Analytics = {
  session_count: number;
  completed_session_count: number;
  outcomes: Record<string, number>;
  sources: Record<string, number>;
  cost: { amount_micros: number | null; currency: string | null; record_count: number };
  voice_impact_cohorts: Record<
    string,
    { sample_size: number; resolved: number; resolution_rate: number } | null
  >;
  latency: Record<
    string,
    { sample_size: number; p50_ms: number; p95_ms: number; max_ms: number } | null
  >;
};
type VoiceSession = {
  id: string;
  external_session_id: string;
  status: string;
  source: string;
  started_at: string;
  error_count: number;
  event_count: number;
};
type Trace = {
  session: VoiceSession;
  events: Array<{
    id: string;
    event_type: string;
    status: string;
    occurred_at: string;
    duration_ms: number | null;
    payload: Record<string, unknown>;
  }>;
  turns: Array<{
    id: string;
    external_turn_id: string;
    sequence: number;
    speaker: string;
    started_at: string;
    transcript: string | null;
  }>;
  errors: Array<{ id: string; type: string; message: string }>;
  findings: Array<{
    id: string;
    certainty: string;
    severity: string | null;
    statement: string;
  }>;
  analysis_runs: Array<{
    id: string;
    status: string;
    prompt_version: string;
    model: string | null;
  }>;
  recordings: Array<{
    id: string;
    source: string;
    duration_ms: number | null;
    media_type: string | null;
    status: string;
  }>;
};

type SessionPage = { offset: number; limit: number; total: number };

function formatLatency(value: number | null) {
  return value === null
    ? "—"
    : value >= 1000
      ? `${(value / 1000).toFixed(2)} s`
      : `${Math.round(value)} ms`;
}
function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}
function formatCost(value: number | null, currency: string | null) {
  return value === null ? "Unknown" : `${currency ?? "USD"} ${(value / 1_000_000).toFixed(4)}`;
}
function formatRate(value: number) {
  return `${Math.round(value * 100)}%`;
}
function turnOffsetSeconds(turn: Trace["turns"][number], session: VoiceSession) {
  return Math.max(0, (new Date(turn.started_at).getTime() - new Date(session.started_at).getTime()) / 1000);
}

function DashboardPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [sessions, setSessions] = useState<VoiceSession[]>([]);
  const [page, setPage] = useState<SessionPage>({ offset: 0, limit: 30, total: 0 });
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [search, setSearch] = useState("");
  const [showRaw, setShowRaw] = useState(false);
  const [traceFilter, setTraceFilter] = useState<"all" | "agent" | "handoff">("all");
  const [activeRecordingId, setActiveRecordingId] = useState<string | null>(null);
  const [playheadSeconds, setPlayheadSeconds] = useState(0);
  const audioRef = useRef<HTMLAudioElement>(null);

  async function loadTrace(sessionId: string, active = true) {
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/projects/${projectSlug}/sessions/${sessionId}`,
      );
      if (!response.ok) throw new Error("Unable to load this session trace.");
      const payload = (await response.json()) as Trace;
      if (active) {
        setTrace(payload);
        setActiveRecordingId((current) =>
          payload.recordings.some((recording) => recording.id === current && recording.status === "available")
            ? current
            : (payload.recordings.find((recording) => recording.status === "available")?.id ?? null),
        );
        setPlayheadSeconds(0);
      }
    } catch (caught) {
      if (active)
        setError(
          caught instanceof Error
            ? caught.message
            : "Unable to load session trace.",
        );
    }
  }

  async function requestReanalysis() {
    if (!trace) return;
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/projects/${projectSlug}/sessions/${trace.session.id}/analysis`,
        { method: "POST" },
      );
      if (!response.ok) throw new Error("Unable to queue re-analysis.");
      await loadTrace(trace.session.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to queue re-analysis.");
    }
  }

  async function loadSessions(offset = 0, active = true) {
    const query = new URLSearchParams({ limit: "30", offset: String(offset) });
    if (statusFilter) query.set("status", statusFilter);
    if (sourceFilter) query.set("source", sourceFilter);
    if (search.trim()) query.set("search", search.trim());
    const response = await fetch(
      `${apiBaseUrl}/api/projects/${projectSlug}/sessions?${query}`,
    );
    if (!response.ok) throw new Error("Unable to load captured sessions.");
    const payload = (await response.json()) as { items: VoiceSession[]; page: SessionPage };
    if (!active) return payload;
    setSessions(payload.items);
    setPage(payload.page);
    return payload;
  }

  useEffect(() => {
    let active = true;
    async function loadDashboard() {
      try {
        const [overviewResponse, analyticsResponse, nextSessions] = await Promise.all([
          fetch(`${apiBaseUrl}/api/projects/${projectSlug}/overview`),
          fetch(`${apiBaseUrl}/api/projects/${projectSlug}/analytics/overview`),
          loadSessions(0, active),
        ]);
        if (!overviewResponse.ok || !analyticsResponse.ok)
          throw new Error("Unable to load observability data.");
        const nextOverview = (await overviewResponse.json()) as Overview;
        const nextAnalytics = (await analyticsResponse.json()) as Analytics;
        if (!active) return;
        setOverview(nextOverview);
        setAnalytics(nextAnalytics);
        if (nextSessions.items[0])
          await loadTrace(nextSessions.items[0].id, active);
      } catch (caught) {
        if (active)
          setError(
            caught instanceof Error
              ? caught.message
              : "Unable to load dashboard.",
          );
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadDashboard();
    return () => {
      active = false;
    };
  }, [statusFilter, sourceFilter, search]);

  useEffect(() => {
    if (!trace || !ingestKey || trace.session.status !== "in_progress") return;
    const liveSession = trace.session;
    const controller = new AbortController();
    async function stream() {
      try {
        const response = await fetch(
          `${apiBaseUrl}/v1/live/sessions/${encodeURIComponent(liveSession.external_session_id)}`,
          { headers: { Authorization: `Bearer ${ingestKey}` }, signal: controller.signal },
        );
        if (!response.ok || !response.body) return;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        while (!controller.signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;
          if (decoder.decode(value).includes("event: trace")) await loadTrace(liveSession.id);
        }
      } catch (caught) {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) return;
      }
    }
    void stream();
    return () => controller.abort();
  }, [trace?.session.id, trace?.session.status]);

  const visibleEvents = trace?.events.filter((event) => {
    if (traceFilter === "all") return true;
    if (traceFilter === "handoff") return event.event_type === "agent.handoff";
    return event.event_type.startsWith("agent.") || event.event_type.startsWith("graph.");
  });
  const activeRecording = trace?.recordings.find((recording) => recording.id === activeRecordingId);

  function seekToTurn(turn: Trace["turns"][number]) {
    if (!trace || !audioRef.current || !activeRecording) return;
    const offset = turnOffsetSeconds(turn, trace.session);
    audioRef.current.currentTime = offset;
    setPlayheadSeconds(offset);
    void audioRef.current.play();
  }


  return (
    <main className="product-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">V</span>
          <span>Voker</span>
        </div>
        <p className="workspace">VOICE INTELLIGENCE</p>
        <nav aria-label="Primary navigation">
          <a className="nav-item active" href="#overview">
            Overview
          </a>
          <a className="nav-item" href="#sessions">
            Sessions
          </a>
          <a className="nav-item" href="#trace">
            Trace explorer
          </a>
          <a className="nav-item" href="#insights">
            Intelligence
          </a>
        </nav>
        <div className="sidebar-foot">
          {overview?.project.name ?? "Voker Voice"}
          <br />
          <span>Development</span>
        </div>
      </aside>
      <section className="content" id="overview">
        <header className="page-header">
          <div>
            <p className="eyebrow">Voice-agent observability</p>
            <h1>Voice-agent intelligence, built on trustworthy traces.</h1>
          </div>
          <Badge className="live-indicator">
            <i /> Live data
          </Badge>
        </header>
        {error ? (
          <div className="connection-error" role="alert">
            {error} Start the API at <code>127.0.0.1:8001</code> and refresh.
          </div>
        ) : null}
        <section className="metric-grid" aria-label="Project metrics">
          <Metric
            label="Sessions captured"
            value={overview?.metrics.total_sessions ?? "—"}
          />
          <Metric
            label="Live sessions"
            value={overview?.metrics.active_sessions ?? "—"}
          />
          <Metric
            label="Errors observed"
            value={overview?.metrics.error_count ?? "—"}
            danger={(overview?.metrics.error_count ?? 0) > 0}
          />
          <Metric
            label="Average span latency"
            value={formatLatency(
              overview?.metrics.average_span_duration_ms ?? null,
            )}
          />
          <Metric
            label="Tracked cost"
            value={formatCost(analytics?.cost.amount_micros ?? null, analytics?.cost.currency ?? null)}
          />
        </section>
        <section className="insight-banner" id="insights">
          <div>
            <p className="eyebrow">Intelligence layer</p>
            <h2>Ask why a conversation failed—with evidence.</h2>
            <p>
              Deterministic signals are recorded immediately. After a session
              ends, analysis findings are attached to the exact trace events
              that support them.
            </p>
          </div>
          <span>{trace?.findings.length ?? 0} evidence-backed findings</span>
        </section>
        <section className="cohort-grid" aria-label="Voice Impact cohorts">
          <CohortCard
            label="High interruptions"
            cohort={analytics?.voice_impact_cohorts.high_interruption ?? null}
          />
          <CohortCard
            label="Normal interruptions"
            cohort={analytics?.voice_impact_cohorts.normal_interruption ?? null}
          />
          <CohortCard label="Slow STT" cohort={analytics?.voice_impact_cohorts.slow_stt ?? null} />
          <CohortCard label="Fast STT" cohort={analytics?.voice_impact_cohorts.fast_stt ?? null} />
        </section>
        <section className="cohort-grid" aria-label="Stage latency percentiles">
          <LatencyCard label="STT latency" value={analytics?.latency.stt ?? null} />
          <LatencyCard label="LLM latency" value={analytics?.latency.llm ?? null} />
          <LatencyCard label="Tool latency" value={analytics?.latency.tool ?? null} />
          <LatencyCard label="TTS latency" value={analytics?.latency.tts ?? null} />
        </section>
        <section className="workspace-grid">
          <Card className="panel sessions-panel" id="sessions">
            <CardHeader className="panel-heading">
              <div>
                <p className="eyebrow">Recent activity</p>
                <h2>Captured sessions</h2>
              </div>
              <span>{page.total} captured</span>
            </CardHeader>
            {loading ? (
              <p className="empty-state">Loading persisted sessions…</p>
            ) : null}
            {!loading && !sessions.length ? (
              <p className="empty-state">
                No sessions yet. Connect the Python SDK or send canonical events
                to begin.
              </p>
            ) : null}
            <div className="session-filters">
              <input aria-label="Search sessions" placeholder="Search session ID" value={search} onChange={(event) => setSearch(event.target.value)} />
              <select aria-label="Filter by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">All statuses</option><option value="in_progress">In progress</option><option value="completed">Completed</option><option value="failed">Failed</option></select>
              <input aria-label="Filter by source" placeholder="Source" value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)} />
            </div>
            <div className="session-list">
              {sessions.map((session) => (
                <button
                  key={session.id}
                  className={`session-row ${trace?.session.id === session.id ? "selected" : ""}`}
                  onClick={() => void loadTrace(session.id)}
                >
                  <span
                    className={`status-dot ${session.error_count ? "error" : session.status}`}
                  />
                  <span className="session-name">
                    {session.external_session_id}
                    <small>
                      {session.source} · {formatDate(session.started_at)}
                    </small>
                  </span>
                  <span className="session-events">
                    {session.event_count} events
                    <small>
                      {session.error_count
                        ? `${session.error_count} errors`
                        : session.status}
                    </small>
                  </span>
                </button>
              ))}
            </div>
            {page.total > page.limit ? <div className="pagination"><button disabled={page.offset === 0} onClick={() => void loadSessions(Math.max(0, page.offset - page.limit))}>Previous</button><span>{page.offset + 1}–{Math.min(page.offset + page.limit, page.total)} of {page.total}</span><button disabled={page.offset + page.limit >= page.total} onClick={() => void loadSessions(page.offset + page.limit)}>Next</button></div> : null}
          </Card>
          <Card className="panel trace-panel" id="trace">
            <CardHeader className="panel-heading">
              <div>
                <p className="eyebrow">Complete conversation trace</p>
                <h2>
                  {trace
                    ? trace.session.external_session_id
                    : "Select a session"}
                </h2>
              </div>
              <span>{trace?.events.length ?? 0} events</span>
            </CardHeader>
            {!trace ? (
              <p className="empty-state">
                Choose a persisted session to inspect its timeline.
              </p>
            ) : (
              <>
                <section className="transcript-panel" aria-label="Transcript">
                  <p className="eyebrow">Transcript</p>
                  {activeRecording ? (
                    <div className="recording-player">
                      <div>
                        <b>Call recording</b>
                        <small>{activeRecording.source} · {formatLatency(activeRecording.duration_ms)}</small>
                      </div>
                      <audio
                        controls
                        onTimeUpdate={(event) => setPlayheadSeconds(event.currentTarget.currentTime)}
                        preload="metadata"
                        ref={audioRef}
                        src={`${apiBaseUrl}/api/projects/${projectSlug}/sessions/${trace.session.id}/recordings/${activeRecording.id}/playback`}
                      />
                    </div>
                  ) : trace.recordings.length ? (
                    <p className="analysis-pending">Recording {trace.recordings[0].status}; playback is unavailable.</p>
                  ) : null}
                  {trace.turns.length ? trace.turns.map((turn, index) => {
                    const offset = turnOffsetSeconds(turn, trace.session);
                    const nextTurn = trace.turns[index + 1];
                    const isActive = activeRecording && playheadSeconds >= offset && (!nextTurn || playheadSeconds < turnOffsetSeconds(nextTurn, trace.session));
                    return <button className={`transcript-turn ${isActive ? "playing" : ""}`} disabled={!activeRecording} key={turn.id} onClick={() => seekToTurn(turn)}><b>{turn.speaker} · {formatLatency(offset * 1000)}</b><span>{turn.transcript ?? "No transcript captured"}</span></button>;
                  }) : <p className="analysis-pending">No transcript was captured for this trace.</p>}
                </section>
                <div className="finding-list">
                  {trace.findings.length ? (
                    trace.findings.map((finding) => (
                      <div className="finding" key={finding.id}>
                        <b>{finding.severity ?? finding.certainty}</b>
                        {finding.statement}
                      </div>
                    ))
                  ) : (
                    <p className="analysis-pending">
                      No analysis findings yet. The trace below remains the
                      source of truth.
                    </p>
                  )}
                </div>
                <div className="analysis-history">
                  <div>
                    <p className="eyebrow">Analysis history</p>
                    <span>{trace.analysis_runs.length} immutable runs</span>
                  </div>
                  <button onClick={() => void requestReanalysis()}>Re-analyze</button>
                  {trace.analysis_runs.slice(0, 3).map((run) => (
                    <small key={run.id}>
                      {run.status} · {run.prompt_version}
                      {run.model ? ` · ${run.model}` : ""}
                    </small>
                  ))}
                </div>
                <div className="trace-filters" aria-label="Trace event filters">
                  <button
                    className={traceFilter === "all" ? "selected" : ""}
                    onClick={() => setTraceFilter("all")}
                  >
                    All events
                  </button>
                  <button
                    className={traceFilter === "agent" ? "selected" : ""}
                    onClick={() => setTraceFilter("agent")}
                  >
                    Graph & agents
                  </button>
                  <button
                    className={traceFilter === "handoff" ? "selected" : ""}
                    onClick={() => setTraceFilter("handoff")}
                  >
                    Handoffs
                  </button>
                </div>
                <ol className="timeline">
                  {visibleEvents?.map((event) => (
                    <li key={event.id}>
                      <span className={`timeline-dot ${event.status}`} />
                      <div>
                        <b>{event.event_type}</b>
                        <small>
                          {formatDate(event.occurred_at)} ·{" "}
                          {formatLatency(event.duration_ms)}
                        </small>
                      </div>
                    </li>
                  ))}
                </ol>
                {trace.errors.map((item) => (
                  <div className="trace-error" key={item.id}>
                    <b>{item.type}</b>
                    {item.message}
                  </div>
                ))}
                <button className="raw-toggle" onClick={() => setShowRaw(!showRaw)} aria-expanded={showRaw}>{showRaw ? "Hide" : "Inspect"} normalized events</button>
                {showRaw ? <pre className="raw-inspector">{JSON.stringify(trace.events, null, 2)}</pre> : null}
              </>
            )}
          </Card>
        </section>
      </section>
    </main>
  );
}

export function App() {
  return <BrowserRouter><Routes><Route path="/settings" element={<SettingsPage />} /><Route path="*" element={<DashboardPage />} /></Routes></BrowserRouter>;
}

function CohortCard({
  label,
  cohort,
}: {
  label: string;
  cohort: { sample_size: number; resolution_rate: number } | null;
}) {
  return (
    <Card className="cohort-card">
      <p>{label}</p>
      {cohort ? (
        <>
          <strong>{formatRate(cohort.resolution_rate)} resolved</strong>
          <span>{cohort.sample_size} observed sessions</span>
        </>
      ) : (
        <>
          <strong>Insufficient evidence</strong>
          <span>At least 5 observed sessions required</span>
        </>
      )}
    </Card>
  );
}

function LatencyCard({
  label,
  value,
}: {
  label: string;
  value: { sample_size: number; p50_ms: number; p95_ms: number } | null;
}) {
  return (
    <Card className="cohort-card">
      <p>{label}</p>
      {value ? (
        <>
          <strong>p50 {formatLatency(value.p50_ms)}</strong>
          <span>p95 {formatLatency(value.p95_ms)} · {value.sample_size} observed spans</span>
        </>
      ) : (
        <>
          <strong>No observed latency</strong>
          <span>Missing spans are not treated as zero</span>
        </>
      )}
    </Card>
  );
}

function Metric({
  label,
  value,
  danger = false,
}: {
  label: string;
  value: string | number;
  danger?: boolean;
}) {
  return (
    <Card className={`metric-card ${danger ? "danger" : ""}`}>
      <p>{label}</p>
      <strong>{value}</strong>
      <span>From captured traces</span>
    </Card>
  );
}
