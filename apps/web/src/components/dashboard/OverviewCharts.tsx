import { useMemo } from "react";
import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
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
const TEAL = "#004d43";
const GREEN = "#20a28b";
const INDIGO = "#4f46e5";
const AMBER = "#d97706";
const ROSE = "#be123c";

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
  return (
    <Card className="chart-card shadow-none">
      <h2>Call volume</h2>
      <p className="chart-description">
        Sessions started per day for the selected environments and dates.
      </p>
      {data.length ? (
        <div
          className="rechart-frame"
          role="img"
          aria-label={`Area chart of call volume: ${total} sessions over ${data.length} day${data.length === 1 ? "" : "s"}`}
        >
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
              <defs>
                <linearGradient id="volumeFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={GREEN} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={GREEN} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={(value) => formatDay(String(value))}
                tick={{ fontSize: 11, fill: AXIS }}
                tickLine={false}
                axisLine={{ stroke: GRID }}
                minTickGap={24}
              />
              <YAxis
                allowDecimals={false}
                tick={{ fontSize: 11, fill: AXIS }}
                tickLine={false}
                axisLine={false}
                width={36}
              />
              <Tooltip
                labelFormatter={(value) => formatDay(String(value))}
                formatter={(value) => [`${value} sessions`, "Volume"]}
              />
              <Area
                type="monotone"
                dataKey="sessions"
                stroke={TEAL}
                strokeWidth={2}
                fill="url(#volumeFill)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <ChartEmpty>Call volume appears once sessions arrive.</ChartEmpty>
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
              className="rechart-frame"
              role="img"
              aria-label={`Donut chart of outcomes: ${data.map((item) => `${item.label} ${item.value}`).join(", ")}`}
            >
              <ResponsiveContainer width="100%" height={210}>
                <PieChart>
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
            className="rechart-frame"
            role="img"
            aria-label={`Bar chart of latency by stage: ${data
              .map((row) => `${row.label} p50 ${formatLatency(row.p50)}, p90 ${formatLatency(row.p90)}`)
              .join("; ")}`}
          >
            <ResponsiveContainer width="100%" height={210}>
              <BarChart
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
            className="rechart-frame"
            role="img"
            aria-label={`Bar chart of voice issue impact: ${data
              .map((item) => `${item.label} ${item.impact_percentage_points} percentage points`)
              .join("; ")}`}
          >
            <ResponsiveContainer width="100%" height={210}>
              <BarChart
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
        </>
      ) : (
        <ChartEmpty>
          At least five affected and baseline calls are required per issue.
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
      <OutcomeMixCard
        outcomes={analytics.outcomes ?? {}}
        coverage={analytics.metric_coverage?.outcomes ?? { observed: 0, total: 0 }}
      />
      <LatencyByStageCard latency={analytics.latency ?? {}} />
      <div className="xl:col-span-2">
        <VoiceIssuesCard issues={analytics.voice_issue_impacts ?? []} />
      </div>
    </section>
  );
}
