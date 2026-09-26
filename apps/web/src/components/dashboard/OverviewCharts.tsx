import { useMemo } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Analytics } from "@/components/dashboard/types";
import { Card } from "@/components/ui/card";

// Chart palette mirrors the design tokens in styles.css (--chart-*). Kept as
// literals because Recharts writes SVG attributes rather than class names.
const AXIS = "#506a65";
const GRID = "#e5eeec";
const GREEN = "#20a28b";
const INDIGO = "#4f46e5";
const AMBER = "#d97706";
const ROSE = "#be123c";
const CATEGORY_PALETTE = [
  GREEN,
  INDIGO,
  AMBER,
  ROSE,
  "#0e7490",
  "#7c3aed",
  "#15803d",
  "#b45309",
];

const STAGE_ORDER = ["stt", "llm", "tool", "tts", "voice"] as const;
const STAGE_LABELS: Record<string, string> = {
  stt: "STT",
  llm: "LLM",
  tool: "Tools",
  tts: "TTS",
  voice: "Voice",
};

// Outcome keys are provider-defined; collapse synonyms onto one readable
// label and a stable colour so success/resolved never render as two slices.
const OUTCOME_LABELS: Record<string, string> = {
  success: "Resolved",
  resolved: "Resolved",
  escalated: "Escalated",
  abandoned: "Abandoned",
  failed: "Failed",
  error: "Error",
};
const OUTCOME_COLORS: Record<string, string> = {
  Resolved: GREEN,
  Escalated: AMBER,
  Abandoned: ROSE,
  Failed: ROSE,
  Error: ROSE,
};
const OUTCOME_WEIGHT: Record<string, number> = {
  Resolved: 0,
  Escalated: 1,
  Abandoned: 2,
  Failed: 3,
  Error: 4,
};

function outcomeLabel(key: string) {
  return (
    OUTCOME_LABELS[key] ??
    key.replace(/_/g, " ").replace(/^\w/, (char) => char.toUpperCase())
  );
}

function outcomeColor(label: string) {
  return OUTCOME_COLORS[label] ?? INDIGO;
}

function formatLatency(value: number) {
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
}

