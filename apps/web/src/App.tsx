import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";

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

export function App() {
  const [overview, setOverview] = useState<Overview | null>(null);
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

  async function loadTrace(sessionId: string, active = true) {
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/projects/${projectSlug}/sessions/${sessionId}`,
      );
      if (!response.ok) throw new Error("Unable to load this session trace.");
      const payload = (await response.json()) as Trace;
      if (active) setTrace(payload);
    } catch (caught) {
      if (active)
        setError(
          caught instanceof Error
            ? caught.message
            : "Unable to load session trace.",
        );
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
        const [overviewResponse, nextSessions] = await Promise.all([
          fetch(`${apiBaseUrl}/api/projects/${projectSlug}/overview`),
          loadSessions(0, active),
        ]);
        if (!overviewResponse.ok)
          throw new Error("Unable to load observability data.");
        const nextOverview = (await overviewResponse.json()) as Overview;
        if (!active) return;
        setOverview(nextOverview);
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
                  {trace.turns.length ? trace.turns.map((turn) => <div className="transcript-turn" key={turn.id}><b>{turn.speaker}</b><span>{turn.transcript ?? "No transcript captured"}</span></div>) : <p className="analysis-pending">No transcript was captured for this trace.</p>}
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
