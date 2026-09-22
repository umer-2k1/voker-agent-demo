import { LoadingSkeleton } from "@/components/dashboard/LoadingSkeleton";
import type { Analytics, Overview } from "@/components/dashboard/types";
import { Card } from "@/components/ui/card";
import { Link } from "react-router-dom";

function formatLatency(value: number | null) {
  return value === null
    ? "—"
    : value >= 1000
      ? `${(value / 1000).toFixed(2)} s`
      : `${Math.round(value)} ms`;
}

function formatRate(value: number) {
  return `${Math.round(value * 100)}%`;
}

function displayRate(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : formatRate(value);
}

export function OverviewPanel({
  overview,
  analytics,
  findingsCount,
  loading,
}: {
  overview: Overview | null;
  analytics: Analytics | null;
  findingsCount: number;
  loading: boolean;
}) {
  if (loading)
    return (
      <section aria-label="Loading dashboard overview">
        <div className="metric-grid skeleton-metrics">
          <LoadingSkeleton rows={5} />
        </div>
        <div className="overview-skeleton">
          <LoadingSkeleton rows={4} />
        </div>
      </section>
    );
  return (
    <>
      <section
        className="operations-brief"
        aria-label="Conversation outcome summary"
      >
        <div className="operations-signal">
          <span
            className={
              (analytics?.rates?.error ?? 0) > 0
                ? "signal-status urgent"
                : "signal-status"
            }
          >
            <i />{" "}
            {(analytics?.rates?.error ?? 0) > 0
              ? "Review conversation failures"
              : "No recorded failures"}
          </span>
          <h2>
            {analytics?.rates?.resolution == null
              ? "Outcome evidence will appear after completed sessions."
              : `${displayRate(analytics.rates.resolution)} of observed outcomes resolved successfully.`}
          </h2>
          <p>
            Move from outcome patterns to the exact sessions, spans, turns, and
            events that support them.
          </p>
        </div>
        <dl className="operations-readout">
          <div>
            <dt>Resolution</dt>
            <dd>{displayRate(analytics?.rates?.resolution)}</dd>
          </div>
          <div>
            <dt>Corrections</dt>
            <dd>{displayRate(analytics?.rates?.correction)}</dd>
          </div>
          <div>
            <dt>Escalation</dt>
            <dd>{displayRate(analytics?.rates?.escalation)}</dd>
          </div>
          <div>
            <dt>Abandonment</dt>
            <dd>{displayRate(analytics?.rates?.abandonment)}</dd>
          </div>
        </dl>
      </section>
      <section className="insight-banner" id="insights">
        <div>
          <h2>Ask why a conversation failed—with evidence.</h2>
          <p>
            Deterministic signals are recorded immediately. After a session
            ends, analysis findings are attached to the exact trace events that
            support them.
          </p>
        </div>
        <span>
          {findingsCount} linked findings ·{" "}
          {overview?.metrics.active_sessions ?? 0} active ·{" "}
          {overview?.metrics.error_count ?? 0} recorded errors
        </span>
      </section>
      <section className="analytics-grid" aria-label="Voice impact analytics">
        <ImpactChart latency={analytics?.latency ?? null} />
        <OutcomeChart outcomes={analytics?.outcomes ?? null} />
      </section>
      <section
        className="analytics-grid"
        aria-label="Recurring findings and comparisons"
      >
        <Card className="chart-card">
          <h2>Recurring observed conditions</h2>
          <div className="mt-4 grid gap-2">
            {(analytics?.insights ?? [])
              .filter((item) => item.count > 0)
              .map((item) => (
                <div
                  className="flex items-center justify-between gap-3 border-b border-slate-100 py-2"
                  key={item.key}
                >
                  <span className="text-sm text-slate-700">{item.label}</span>
                  {item.session_ids[0] ? (
                    <Link
                      className="text-sm font-semibold text-emerald-800 underline-offset-4 hover:underline"
                      to={`/sessions/${item.session_ids[0]}`}
                    >
                      {item.count} sessions
                    </Link>
                  ) : (
                    <b>{item.count}</b>
                  )}
                </div>
              ))}
            {(analytics?.failure_category_insights ?? []).map(
              ({ category, count, session_ids }) => (
                <div
                  className="flex items-center justify-between gap-3 border-b border-slate-100 py-2"
                  key={category}
                >
                  <span className="text-sm text-slate-700">
                    {category.replaceAll("_", " ")}
                  </span>
                  {session_ids[0] ? (
                    <Link
                      className="text-sm font-semibold text-emerald-800 underline-offset-4 hover:underline"
                      to={`/sessions/${session_ids[0]}`}
                    >
                      {count} findings
                    </Link>
                  ) : (
                    <b className="text-sm tabular-nums text-slate-900">
                      {count} findings
                    </b>
                  )}
                </div>
              ),
            )}
            {!(analytics?.insights ?? []).some((item) => item.count > 0) ? (
              <p className="empty-state">
                No recurring failure condition has enough observed evidence yet.
              </p>
            ) : null}
          </div>
        </Card>
        <Card className="chart-card">
          <h2>Agent and provider comparison</h2>
          <div className="mt-4 grid gap-3">
            {[
              ...(analytics?.comparisons?.agents ?? []),
              ...(analytics?.comparisons?.providers ?? []),
            ]
              .slice(0, 8)
              .map((item) => (
                <div
                  className="grid grid-cols-[minmax(0,1fr)_auto] gap-3"
                  key={item.label}
                >
                  <span className="truncate text-sm text-slate-700">
                    {item.label}
                  </span>
                  <b className="text-sm tabular-nums text-slate-900">
                    {formatRate(item.resolution_rate)} · {item.sessions}
                  </b>
                </div>
              ))}
            {!(
              analytics?.comparisons?.agents?.length ||
              analytics?.comparisons?.providers?.length
            ) ? (
              <p className="empty-state">
                Comparisons appear when agent versions or provider models report
                outcomes.
              </p>
            ) : null}
          </div>
        </Card>
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
        <CohortCard
          label="Slow STT"
          cohort={analytics?.voice_impact_cohorts.slow_stt ?? null}
        />
        <CohortCard
          label="Fast STT"
          cohort={analytics?.voice_impact_cohorts.fast_stt ?? null}
        />
      </section>
    </>
  );
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
function ImpactChart({ latency }: { latency: Analytics["latency"] | null }) {
  const entries = Object.entries(latency ?? {}).filter(([, value]) => value);
  const max = Math.max(...entries.map(([, value]) => value?.p95_ms ?? 0), 1);
  return (
    <Card className="chart-card">
      <p className="eyebrow">Stage latency</p>
      <h2>p95 across captured spans</h2>
      {entries.length ? (
        <div className="bar-chart">
          {entries.map(([stage, value]) => (
            <div className="bar-row" key={stage}>
              <span>{stage.toUpperCase()}</span>
              <div>
                <i
                  style={{
                    width: `${Math.max(8, ((value?.p95_ms ?? 0) / max) * 100)}%`,
                  }}
                />
              </div>
              <b>{formatLatency(value?.p95_ms ?? null)}</b>
            </div>
          ))}
        </div>
      ) : (
        <p className="empty-state">
          Latency bars appear after spans are captured.
        </p>
      )}
    </Card>
  );
}
function OutcomeChart({
  outcomes,
}: {
  outcomes: Record<string, number> | null;
}) {
  const entries = Object.entries(outcomes ?? {});
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  return (
    <Card className="chart-card">
      <p className="eyebrow">Session outcomes</p>
      <h2>Captured result mix</h2>
      {total ? (
        <div className="outcome-list">
          {entries.map(([outcome, count]) => (
            <div key={outcome}>
              <span>{outcome}</span>
              <b>{count}</b>
              <i style={{ width: `${(count / total) * 100}%` }} />
            </div>
          ))}
        </div>
      ) : (
        <p className="empty-state">
          Outcome mix appears after completed sessions are captured.
        </p>
      )}
    </Card>
  );
}