function formatLatencyTick(value: number) {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${Math.round(value)}ms`;
}

function formatRate(value: number) {
  return `${Math.round(value * 100)}%`;
}

function formatDay(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

const DAY_MS = 86_400_000;

/**
 * Fill calendar gaps between the first and last observed day so the trend
 * reads as time rather than as adjacent samples. Refuses to fabricate a wide
 * window (over ~3 months) where the axes would misrepresent the data.
 */
function fillTrend(rows: Analytics["volume_trend"]) {
  const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
  if (sorted.length < 2) return sorted;

  const first = new Date(`${sorted[0].date}T00:00:00Z`).getTime();
  const last = new Date(`${sorted[sorted.length - 1].date}T00:00:00Z`).getTime();
  const days = Math.round((last - first) / DAY_MS) + 1;
  if (days > 92) return sorted;

  const observed = new Map(sorted.map((row) => [row.date, row.sessions]));
  return Array.from({ length: days }, (_, index) => {
    const date = new Date(first + index * DAY_MS).toISOString().slice(0, 10);
    return { date, sessions: observed.get(date) ?? 0 };
  });
}

function ChartEmpty({ children }: { children: string }) {
  return <p className="empty-state">{children}</p>;
}

function VolumeTrendCard({ rows }: { rows: Analytics["volume_trend"] }) {
  const data = useMemo(() => fillTrend(rows ?? []), [rows]);
  const total = data.reduce((sum, row) => sum + row.sessions, 0);
  const busiest = data.reduce<{ date: string; sessions: number } | null>(
    (best, row) => (row.sessions > (best?.sessions ?? -1) ? row : best),
    null,
  );
  return (
    <Card className="chart-card shadow-none">
      <h2>Call volume</h2>
      <p className="chart-description">
        Sessions started per day for the selected environments and dates.
      </p>
      {data.length ? (
        <>
          <div
            className="rechart-frame [&_svg]:outline-none"
            role="img"
            aria-label={`Bar chart of call volume: ${total} sessions over ${data.length} day${data.length === 1 ? "" : "s"}`}
          >
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                accessibilityLayer={false}
                data={data}
                margin={{ top: 12, right: 8, bottom: 0, left: -16 }}
              >
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis
                  dataKey="date"
                  tickFormatter={(value) => formatDay(String(value))}
                  tick={{ fontSize: 11, fill: AXIS }}
                  tickLine={false}
                  axisLine={{ stroke: GRID }}
                  minTickGap={16}
                  padding={{ left: 12, right: 12 }}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fontSize: 11, fill: AXIS }}
                  tickLine={false}
                  axisLine={false}
                  width={36}
                />
                <Tooltip
                  cursor={{ fill: "rgba(32,162,139,0.08)" }}
                  labelFormatter={(value) => formatDay(String(value))}
                  formatter={(value) => [`${value} sessions`, "Volume"]}
                />
                <Bar
                  dataKey="sessions"
                  fill={GREEN}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={48}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="chart-footnote">
            {total.toLocaleString()} sessions ·{" "}
            {busiest
              ? `busiest ${formatDay(busiest.date)} (${busiest.sessions})`
              : "no activity"}{" "}
            · {(total / data.length).toFixed(1)}/day average
          </p>
          <table className="sr-only">
            <caption>Call volume by day</caption>
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col">Sessions</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.date}>
                  <td>{formatDay(row.date)}</td>
                  <td>{row.sessions}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <ChartEmpty>Call volume appears once sessions arrive.</ChartEmpty>
      )}
    </Card>
  );
}

function RatesTrendCard({ rows }: { rows: Analytics["rates_trend"] }) {
  const data = useMemo(
    () =>
      (rows ?? []).map((row) => ({
        date: row.date,
        resolution:
          row.resolution_rate == null
            ? null
            : Math.round(row.resolution_rate * 1000) / 10,
        correction:
          row.correction_rate == null
            ? null
            : Math.round(row.correction_rate * 1000) / 10,
        sessions: row.sessions,
      })),
    [rows],
  );
  const hasRates = data.some(
    (row) => row.resolution != null || row.correction != null,
  );
  return (
    <Card className="chart-card shadow-none">
      <h2>Correction vs resolution over time</h2>
      <p className="chart-description">
        Share of sessions resolved and share with an explicit caller correction,
        per day. Days without a known outcome stay out of the resolution line.
      </p>
      {hasRates ? (
        <>
          <div className="chart-legend" aria-hidden="true">
            <span>
              <i style={{ background: GREEN }} /> Resolution rate
            </span>
            <span>
              <i style={{ background: AMBER }} /> Correction rate
            </span>
          </div>
          <div
            className="rechart-frame [&_svg]:outline-none"
            role="img"
            aria-label={`Line chart of correction and resolution rates: ${data
              .map(
                (row) =>
                  `${formatDay(row.date)} resolution ${row.resolution == null ? "not measured" : `${row.resolution}%`}, correction ${row.correction == null ? "not measured" : `${row.correction}%`}`,
              )
              .join("; ")}`}
          >
            <ResponsiveContainer width="100%" height={240}>
              <LineChart
                accessibilityLayer={false}
                data={data}
                margin={{ top: 8, right: 12, bottom: 0, left: -16 }}
              >
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis
                  dataKey="date"
                  tickFormatter={(value) => formatDay(String(value))}
                  tick={{ fontSize: 11, fill: AXIS }}
                  tickLine={false}
                  axisLine={{ stroke: GRID }}
                  minTickGap={16}
                />
                <YAxis
                  domain={[0, 100]}
                  unit="%"
                  tick={{ fontSize: 11, fill: AXIS }}
                  tickLine={false}
                  axisLine={false}
                  width={44}
                />
                <Tooltip
                  labelFormatter={(value) => formatDay(String(value))}
                  formatter={(value, name) => [
                    value == null ? "Not measured" : `${value}%`,
                    name === "resolution" ? "Resolution" : "Correction",
                  ]}
                />
                <Line
                  type="monotone"
                  dataKey="resolution"
                  stroke={GREEN}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="correction"
                  stroke={AMBER}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <table className="sr-only">
            <caption>Correction and resolution rates by day</caption>
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col">Sessions</th>
                <th scope="col">Resolution rate</th>
                <th scope="col">Correction rate</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.date}>
                  <td>{formatDay(row.date)}</td>
                  <td>{row.sessions}</td>
                  <td>
                    {row.resolution == null ? "Not measured" : `${row.resolution}%`}
                  </td>
                  <td>
                    {row.correction == null ? "Not measured" : `${row.correction}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <ChartEmpty>
          Rate trends appear once calls report outcomes or corrections.
        </ChartEmpty>
      )}
    </Card>
  );
}

