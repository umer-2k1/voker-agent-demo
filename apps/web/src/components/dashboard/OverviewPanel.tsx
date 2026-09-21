import { LoadingSkeleton } from "@/components/dashboard/LoadingSkeleton";
import type { Analytics, Overview } from "@/components/dashboard/types";
import { Card } from "@/components/ui/card";

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
      <section className="operations-brief" aria-label="Operational summary">
        <div className="operations-signal">
          <span className={(overview?.metrics.error_count ?? 0) > 0 ? "signal-status urgent" : "signal-status"}>
            <i /> {(overview?.metrics.error_count ?? 0) > 0 ? "Attention needed" : "System steady"}
          </span>
          <h2>{(overview?.metrics.error_count ?? 0) > 0 ? "Errors need investigation before the next release." : "No failing traces need immediate action."}</h2>
          <p>Review the sessions queue to move from an observed signal to the exact turn and trace event behind it.</p>
        </div>
        <dl className="operations-readout">
          <div><dt>Open errors</dt><dd>{overview?.metrics.error_count ?? "—"}</dd></div>
          <div><dt>Active now</dt><dd>{overview?.metrics.active_sessions ?? "—"}</dd></div>
          <div><dt>Observed sessions</dt><dd>{overview?.metrics.total_sessions ?? "—"}</dd></div>
          <div><dt>Mean span</dt><dd>{formatLatency(overview?.metrics.average_span_duration_ms ?? null)}</dd></div>
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
        <span>{findingsCount} linked findings in the selected trace</span>
      </section>
      <section className="analytics-grid" aria-label="Voice impact analytics">
        <ImpactChart latency={analytics?.latency ?? null} />
        <OutcomeChart outcomes={analytics?.outcomes ?? null} />
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
