import { LoadingSkeleton } from "@/components/dashboard/LoadingSkeleton";
import type { Analytics, Overview } from "@/components/dashboard/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

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

function formatCost(value: number | null | undefined) {
  return value === null || value === undefined
    ? "Unknown"
    : new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 4,
        maximumFractionDigits: 6,
      }).format(value / 1_000_000);
}

export function OverviewPanel({
  overview,
  analytics,
  findingsCount,
  loading,
  environments,
  environmentFilter,
  startedAfter,
  startedBefore,
  onEnvironmentChange,
  onStartedAfterChange,
  onStartedBeforeChange,
  onClearFilters,
}: {
  overview: Overview | null;
  analytics: Analytics | null;
  findingsCount: number;
  loading: boolean;
  environments: Array<{ name: string; slug: string }>;
  environmentFilter: string;
  startedAfter: string;
  startedBefore: string;
  onEnvironmentChange(value: string): void;
  onStartedAfterChange(value: string): void;
  onStartedBeforeChange(value: string): void;
  onClearFilters(): void;
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
        className="mb-5 grid gap-3 rounded-xl border border-slate-200 bg-white p-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end"
        aria-label="Analytics filters"
      >
        <label className="grid gap-1.5 text-xs font-semibold text-slate-600">
          Environment
          <NativeSelect
            value={environmentFilter}
            onChange={(event) => onEnvironmentChange(event.target.value)}
          >
            <option value="">All environments</option>
            {environments.map((item) => (
              <option value={item.slug} key={item.slug}>
                {item.name}
              </option>
            ))}
          </NativeSelect>
        </label>
        <label className="grid gap-1.5 text-xs font-semibold text-slate-600">
          Started after
          <Input
            type="date"
            value={startedAfter}
            onChange={(event) => onStartedAfterChange(event.target.value)}
          />
        </label>
        <label className="grid gap-1.5 text-xs font-semibold text-slate-600">
          Started before
          <Input
            type="date"
            value={startedBefore}
            onChange={(event) => onStartedBeforeChange(event.target.value)}
          />
        </label>
        <Button
          variant="outline"
          disabled={!environmentFilter && !startedAfter && !startedBefore}
          onClick={onClearFilters}
        >
          Clear filters
        </Button>
        <p className="text-xs text-slate-500 md:col-span-4">
          Showing {analytics?.session_count ?? 0} sessions. Missing outcomes,
          latency, usage, and cost remain unknown rather than being counted as
          zero.
        </p>
      </section>
      {analytics?.session_count === 0 ? (
        <section className="first-observation-state">
          <div>
            <h2>Your workspace is ready for its first call</h2>
            <p>
              Nothing is wrong—there is simply no conversation evidence yet.
              Create an ingest key, connect your agent, and the first completed
              session will unlock this dashboard.
            </p>
            <Link to="/settings">Create an API key</Link>
            <span aria-hidden="true"> · </span>
            <Link to="/setup">Connect an agent</Link>
          </div>
        </section>
      ) : (
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
                Move from outcome patterns to the exact sessions, spans, turns,
                and events that support them.
              </p>
            </div>
            <dl className="operations-readout">
              <div>
                <dt>Total calls</dt>
                <dd>{(analytics?.session_count ?? 0).toLocaleString()}</dd>
              </div>
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
              <div>
                <dt>STT p90 latency</dt>
                <dd>
                  {formatLatency(analytics?.latency?.stt?.p90_ms ?? null)}
                </dd>
              </div>
            </dl>
          </section>
          <section className="insight-banner" id="insights">
            <div>
              <h2>Ask why a conversation failed—with evidence.</h2>
              <p>
                Deterministic signals are recorded immediately. After a session
                ends, analysis findings are attached to the exact trace events
                that support them.
              </p>
            </div>
            <span>
              {findingsCount} linked findings ·{" "}
              {overview?.metrics.active_sessions ?? 0} active ·{" "}
              {overview?.metrics.error_count ?? 0} recorded errors
            </span>
          </section>
          <section
            className="analytics-grid"
            aria-label="Voice impact analytics"
          >
            <InterruptionResolutionChart
              points={analytics?.interruption_resolution_points ?? []}
            />
            <div className="grid gap-3">
              <TopIntentsChart intents={analytics?.intent_comparisons ?? []} />
              <VoiceIssuesChart issues={analytics?.voice_issue_impacts ?? []} />
            </div>
          </section>
          <section
            className="grid gap-3 md:grid-cols-4"
            aria-label="Cost, usage, and outcome provenance"
          >
            <Card className="cohort-card">
              <p>Tracked cost</p>
              <strong>{formatCost(analytics?.cost.amount_micros)}</strong>
              <span>
                {formatCost(analytics?.cost.exact_amount_micros)} exact ·{" "}
                {formatCost(analytics?.cost.estimated_amount_micros)} estimated
              </span>
            </Card>
            <Card className="cohort-card">
              <p>Voice usage</p>
              <strong>
                {analytics?.usage.audio_seconds == null
                  ? "Unknown"
                  : `${analytics.usage.audio_seconds.toFixed(1)} seconds`}
              </strong>
              <span>
                {analytics?.usage.tts_characters == null
                  ? "TTS units unknown"
                  : `${analytics.usage.tts_characters.toLocaleString()} TTS characters`}
              </span>
            </Card>
            <Card className="cohort-card">
              <p>Outcome provenance</p>
              <strong>
                {analytics?.outcome_sources.explicit ?? 0} explicit
              </strong>
              <span>
                {analytics?.outcome_sources.inferred ?? 0} inferred ·{" "}
                {analytics?.outcome_sources.unknown ?? 0} unknown
              </span>
            </Card>
            <Card className="cohort-card">
              <p>Voice behavior</p>
              <strong>
                {analytics?.voice_behavior.interruption_sessions ?? 0}{" "}
                interrupted
              </strong>
              <span>
                {analytics?.voice_behavior.dead_air_sessions ?? 0} dead-air ·{" "}
                {analytics?.voice_behavior.talk_over_sessions ?? 0} talk-over
              </span>
            </Card>
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
                      <span className="text-sm text-slate-700">
                        {item.label}
                      </span>
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
                    No recurring failure condition has enough observed evidence
                    yet.
                  </p>
                ) : null}
              </div>
            </Card>
            <Card className="chart-card">
              <h2>Agent and provider comparison</h2>
              <div className="mt-4 grid gap-3">
                {[
                  ["Agent", analytics?.comparisons?.agents ?? []] as const,
                  ["Version", analytics?.comparisons?.versions ?? []] as const,
                  [
                    "Platform",
                    analytics?.comparisons?.platforms ?? [],
                  ] as const,
                  [
                    "Provider",
                    analytics?.comparisons?.providers ?? [],
                  ] as const,
                  ["Model", analytics?.comparisons?.models ?? []] as const,
                ]
                  .flatMap(([group, items]) =>
                    items.map((item) => ({ ...item, group })),
                  )
                  .slice(0, 10)
                  .map((item) => (
                    <div
                      className="grid grid-cols-[minmax(0,1fr)_auto] gap-3"
                      key={`${item.group}-${item.label}`}
                    >
                      <span className="truncate text-sm text-slate-700">
                        <small className="mr-1 text-slate-600">
                          {item.group}
                        </small>
                        {item.label}
                      </span>
                      {item.session_ids[0] ? (
                        <Link
                          className="text-sm font-semibold tabular-nums text-emerald-800 underline-offset-4 hover:underline"
                          to={`/sessions/${item.session_ids[0]}`}
                        >
                          {displayRate(item.resolution_rate)} ·{" "}
                          {item.known_outcomes} known / {item.sessions} sessions
                        </Link>
                      ) : (
                        <b className="text-sm tabular-nums text-slate-900">
                          {displayRate(item.resolution_rate)} ·{" "}
                          {item.known_outcomes} known / {item.sessions} sessions
                        </b>
                      )}
                    </div>
                  ))}
                {!(
                  analytics?.comparisons?.agents?.length ||
                  analytics?.comparisons?.versions?.length ||
                  analytics?.comparisons?.platforms?.length ||
                  analytics?.comparisons?.providers?.length ||
                  analytics?.comparisons?.models?.length
                ) ? (
                  <p className="empty-state">
                    Comparisons appear when agent versions or provider models
                    report outcomes.
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
              label="Observed dead air"
              cohort={analytics?.voice_impact_cohorts.dead_air ?? null}
            />
            <CohortCard
              label="No dead air"
              cohort={analytics?.voice_impact_cohorts.no_dead_air ?? null}
            />
            <CohortCard
              label="Normal interruptions"
              cohort={
                analytics?.voice_impact_cohorts.normal_interruption ?? null
              }
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
      )}
    </>
  );
}