function OutcomeMixCard({
  outcomes,
  coverage,
}: {
  outcomes: Analytics["outcomes"];
  coverage: { observed: number; total: number };
}) {
  const data = useMemo(() => {
    const merged = new Map<string, number>();
    for (const [key, count] of Object.entries(outcomes ?? {})) {
      if (!count) continue;
      const label = outcomeLabel(key);
      merged.set(label, (merged.get(label) ?? 0) + count);
    }
    return [...merged.entries()]
      .map(([label, value]) => ({ label, value, color: outcomeColor(label) }))
      .sort(
        (a, b) =>
          (OUTCOME_WEIGHT[a.label] ?? 99) - (OUTCOME_WEIGHT[b.label] ?? 99) ||
          b.value - a.value,
      );
  }, [outcomes]);
  const known = data.reduce((sum, item) => sum + item.value, 0);
  const unmeasured = Math.max(0, coverage.total - known);

  return (
    <Card className="chart-card shadow-none">
      <h2>Outcome mix</h2>
      <p className="chart-description">
        Known terminal outcomes only; sessions without an outcome stay out of
        the ring.
      </p>
      {data.length ? (
        <>
          <div className="relative">
            <div
              className="rechart-frame [&_svg]:outline-none"
              role="img"
              aria-label={`Donut chart of outcomes: ${data.map((item) => `${item.label} ${item.value}`).join(", ")}`}
            >
              <ResponsiveContainer width="100%" height={210}>
                <PieChart accessibilityLayer={false}>
                  <Pie
                    data={data}
                    dataKey="value"
                    nameKey="label"
                    innerRadius={58}
                    outerRadius={86}
                    paddingAngle={2}
                    stroke="#ffffff"
                    strokeWidth={2}
                    isAnimationActive={false}
                  >
                    {data.map((item) => (
                      <Cell key={item.label} fill={item.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value, name) => [
                      `${value} sessions`,
                      String(name),
                    ]}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div
              className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"
              aria-hidden="true"
            >
              <strong className="text-2xl font-semibold tabular-nums text-foreground">
                {known}
              </strong>
              <span className="text-xs text-muted-foreground">
                known outcomes
              </span>
            </div>
          </div>
          <div className="chart-legend">
            {data.map((item) => (
              <span key={item.label}>
                <i style={{ background: item.color }} />
                {item.label} · {item.value} ({formatRate(item.value / known)})
              </span>
            ))}
          </div>
          <p className="chart-footnote">
            {known} of {coverage.total} sessions have a known outcome
            {unmeasured ? ` · ${unmeasured} not yet measured` : ""}.{" "}
            <Link to="/sessions">Review sessions</Link>
          </p>
          <table className="sr-only">
            <caption>Outcome mix</caption>
            <thead>
              <tr>
                <th scope="col">Outcome</th>
                <th scope="col">Sessions</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item) => (
                <tr key={item.label}>
                  <td>{item.label}</td>
                  <td>{item.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <ChartEmpty>
          Outcome mix appears once calls report a terminal result.
        </ChartEmpty>
      )}
    </Card>
  );
}

function LatencyByStageCard({ latency }: { latency: Analytics["latency"] }) {
  const data = STAGE_ORDER.map((stage) => {
    const distribution = latency?.[stage];
    if (!distribution || !distribution.sample_size) return null;
    return {
      stage,
      label: STAGE_LABELS[stage] ?? stage,
      p50: Math.round(distribution.p50_ms),
      p90: Math.round(distribution.p90_ms),
      samples: distribution.sample_size,
    };
  }).filter((row): row is NonNullable<typeof row> => row !== null);
  const zeroReported = data.some((row) => row.p90 === 0);

  return (
    <Card className="chart-card shadow-none">
      <h2>Latency by stage</h2>
      <p className="chart-description">
        Median and 90th percentile per measured span. Stages with no spans stay
        out of the chart.
      </p>
      {data.length ? (
        <>
          <div className="chart-legend" aria-hidden="true">
            <span>
              <i style={{ background: GREEN }} /> p50
            </span>
            <span>
              <i style={{ background: INDIGO }} /> p90
            </span>
          </div>
          <div
            className="rechart-frame [&_svg]:outline-none"
            role="img"
            aria-label={`Bar chart of latency by stage: ${data
              .map((row) => `${row.label} p50 ${formatLatency(row.p50)}, p90 ${formatLatency(row.p90)}`)
              .join("; ")}`}
          >
            <ResponsiveContainer width="100%" height={210}>
              <BarChart
                accessibilityLayer={false}
                data={data}
                margin={{ top: 8, right: 12, bottom: 0, left: -8 }}
              >
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 11, fill: AXIS }}
                  tickLine={false}
                  axisLine={{ stroke: GRID }}
                />
                <YAxis
                  tickFormatter={formatLatencyTick}
                  tick={{ fontSize: 11, fill: AXIS }}
                  tickLine={false}
                  axisLine={false}
                  width={52}
                />
                <Tooltip
                  cursor={{ fill: "rgba(32,162,139,0.08)" }}
                  formatter={(value, name) => [
                    formatLatency(Number(value)),
                    name === "p50" ? "p50" : "p90",
                  ]}
                />
                <Bar
                  dataKey="p50"
                  fill={GREEN}
                  radius={[4, 4, 0, 0]}
                  isAnimationActive={false}
                />
                <Bar
                  dataKey="p90"
                  fill={INDIGO}
                  radius={[4, 4, 0, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="chart-footnote">
            {data.map((row) => `${row.label}: ${row.samples}`).join(" · ")} spans.{" "}
            {zeroReported
              ? "A 0 ms stage means the provider reported no duration for that span."
              : null}
          </p>
          <table className="sr-only">
            <caption>Latency by stage</caption>
            <thead>
              <tr>
                <th scope="col">Stage</th>
                <th scope="col">p50</th>
                <th scope="col">p90</th>
                <th scope="col">Samples</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.stage}>
                  <td>{row.label}</td>
                  <td>{formatLatency(row.p50)}</td>
                  <td>{formatLatency(row.p90)}</td>
                  <td>{row.samples}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <ChartEmpty>
          Latency appears once adapters report span timings.
        </ChartEmpty>
      )}
    </Card>
  );
}

function VoiceIssuesCard({
  issues,
}: {
  issues: Analytics["voice_issue_impacts"];
}) {
  const data = useMemo(
    () =>
      (issues ?? [])
        .map((item) => ({
          ...item,
          magnitude: Math.abs(item.impact_percentage_points),
          color: item.impact_percentage_points < 0 ? ROSE : GREEN,
        }))
        .sort((a, b) => b.magnitude - a.magnitude)
        .slice(0, 5),
    [issues],
  );

  return (
    <Card className="chart-card shadow-none">
      <h2>Voice issues by impact</h2>
      <p className="chart-description">
        Change in resolution rate versus each issue&rsquo;s observed baseline.
        Longer bars mean a larger effect.
      </p>
      {data.length ? (
        <>
          <div
            className="rechart-frame [&_svg]:outline-none"
            role="img"
            aria-label={`Bar chart of voice issue impact: ${data
              .map((item) => `${item.label} ${item.impact_percentage_points} percentage points`)
              .join("; ")}`}
          >
            <ResponsiveContainer width="100%" height={210}>
              <BarChart
                accessibilityLayer={false}
                data={data}
                layout="vertical"
                margin={{ top: 4, right: 24, bottom: 0, left: 8 }}
              >
                <CartesianGrid stroke={GRID} horizontal={false} />
                <XAxis type="number" unit=" pp" tick={{ fontSize: 11, fill: AXIS }} tickLine={false} />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={140}
                  tick={{ fontSize: 11, fill: AXIS }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  cursor={{ fill: "rgba(32,162,139,0.08)" }}
                  formatter={(value, _name, item) => [
                    `${item?.payload?.impact_percentage_points ?? value} pp`,
                    "Impact",
                  ]}
                />
                <Bar
                  dataKey="magnitude"
                  radius={[0, 4, 4, 0]}
                  isAnimationActive={false}
                >
                  {data.map((item) => (
                    <Cell key={item.key} fill={item.color} />
                  ))}
                </Bar>
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
          <table className="sr-only">
            <caption>Voice issues by impact</caption>
            <thead>
              <tr>
                <th scope="col">Issue</th>
                <th scope="col">Impact (percentage points)</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item) => (
                <tr key={item.key}>
                  <td>{item.label}</td>
                  <td>{item.impact_percentage_points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <ChartEmpty>
          At least five affected and baseline calls are required per issue.
        </ChartEmpty>
      )}
    </Card>
  );
}

function IntentCategoriesCard({
  intents,
}: {
  intents: Analytics["intent_comparisons"];
}) {
  const ranked = useMemo(
    () =>
      [...(intents ?? [])]
        .filter((item) => item.sessions > 0)
        .sort((a, b) => b.sessions - a.sessions),
    [intents],
  );
  const total = ranked.reduce((sum, item) => sum + item.sessions, 0);
  const segments = useMemo(() => {
    if (!total) return [];
    const rows = ranked.slice(0, 7).map((item, index) => ({
      label: item.label,
      value: item.sessions,
      rate: item.resolution_rate,
      color: CATEGORY_PALETTE[index % CATEGORY_PALETTE.length],
    }));
    const rest = ranked.slice(7).reduce((sum, item) => sum + item.sessions, 0);
    if (rest > 0)
      rows.push({ label: "Other", value: rest, rate: null, color: "#94a3b8" });
    return rows;
  }, [ranked, total]);

  return (
    <Card className="chart-card shadow-none">
      <h2>Intent categories</h2>
      <p className="chart-description">
        Share of calls by routed intent across the selected filters. Resolution
        is shown per category where a known outcome exists.
      </p>
      {total ? (
        <>
          <div
            className="flex h-3 w-full overflow-hidden rounded-full"
            role="img"
            aria-label={`Intent category mix across ${total} calls: ${segments
              .map((segment) => `${segment.label} ${Math.round((segment.value / total) * 100)}%`)
              .join(", ")}`}
          >
            {segments.map((segment) => (
              <span
                key={segment.label}
                style={{
                  width: `${(segment.value / total) * 100}%`,
                  background: segment.color,
                }}
                title={`${segment.label}: ${segment.value} calls`}
              />
            ))}
          </div>
          <ul className="mt-4 grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
            {segments.map((segment) => (
              <li
                className="flex items-center justify-between gap-3 text-sm"
                key={segment.label}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <i
                    aria-hidden="true"
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ background: segment.color }}
                  />
                  <span className="truncate" title={segment.label}>
                    {segment.label}
                  </span>
                </span>
                <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                  {Math.round((segment.value / total) * 100)}%
                  {segment.rate != null ? ` · ${formatRate(segment.rate)}` : ""}
                </span>
              </li>
            ))}
          </ul>
          <table className="sr-only">
            <caption>Intent categories</caption>
            <thead>
              <tr>
                <th scope="col">Intent</th>
                <th scope="col">Calls</th>
                <th scope="col">Share</th>
                <th scope="col">Resolution rate</th>
              </tr>
            </thead>
            <tbody>
              {segments.map((segment) => (
                <tr key={segment.label}>
                  <td>{segment.label}</td>
                  <td>{segment.value}</td>
                  <td>{Math.round((segment.value / total) * 100)}%</td>
                  <td>
                    {segment.rate == null ? "Not measured" : formatRate(segment.rate)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <ChartEmpty>
          Intent categories appear once calls report a routed intent.
        </ChartEmpty>
      )}
    </Card>
  );
}

export function OverviewCharts({ analytics }: { analytics: Analytics | null }) {
  if (!analytics) return null;
  return (
    <section
      className="grid gap-4 xl:grid-cols-2"
      aria-label="Workspace charts"
    >
      <div className="xl:col-span-2">
        <VolumeTrendCard rows={analytics.volume_trend ?? []} />
      </div>
      <div className="xl:col-span-2">
        <RatesTrendCard rows={analytics.rates_trend ?? []} />
      </div>
      <OutcomeMixCard
        outcomes={analytics.outcomes ?? {}}
        coverage={analytics.metric_coverage?.outcomes ?? { observed: 0, total: 0 }}
      />
      <LatencyByStageCard latency={analytics.latency ?? {}} />
      <div className="xl:col-span-2">
        <IntentCategoriesCard intents={analytics.intent_comparisons ?? []} />
      </div>
      <div className="xl:col-span-2">
        <VoiceIssuesCard issues={analytics.voice_issue_impacts ?? []} />
      </div>
    </section>
  );
}
