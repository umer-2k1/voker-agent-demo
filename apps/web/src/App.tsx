import { useEffect, useState } from "react";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001";
const projectSlug = import.meta.env.VITE_PROJECT_SLUG ?? "voker-voice";

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
  }>;
  errors: Array<{ id: string; type: string; message: string }>;
  findings: Array<{
    id: string;
    certainty: string;
    severity: string | null;
    statement: string;
  }>;
};

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
  const [trace, setTrace] = useState<Trace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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

  useEffect(() => {
    let active = true;
    async function loadDashboard() {
      try {
        const [overviewResponse, sessionsResponse] = await Promise.all([
          fetch(`${apiBaseUrl}/api/projects/${projectSlug}/overview`),
          fetch(`${apiBaseUrl}/api/projects/${projectSlug}/sessions`),
        ]);
        if (!overviewResponse.ok || !sessionsResponse.ok)
          throw new Error("Unable to load observability data.");
        const nextOverview = (await overviewResponse.json()) as Overview;
        const nextSessions = (await sessionsResponse.json()) as {
          items: VoiceSession[];
        };
        if (!active) return;
        setOverview(nextOverview);
        setSessions(nextSessions.items);
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
  }, []);

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
          <span className="live-indicator">
            <i /> Live data
          </span>
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
          <article className="panel sessions-panel" id="sessions">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Recent activity</p>
                <h2>Captured sessions</h2>
              </div>
              <span>{sessions.length} shown</span>
            </div>
            {loading ? (
              <p className="empty-state">Loading persisted sessions…</p>
            ) : null}
            {!loading && !sessions.length ? (
              <p className="empty-state">
                No sessions yet. Connect the Python SDK or send canonical events
                to begin.
              </p>
            ) : null}
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
          </article>
          <article className="panel trace-panel" id="trace">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Complete conversation trace</p>
                <h2>
                  {trace
                    ? trace.session.external_session_id
                    : "Select a session"}
                </h2>
              </div>
              <span>{trace?.events.length ?? 0} events</span>
            </div>
            {!trace ? (
              <p className="empty-state">
                Choose a persisted session to inspect its timeline.
              </p>
            ) : (
              <>
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
                <ol className="timeline">
                  {trace.events.map((event) => (
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
              </>
            )}
          </article>
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
    <article className={`metric-card ${danger ? "danger" : ""}`}>
      <p>{label}</p>
      <strong>{value}</strong>
      <span>From captured traces</span>
    </article>
  );
}