function CohortCard({
  label,
  cohort,
}: {
  label: string;
  cohort: {
    sample_size: number;
    resolution_rate: number;
    session_ids?: string[];
  } | null;
}) {
  return (
    <Card className="cohort-card">
      <p>{label}</p>
      {cohort ? (
        <>
          <strong>{formatRate(cohort.resolution_rate)} resolved</strong>
          {cohort.session_ids?.[0] ? (
            <Link
              className="text-xs font-semibold text-emerald-800 underline-offset-4 hover:underline"
              to={`/sessions/${cohort.session_ids[0]}`}
            >
              {cohort.sample_size} observed sessions
            </Link>
          ) : (
            <span>{cohort.sample_size} observed sessions</span>
          )}
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
function ChartEmpty({ children }: { children: string }) {
  return <p className="empty-state">{children}</p>;
}

function InterruptionResolutionChart({
  points,
}: {
  points: Analytics["interruption_resolution_points"];
}) {
  return (
    <Card className="chart-card voice-scatter-card">
      <h2>Interruption rate vs. resolution result</h2>
      <p className="chart-description">
        Each dot is an observed call. Green calls resolved; red calls did not.
      </p>
      {points.length ? (
        <>
          <div className="chart-legend" aria-hidden="true">
            <span>
              <i className="resolved" /> Resolved
            </span>
            <span>
              <i className="failed" /> Not resolved
            </span>
          </div>
          <div
            className="rechart-frame"
            role="img"
            aria-label="Scatter plot of interruption count against binary resolution result"
          >
            <ResponsiveContainer width="100%" height={300}>
              <ScatterChart
                margin={{ top: 12, right: 18, bottom: 20, left: 0 }}
              >
                <CartesianGrid stroke="#dce8e5" strokeDasharray="3 3" />
                <XAxis
                  dataKey="interruptions"
                  type="number"
                  allowDecimals={false}
                  name="Interruptions"
                  label={{
                    value: "Interruptions per call",
                    position: "insideBottom",
                    offset: -12,
                  }}
                />
                <YAxis
                  dataKey="resolution"
                  type="number"
                  domain={[-0.1, 1.1]}
                  ticks={[0, 1]}
                  tickFormatter={(value) =>
                    value ? "Resolved" : "Not resolved"
                  }
                  width={86}
                />
                <Tooltip
                  cursor={{ strokeDasharray: "3 3" }}
                  formatter={(value, name) =>
                    name === "resolution"
                      ? value
                        ? "Resolved"
                        : "Not resolved"
                      : value
                  }
                />
                <Scatter data={points} isAnimationActive={false}>
                  {points.map((point) => (
                    <Cell
                      key={point.session_id}
                      fill={point.resolution ? "#0f9d7a" : "#e64b5d"}
                    />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <p className="chart-footnote">
            Open an example:{" "}
            <Link to={`/sessions/${points[0].session_id}`}>
              {points[0].intent}
            </Link>
          </p>
        </>
      ) : (
        <ChartEmpty>
          Resolution points appear after sessions report outcomes.
        </ChartEmpty>
      )}
    </Card>
  );
}

function TopIntentsChart({
  intents,
}: {
  intents: Analytics["intent_comparisons"];
}) {
  const observed = intents
    .filter((item) => item.resolution_rate !== null)
    .slice(0, 5);
  const data = observed.map((item) => ({
    ...item,
    percent: Math.round((item.resolution_rate ?? 0) * 100),
  }));
  return (
    <Card className="chart-card compact-chart-card">
      <h2>Top intents by resolution rate</h2>
      <p className="chart-description">
        Observed outcomes, ranked across captured intents.
      </p>
      {data.length ? (
        <>
          <div
            className="rechart-frame"
            role="img"
            aria-label="Bar chart of intent resolution rates"
          >
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={data}
                layout="vertical"
                margin={{ top: 6, right: 22, bottom: 4, left: 8 }}
              >
                <CartesianGrid stroke="#e5eeec" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} unit="%" />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={120}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip formatter={(value) => `${value}%`} />
                <Bar
                  dataKey="percent"
                  fill="#0f9d7a"
                  radius={[0, 4, 4, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-links" aria-label="Intent evidence links">
            {data.map((item) => (
              <Link
                key={item.label}
                to={`/intents/${encodeURIComponent(item.label)}`}
              >
                {item.label}: {item.percent}%
              </Link>
            ))}
          </div>
        </>
      ) : (
        <ChartEmpty>
          Intent rankings appear after outcomes are observed.
        </ChartEmpty>
      )}
    </Card>
  );
}

function VoiceIssuesChart({
  issues,
}: {
  issues: Analytics["voice_issue_impacts"];
}) {
  const data = issues.map((item) => ({
    ...item,
    impact: Math.abs(item.impact_percentage_points),
  }));
  return (
    <Card className="chart-card compact-chart-card">
      <h2>Top voice issues by impact</h2>
      <p className="chart-description">
        Difference in resolution rate versus the observed baseline.
      </p>
      {data.length ? (
        <>
          <div
            className="rechart-frame"
            role="img"
            aria-label="Bar chart of voice issue impact on resolution rate"
          >
            <ResponsiveContainer width="100%" height={190}>
              <BarChart
                data={data}
                layout="vertical"
                margin={{ top: 6, right: 24, bottom: 4, left: 8 }}
              >
                <CartesianGrid stroke="#f1dfe2" horizontal={false} />
                <XAxis type="number" unit=" pp" />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={132}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip formatter={(value) => `${value} percentage points`} />
                <Bar
                  dataKey="impact"
                  fill="#e64b5d"
                  radius={[0, 4, 4, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-links" aria-label="Voice issue evidence links">
            {data.map((item) =>
              item.session_ids[0] ? (
                <Link key={item.key} to={`/sessions/${item.session_ids[0]}`}>
                  {item.label}: {item.impact_percentage_points} pp
                </Link>
              ) : null,
            )}
          </div>
        </>
      ) : (
        <ChartEmpty>
          At least five affected and baseline calls are required per issue.
        </ChartEmpty>
      )}
    </Card>
  );
}
