import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  ExternalLink,
  RotateCcw,
  Share2,
  Waypoints,
  Zap,
} from "lucide-react";
import WaveSurfer from "wavesurfer.js";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/dashboard/LoadingSkeleton";
import type { Trace } from "@/components/dashboard/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Eyebrow, H2, H3 } from "@/components/ui/typography";
import { cn } from "@/lib/utils";

function formatLatency(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return value >= 1000
    ? `${(value / 1000).toFixed(2)} s`
    : `${Math.round(value)} ms`;
}

function formatClock(seconds: number) {
  const rounded = Math.max(0, Math.floor(seconds));
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

function formatCost(micros: number) {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: micros < 10_000 ? 4 : 2,
    maximumFractionDigits: 6,
  }).format(micros / 1_000_000);
}

function certaintyLabel(certainty: string) {
  switch (certainty) {
    case "confirmed_execution_fact":
      return "Confirmed execution fact";
    case "detected_condition":
    case "observed":
      return "Detected condition";
    case "inferred_contributing_factor":
      return "Inferred contributing factor";
    default:
      return "Insufficient evidence";
  }
}

function statusMeta(status: string) {
  switch (status) {
    case "completed":
      return { label: "Completed", variant: "success" as const, tone: "text-success" };
    case "in_progress":
      return { label: "In progress", variant: "info" as const, tone: "text-info" };
    case "failed":
      return { label: "Failed", variant: "destructive" as const, tone: "text-destructive" };
    case "incomplete":
      return { label: "Incomplete", variant: "warning" as const, tone: "text-warning" };
    default:
      return {
        label: status.replaceAll("_", " "),
        variant: "secondary" as const,
        tone: "text-muted-foreground",
      };
  }
}

function WaveformPlayer({
  src,
  onReady,
  onTimeUpdate,
}: {
  src: string;
  onReady(wave: WaveSurfer | null): void;
  onTimeUpdate(seconds: number): void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const waveRef = useRef<WaveSurfer | null>(null);
  const [playing, setPlaying] = useState(false);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [duration, setDuration] = useState(0);
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    if (!containerRef.current) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    const wave = WaveSurfer.create({
      container: containerRef.current,
      cursorColor: "#004d43",
      height: 42,
      progressColor: "#176258",
      waveColor: "#b8d4ce",
      barWidth: 2,
      barGap: 2,
      barRadius: 2,
    });
    waveRef.current = wave;
    onReady(wave);
    void fetch(src, { credentials: "include", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`Recording request failed: ${response.status}`);
        objectUrl = URL.createObjectURL(await response.blob());
        await wave.load(objectUrl);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError"))
          setState("error");
      });
    wave.on("ready", (readyDuration) => {
      setDuration(readyDuration);
      setState("ready");
    });
    wave.on("error", () => setState("error"));
    wave.on("play", () => setPlaying(true));
    wave.on("pause", () => setPlaying(false));
    wave.on("finish", () => setPlaying(false));
    wave.on("timeupdate", (seconds) => {
      setCurrent(seconds);
      onTimeUpdate(seconds);
    });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      waveRef.current = null;
      onReady(null);
      wave.destroy();
    };
  }, [onReady, onTimeUpdate, src]);

  return (
    <div className="waveform-player">
      <Button
        className="waveform-toggle"
        disabled={state === "error"}
        onClick={() => waveRef.current?.playPause()}
        type="button"
        aria-label={playing ? "Pause call recording" : "Play call recording"}
      >
        {state === "loading" ? "Loading…" : playing ? "Pause" : "Play"}
      </Button>
      <div
        className="waveform-track"
        ref={containerRef}
        aria-label="Call recording waveform"
        role="img"
      />
      <output className="recording-clock" aria-live="polite">
        {state === "loading"
          ? "Preparing waveform…"
          : `${formatClock(current)} / ${formatClock(duration)}`}
      </output>
      {state === "error" ? (
        <p className="waveform-error" role="alert">
          Recording could not be loaded. Try downloading it instead.
        </p>
      ) : null}
    </div>
  );
}

function turnOffsetSeconds(turn: Trace["turns"][number], trace: Trace) {
  return Math.max(
    0,
    (new Date(turn.started_at).getTime() -
      new Date(trace.session.started_at).getTime()) /
      1000,
  );
}

function valueLabel(value: unknown) {
  if (typeof value === "string" || typeof value === "number")
    return String(value);
  return null;
}

function TraceWaterfall({ trace }: { trace: Trace }) {
  const start = new Date(trace.session.started_at).getTime();
  const observedEnd = Math.max(
    start + 1,
    ...trace.spans.map((span) => {
      if (span.ended_at) return new Date(span.ended_at).getTime();
      if (span.duration_ms !== null)
        return new Date(span.started_at).getTime() + span.duration_ms;
      return new Date(span.started_at).getTime();
    }),
  );
  const total = Math.max(1, observedEnd - start);
  const byExternalId = new Map(
    trace.spans.map((span) => [span.external_span_id, span]),
  );
  const depthFor = (span: Trace["spans"][number]) => {
    let depth = 0;
    let parent = span.parent_external_span_id;
    const visited = new Set<string>();
    while (
      parent &&
      byExternalId.has(parent) &&
      !visited.has(parent) &&
      depth < 8
    ) {
      visited.add(parent);
      depth += 1;
      parent = byExternalId.get(parent)?.parent_external_span_id ?? null;
    }
    return depth;
  };

  if (!trace.spans.length)
    return (
      <p className="analysis-pending">
        No canonical spans were captured for this trace.
      </p>
    );

  return (
    <div
      className="grid min-w-[560px] gap-2"
      aria-label="Nested trace waterfall"
    >
      <div className="grid grid-cols-[minmax(150px,260px)_minmax(260px,1fr)_88px] gap-3 px-3 text-xs font-semibold text-muted-foreground">
        <span>Operation</span>
        <span>Relative timeline</span>
        <span className="text-right">Duration</span>
      </div>
      {trace.spans.map((span) => {
        const left = Math.max(
          0,
          ((new Date(span.started_at).getTime() - start) / total) * 100,
        );
        const width = Math.max(1.25, ((span.duration_ms ?? 0) / total) * 100);
        const run = trace.agent_runs.find(
          (item) => item.id === span.agent_run_id,
        );
        const identity = [
          run?.agent ?? run?.name,
          run?.version,
          valueLabel(span.attributes.provider),
          valueLabel(span.attributes.model),
        ]
          .filter(Boolean)
          .join(" · ");
        const hasCapturedData = span.input !== null || span.output !== null;
        const capturedJson = JSON.stringify(
          { input: span.input, output: span.output },
          null,
          2,
        );
        const captureLimited =
          /\[(?:REDACTED|EXCLUDED|OMITTED|TRUNCATED)/i.test(capturedJson);
        const failed =
          span.status === "error" || span.status === "timeout";
        return (
          <details
            className="group grid grid-cols-[minmax(150px,260px)_minmax(260px,1fr)_88px] gap-3 rounded-lg px-3 py-2 hover:bg-accent/50"
            id={`span-${span.id}`}
            key={span.id}
          >
            <summary className="contents cursor-pointer list-none">
              <span
                className="min-w-0"
                style={{ paddingInlineStart: `${depthFor(span) * 14}px` }}
              >
                <b
                  className="block truncate text-sm font-medium text-foreground"
                  title={span.name}
                >
                  {span.name}
                </b>
                <small
                  className="block truncate text-xs text-muted-foreground"
                  title={`${span.kind}${identity ? ` · ${identity}` : ""}`}
                >
                  {span.kind}
                  {identity ? ` · ${identity}` : ""}
                </small>
              </span>
              <span className="relative my-1 min-h-8 overflow-hidden rounded bg-muted">
                <i
                  className={cn(
                    "absolute top-1/2 h-3 -translate-y-1/2 rounded",
                    failed ? "bg-destructive" : "bg-chart-2",
                  )}
                  style={{
                    left: `${Math.min(left, 98)}%`,
                    width: `${Math.min(width, 100 - Math.min(left, 98))}%`,
                  }}
                />
              </span>
              <span className="self-center text-right text-xs tabular-nums text-muted-foreground">
                {formatLatency(span.duration_ms)}
              </span>
            </summary>
            <div className="col-span-3 mt-1 grid gap-2 rounded-lg bg-foreground p-3 text-xs text-background">
              <span>
                Status: {span.status} · Source: {span.source ?? "unknown"}
                {captureLimited
                  ? " · Some captured values were redacted or omitted"
                  : ""}
              </span>
              {hasCapturedData ? (
                <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words">
                  {capturedJson}
                </pre>
              ) : (
                <span>
                  Input and output were not captured or were omitted by capture
                  policy.
                </span>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}

export function TracePanel({
  trace,
  loading = false,
  apiBaseUrl,
  projectSlug,
  reanalyzing,
  reanalysisError,
  onReanalyze,
  onEventPage,
}: {
  trace: Trace | null;
  loading?: boolean;
  apiBaseUrl: string;
  projectSlug: string;
  reanalyzing: boolean;
  reanalysisError: string | null;
  onReanalyze(): void;
  onEventPage?(offset: number): void;
}) {
  if (!trace)
    return (
      <Card className="overflow-hidden" id="trace">
        <CardHeader>
          <Eyebrow>Session trace</Eyebrow>
          <H2>
            {loading ? "Loading session…" : "Select a session"}
          </H2>
          <p className="text-sm text-muted-foreground">
            {loading
              ? "Fetching the trace, transcript, and evidence for this call."
              : "Choose a persisted session to inspect its timeline."}
          </p>
        </CardHeader>
        {loading ? (
          <CardContent>
            <LoadingSkeleton rows={7} />
          </CardContent>
        ) : null}
      </Card>
    );
  return (
    <TracePanelContent
      key={`${trace.session.id}-${trace.event_page?.offset ?? 0}`}
      {...{
        trace,
        apiBaseUrl,
        projectSlug,
        reanalyzing,
        reanalysisError,
        onReanalyze,
        onEventPage,
      }}
    />
  );
}

function TracePanelContent({
  trace,
  apiBaseUrl,
  projectSlug,
  reanalyzing,
  reanalysisError,
  onReanalyze,
  onEventPage,
}: {
  trace: Trace;
  apiBaseUrl: string;
  projectSlug: string;
  reanalyzing: boolean;
  reanalysisError: string | null;
  onReanalyze(): void;
  onEventPage?(offset: number): void;
}) {
  const [showRaw, setShowRaw] = useState(false);
  const [activeTab, setActiveTab] = useState(() =>
    trace.recordings.some((item) => item.status === "available")
      ? "playback"
      : "transcript",
  );
  const [activeRecordingId] = useState(
    () =>
      trace.recordings.find((item) => item.status === "available")?.id ?? null,
  );
  const [playheadSeconds, setPlayheadSeconds] = useState(0);
  const [seekNotice, setSeekNotice] = useState("");
  const [shareCopied, setShareCopied] = useState(false);
  const waveformRef = useRef<WaveSurfer | null>(null);
  const pendingSeekRef = useRef<number | null>(null);
  const handleWaveReady = useCallback((wave: WaveSurfer | null) => {
    waveformRef.current = wave;
    if (wave && pendingSeekRef.current !== null) {
      wave.setTime(pendingSeekRef.current);
      void wave.play();
      pendingSeekRef.current = null;
    }
  }, []);
  const handleWaveTimeUpdate = useCallback((seconds: number) => {
    setPlayheadSeconds(seconds);
  }, []);
  const activeRecording = trace.recordings.find(
    (recording) => recording.id === activeRecordingId,
  );
  const primaryFinding = trace.findings[0];
  const usage = trace.usage ?? [];
  const costs = trace.costs ?? [];
  const totalTokens = usage.reduce(
    (sum, item) => sum + (item.total_tokens ?? 0),
    0,
  );
  const totalCost = costs.reduce((sum, item) => sum + item.amount_micros, 0);
  const behavior = trace.voice_behavior ?? {
    interruptions: 0,
    talk_over: 0,
    dead_air: 0,
    corrections: 0,
    abandonment: 0,
  };
  const collection = trace.collection ?? {
    last_event_type: trace.events.at(-1)?.event_type ?? null,
    last_event_at: trace.events.at(-1)?.occurred_at ?? null,
    last_received_at: null,
    terminal_event_received: ["completed", "failed", "cancelled", "incomplete"].includes(
      trace.session.status,
    ),
    diagnostic_log: `logs/sessions/${trace.session.id}.jsonl`,
  };
  const timelineDurationSeconds = Math.max(
    (trace.session.duration_ms ?? 0) / 1000,
    ...trace.turns.map((turn) => {
      const end = turn.ended_at ?? turn.started_at;
      return Math.max(
        1,
        (new Date(end).getTime() - new Date(trace.session.started_at).getTime()) / 1000,
      );
    }),
    ...trace.events.map((event) =>
      Math.max(
        1,
        (new Date(event.occurred_at).getTime() - new Date(trace.session.started_at).getTime()) / 1000,
      ),
    ),
    1,
  );
  const observedTurnGaps = trace.turns.slice(0, -1).flatMap((turn, index) => {
    if (!turn.ended_at) return [];
    const next = trace.turns[index + 1];
    const start = Math.max(
      0,
      (new Date(turn.ended_at).getTime() -
        new Date(trace.session.started_at).getTime()) /
        1000,
    );
    const end = Math.max(
      start,
      (new Date(next.started_at).getTime() -
        new Date(trace.session.started_at).getTime()) /
        1000,
    );
    return end - start > 2.5 ? [{ start, end, key: `${turn.id}-${next.id}` }] : [];
  });

  function seekToOffset(seconds: number, label: string) {
    if (!activeRecording) return;
    setPlayheadSeconds(seconds);
    setSeekNotice(`Seeking to ${label} at ${formatClock(seconds)}.`);
    if (waveformRef.current) {
      waveformRef.current.setTime(seconds);
      void waveformRef.current.play();
    } else {
      pendingSeekRef.current = seconds;
      setActiveTab("playback");
    }
  }

  function seekToTurn(turn: Trace["turns"][number]) {
    if (!activeRecording) return;
    const offset = turnOffsetSeconds(turn, trace);
    seekToOffset(offset, turn.speaker);
  }

  function revealEvidence(target: {
    event_id: string | null;
    span_id: string | null;
    turn_id: string | null;
  }) {
    setActiveTab(target.turn_id && !target.span_id ? "transcript" : "events");
    const targetId = target.span_id
      ? `span-${target.span_id}`
      : target.turn_id
        ? `turn-${target.turn_id}`
        : target.event_id
          ? `event-${target.event_id}`
          : null;
    if (!targetId) return;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const targetElement = document.getElementById(targetId);
        if (typeof targetElement?.scrollIntoView === "function")
          targetElement.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    });
  }

  return (
    <Card className="overflow-hidden" id="trace">
      <CardHeader className="flex flex-col gap-3 border-b border-border sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <Eyebrow>Session trace</Eyebrow>
          <H2
            className="truncate"
            title={trace.session.external_session_id}
          >
            {trace.session.external_session_id}
          </H2>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <Badge variant={statusMeta(trace.session.status).variant}>
              {statusMeta(trace.session.status).label}
            </Badge>
            <span>
              {trace.session.status === "incomplete"
                ? "Collection ended without a terminal event"
                : trace.session.status === "in_progress"
                  ? "Receiving trace events"
                  : "Trace collection complete"}
            </span>
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="w-fit"
          onClick={() => {
            void navigator.clipboard?.writeText(window.location.href);
            setShareCopied(true);
            toast.success("Session link copied");
            window.setTimeout(() => setShareCopied(false), 1800);
          }}
        >
          <Share2 size={14} /> {shareCopied ? "Copied" : "Share"}
        </Button>
      </CardHeader>

      <dl className="grid grid-cols-2 gap-2 px-4 py-4 sm:grid-cols-3 xl:grid-cols-7">
        {[
          ["Status", trace.session.status],
          [
            "Intent",
            trace.session.intent
              ? `${trace.session.intent.replaceAll("_", " ")}${trace.session.intent_confidence != null ? ` · ${Math.round(trace.session.intent_confidence * 100)}%` : ""}`
              : "Not observed",
          ],
          [
            "Outcome",
            trace.session.outcome
              ? `${trace.session.outcome} · ${trace.session.outcome_source ?? "unknown source"}`
              : "Unknown",
          ],
          ["Session latency", formatLatency(trace.session.duration_ms)],
          [
            "Usage",
            totalTokens
              ? `${totalTokens.toLocaleString()} tokens`
              : "Not reported",
          ],
          [
            "Cost",
            costs.length
              ? `${formatCost(totalCost)} ${costs.some((item) => item.is_estimate) ? "estimated" : "exact"}`
              : "Not reported",
          ],
          ["Errors", trace.errors.length.toLocaleString()],
        ].map(([label, value]) => (
          <div
            className="min-w-0 rounded-lg border border-border bg-card px-3 py-2"
            key={label}
          >
            <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
            <dd
              className="mt-1 truncate text-sm font-semibold text-foreground"
              title={value}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>

      <section
        className={cn(
          "flex flex-col gap-2 border-y px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between",
          trace.session.status === "incomplete"
            ? "border-warning/30 bg-warning-soft"
            : "border-border bg-muted/40",
        )}
        aria-label="Trace collection health"
      >
        <div className="flex flex-wrap items-center gap-2">
          {trace.session.status === "incomplete" ? (
            <AlertTriangle className="size-4 shrink-0 text-warning" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden="true" />
          )}
          <b className="font-medium text-foreground">
            {trace.session.status === "incomplete"
              ? "Trace collection stopped before the session closed"
              : collection.terminal_event_received
                ? "Trace collection finalized"
                : "Trace collection is active"}
          </b>
          <span className="text-muted-foreground">
            {collection.last_event_type
              ? `Last event: ${collection.last_event_type}`
              : "No events received yet"}
            {collection.last_event_at
              ? ` · ${new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(new Date(collection.last_event_at))}`
              : ""}
          </span>
        </div>
        <code
          className="max-w-full truncate rounded bg-background/70 px-2 py-0.5 text-xs text-muted-foreground"
          title="Session diagnostic log path"
        >
          {collection.diagnostic_log}
        </code>
      </section>

      <section aria-label="Call state" className="grid gap-3 p-4 sm:grid-cols-3">
        <div className="rounded-lg border border-border bg-card p-3">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Intent evidence
          </p>
          <p className="mt-1 text-sm font-semibold text-foreground">
            {trace.session.intent ? trace.session.intent.replaceAll("_", " ") : "No routed intent captured"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {trace.session.intent_source ?? "The agent did not emit intent evidence."}
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card p-3">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Resolution
          </p>
          <p className="mt-1 text-sm font-semibold text-foreground">
            {trace.session.outcome ? trace.session.outcome.replaceAll("_", " ") : "Outcome not observed"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {trace.session.outcome_source ?? "No result event was received."}
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card p-3">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            Voice quality
          </p>
          <p className="mt-1 text-sm font-semibold text-foreground">
            {behavior.interruptions} interruptions · {behavior.dead_air} dead-air events
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {behavior.talk_over} talk-over · {behavior.corrections} corrections
          </p>
        </div>
      </section>

      <section
        className="conversation-timeline"
        aria-labelledby="conversation-timeline-heading"
      >
        <div className="conversation-timeline-heading">
          <div>
            <h3 id="conversation-timeline-heading">Conversation timeline</h3>
            <p>Open a turn or voice event at its recorded point in the call.</p>
          </div>
          <div
            className="conversation-timeline-legend"
            aria-label="Timeline legend"
          >
            <span>
              <i className="customer" /> Customer
            </span>
            <span>
              <i className="agent" /> Agent
            </span>
            <span>
              <i className="interruption" /> Interruption
            </span>
            <span>
              <i className="dead-air" /> Dead air
            </span>
          </div>
        </div>
        <div className="conversation-timeline-track">
          {trace.turns.map((turn) => {
            const start = turnOffsetSeconds(turn, trace);
            const end = turn.ended_at
              ? Math.max(
                  start + 1,
                  (new Date(turn.ended_at).getTime() -
                    new Date(trace.session.started_at).getTime()) /
                    1000,
                )
              : start + 3;
            return (
              <button
                key={turn.id}
                className={`timeline-segment ${turn.speaker === "customer" ? "customer" : "agent"}`}
                style={{
                  left: `${Math.min(99, (start / timelineDurationSeconds) * 100)}%`,
                  width: `${Math.max(1.5, ((end - start) / timelineDurationSeconds) * 100)}%`,
                }}
                title={`${turn.speaker} at ${formatClock(start)}`}
                aria-label={`Open ${turn.speaker} turn at ${formatClock(start)}`}
                onClick={() =>
                  activeRecording
                    ? seekToTurn(turn)
                    : revealEvidence({ event_id: null, span_id: null, turn_id: turn.id })
                }
              />
            );
          })}
          {trace.events
            .filter(
              (event) =>
                event.event_type === "voice.interruption" ||
                event.event_type === "voice.dead_air" ||
                event.event_type === "voice.dead-air",
            )
            .map((event) => {
              const total = timelineDurationSeconds;
              const start = Math.max(
                0,
                (new Date(event.occurred_at).getTime() -
                  new Date(trace.session.started_at).getTime()) /
                  1000,
              );
              const kind =
                event.event_type === "voice.interruption"
                  ? "interruption"
                  : "dead-air";
              return (
                <button
                  key={event.id}
                  className={`timeline-segment ${kind}`}
                  style={{
                    left: `${Math.min(99, (start / total) * 100)}%`,
                    width: `${Math.max(1.2, ((event.duration_ms ?? 800) / 1000 / total) * 100)}%`,
                  }}
                  title={`${event.event_type} at ${formatClock(start)}`}
                  aria-label={`Open ${event.event_type} at ${formatClock(start)}`}
                  onClick={() =>
                    revealEvidence({
                      event_id: event.id,
                      span_id: null,
                      turn_id: null,
                    })
                  }
                />
            );
          })}
          {observedTurnGaps.map((gap) => (
            <button
              aria-label={`Seek to observed dead air at ${formatClock(gap.start)}`}
              className="timeline-segment dead-air"
              disabled={!activeRecording}
              key={gap.key}
              onClick={() => seekToOffset(gap.start, "observed dead air")}
              style={{
                left: `${Math.min(99, (gap.start / timelineDurationSeconds) * 100)}%`,
                width: `${Math.max(1.2, ((gap.end - gap.start) / timelineDurationSeconds) * 100)}%`,
              }}
              title={`Observed dead air at ${formatClock(gap.start)}`}
            />
          ))}
        </div>
        <div className="conversation-timeline-scale" aria-hidden="true">
          <span>0:00</span>
          <span>{formatClock(timelineDurationSeconds / 2)}</span>
          <span>{formatClock(timelineDurationSeconds)}</span>
        </div>
        <p className="sr-only" aria-live="polite">
          {shareCopied ? "Session link copied to clipboard." : ""}
        </p>
      </section>

      <Tabs
        value={activeTab}
        onValueChange={setActiveTab}
        className="border-t border-border p-5"
      >
        <TabsList variant="line" className="mb-5 gap-5 p-0">
          {activeRecording ? <TabsTrigger value="playback" className="px-0">Playback</TabsTrigger> : null}
          <TabsTrigger value="transcript" className="px-0">
            Transcript
          </TabsTrigger>
          <TabsTrigger value="analysis" className="px-0">
            Analysis
          </TabsTrigger>
          <TabsTrigger value="events" className="px-0">
            Trace & events
          </TabsTrigger>
        </TabsList>

        <TabsContent value="playback">
          {activeRecording ? (
            <div className="flex flex-col gap-4 rounded-xl border border-border bg-muted/40 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <b className="block text-sm font-medium text-foreground">
                    Call recording
                  </b>
                  <small className="text-xs text-muted-foreground">
                    {activeRecording.source} ·{" "}
                    {formatLatency(activeRecording.duration_ms)}
                  </small>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  {activeRecording.expires_at ? (
                    <small className="text-xs text-muted-foreground">
                      Available until{" "}
                      {new Intl.DateTimeFormat().format(
                        new Date(activeRecording.expires_at),
                      )}
                    </small>
                  ) : null}
                  <Button asChild size="sm" variant="outline">
                    <a
                      href={`${apiBaseUrl}/api/projects/${projectSlug}/sessions/${trace.session.id}/recordings/${activeRecording.id}/playback`}
                    >
                      <Download aria-hidden="true" size={13} /> Download
                    </a>
                  </Button>
                </div>
              </div>
              <WaveformPlayer
                onReady={handleWaveReady}
                onTimeUpdate={handleWaveTimeUpdate}
                src={`${apiBaseUrl}/api/projects/${projectSlug}/sessions/${trace.session.id}/recordings/${activeRecording.id}/playback`}
              />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {trace.recordings.length
                ? `Recording is ${trace.recordings[0].status}; playback is unavailable.`
                : "No recording was attached. Trace investigation remains fully available."}
            </p>
          )}
        </TabsContent>

        <TabsContent value="transcript">
          <section className="flex flex-col gap-2" aria-label="Transcript">
            {trace.turns.length ? (
              trace.turns.map((turn, index) => {
                const offset = turnOffsetSeconds(turn, trace);
                const nextTurn = trace.turns[index + 1];
                const active = Boolean(
                  activeRecording &&
                  playheadSeconds >= offset &&
                  (!nextTurn ||
                    playheadSeconds < turnOffsetSeconds(nextTurn, trace)),
                );
                return (
                  <button
                    type="button"
                    className={cn(
                      "flex w-full flex-col items-start gap-1 rounded-lg border border-border bg-card px-3 py-2 text-left transition-colors hover:bg-accent/60",
                      active && "border-primary/50 bg-primary/5",
                    )}
                    id={`turn-${turn.id}`}
                    key={turn.id}
                    onClick={() =>
                      activeRecording
                        ? seekToTurn(turn)
                        : revealEvidence({ event_id: null, span_id: null, turn_id: turn.id })
                    }
                  >
                    <b className="text-xs font-semibold tracking-wide text-primary uppercase">
                      {turn.speaker} · {formatLatency(offset * 1000)}
                    </b>
                    <span className="text-sm text-foreground">
                      {turn.transcript ?? "Transcript omitted or not captured"}
                    </span>
                  </button>
                );
              })
            ) : (
              <p className="text-sm text-muted-foreground">
                No transcript was captured for this trace.
              </p>
            )}
          </section>
        </TabsContent>

        <TabsContent value="analysis" className="grid gap-5">
          <section
            className="grid grid-cols-2 gap-3 sm:grid-cols-5"
            aria-label="Voice behavior summary"
          >
            {Object.entries(behavior).map(([label, value]) => (
              <div
                className="rounded-lg border border-border bg-card p-3"
                key={label}
              >
                <b className="block text-lg tabular-nums text-foreground">
                  {value}
                </b>
                <span className="text-xs text-muted-foreground capitalize">
                  {label.replaceAll("_", "-")}
                </span>
              </div>
            ))}
          </section>
          {primaryFinding ? (
            <section
              className="grid gap-4 rounded-xl border border-destructive/20 bg-destructive-soft p-4 text-sm text-foreground md:grid-cols-[minmax(0,1fr)_190px]"
              aria-label="Key takeaway"
            >
              <div>
                <div className="mb-2 flex items-center gap-2 font-semibold text-destructive">
                  <AlertTriangle size={16} /> Key takeaway
                </div>
                <strong className="block text-base">
                  {certaintyLabel(primaryFinding.certainty)}:{" "}
                  {primaryFinding.statement}
                </strong>
                {primaryFinding.confidence !== null &&
                primaryFinding.certainty === "inferred_contributing_factor" ? (
                  <p className="mt-2 text-xs">
                    Confidence {Math.round(primaryFinding.confidence * 100)}%
                  </p>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-2">
                  {primaryFinding.evidence.map((evidence) => (
                    <Button
                      key={evidence.entity_id}
                      size="sm"
                      variant="outline"
                      onClick={() => revealEvidence(evidence)}
                    >
                      <ExternalLink size={13} /> View {evidence.entity_type}
                    </Button>
                  ))}
                </div>
              </div>
              <div className="rounded-lg border border-border bg-card p-3">
                <div className="flex items-center gap-2 text-xs font-semibold text-primary">
                  <Zap size={15} /> Next inspection
                </div>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">
                  {String(
                    primaryFinding.attributes.next_step ??
                      "Review the linked evidence before changing the agent configuration.",
                  )}
                </p>
              </div>
            </section>
          ) : (
            <p className="text-sm text-muted-foreground">
              No findings yet. The canonical trace remains the source of truth.
            </p>
          )}
          <div className="flex flex-col gap-2">
            {trace.findings.map((finding) => (
              <div
                className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3"
                key={finding.id}
              >
                <div className="flex items-center gap-2">
                  <Badge
                    variant={
                      finding.severity === "high" || finding.severity === "critical"
                        ? "destructive"
                        : finding.severity === "medium"
                          ? "warning"
                          : "secondary"
                    }
                  >
                    {certaintyLabel(finding.certainty)}
                  </Badge>
                  {finding.severity ? (
                    <span className="text-xs font-medium text-muted-foreground capitalize">
                      {finding.severity} severity
                    </span>
                  ) : null}
                </div>
                <span className="text-sm text-foreground">
                  {finding.statement}
                </span>
                {finding.evidence.length ? (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {finding.evidence.map((evidence) => (
                      <Button
                        key={`${evidence.entity_type}-${evidence.entity_id}`}
                        type="button"
                        size="xs"
                        variant="secondary"
                        onClick={() => revealEvidence(evidence)}
                      >
                        View {evidence.entity_type}
                      </Button>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
          <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <b className="text-sm font-medium text-foreground">
                  Analysis history
                </b>
                <span className="ml-2 text-xs text-muted-foreground">
                  {trace.analysis_runs.length} immutable runs
                </span>
              </div>
              <Button
                disabled={reanalyzing}
                onClick={onReanalyze}
                size="sm"
                variant="outline"
              >
                <RotateCcw size={13} />
                {reanalyzing ? "Queueing…" : "Re-analyze"}
              </Button>
            </div>
            {trace.analysis_runs.map((run) => (
              <small
                className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground"
                key={run.id}
              >
                <Badge
                  variant={
                    run.status === "completed"
                      ? "success"
                      : run.status === "failed"
                        ? "destructive"
                        : "info"
                  }
                >
                  {run.status.replaceAll("_", " ")}
                </Badge>
                <span>
                  v{run.analysis_version} · {run.prompt_version}
                  {run.model ? ` · ${run.model}` : ""}
                </span>
                {run.evaluator_latency_ms !== null ? (
                  <span>{formatLatency(run.evaluator_latency_ms)}</span>
                ) : null}
                {run.error ? (
                  <span className="text-destructive">{run.error}</span>
                ) : null}
              </small>
            ))}
            {reanalysisError ? (
              <p className="text-sm text-destructive" role="alert">
                Analysis could not be queued: {reanalysisError}
              </p>
            ) : null}
          </div>
        </TabsContent>

        <TabsContent value="events" className="grid gap-5">
          <section>
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <H3>Execution waterfall</H3>
                <p className="mt-1 text-xs text-muted-foreground">
                  Nested spans share one relative timeline; overlaps remain
                  visible.
                </p>
              </div>
              <Waypoints className="text-primary" size={20} />
            </div>
            <div className="overflow-x-auto">
              <TraceWaterfall trace={trace} />
            </div>
          </section>
          {trace.errors.length ? (
            <section className="grid gap-2" aria-label="Trace errors">
              {trace.errors.map((item) => (
                <Button
                  className="h-auto justify-start gap-3 whitespace-normal border-destructive/20 bg-destructive-soft p-3 text-left text-destructive hover:bg-destructive-soft/70"
                  key={item.id}
                  variant="outline"
                  onClick={() =>
                    revealEvidence({
                      span_id: item.span_id,
                      event_id: item.event_id,
                      turn_id: null,
                    })
                  }
                >
                  <AlertTriangle size={15} />
                  <span>
                    <b>{item.type}</b>
                    <small className="block">{item.message}</small>
                  </span>
                </Button>
              ))}
            </section>
          ) : null}
          <section>
            <div className="mb-3 flex items-center justify-between gap-3">
              <H3>Normalized events</H3>
              <span className="text-xs text-muted-foreground">
                {trace.event_page.total} total
              </span>
            </div>
            <ol className="flex flex-col gap-2">
              {trace.events.map((event) => (
                <li
                  className="flex items-start gap-3 rounded-lg border border-border bg-card px-3 py-2"
                  id={`event-${event.id}`}
                  key={event.id}
                >
                  <span
                    className={cn(
                      "mt-1.5 size-2 shrink-0 rounded-full",
                      event.status === "error" || event.status === "timeout"
                        ? "bg-destructive"
                        : "bg-chart-2",
                    )}
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <b className="block text-sm font-medium text-foreground">
                      {event.event_type}
                    </b>
                    <small className="text-xs text-muted-foreground">
                      {new Intl.DateTimeFormat(undefined, {
                        hour: "numeric",
                        minute: "2-digit",
                        second: "2-digit",
                      }).format(new Date(event.occurred_at))}{" "}
                      · {formatLatency(event.duration_ms)}
                    </small>
                  </div>
                </li>
              ))}
            </ol>
            {trace.event_page.total > trace.event_page.limit ? (
              <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={trace.event_page.offset === 0}
                  onClick={() =>
                    onEventPage?.(
                      Math.max(
                        0,
                        trace.event_page.offset - trace.event_page.limit,
                      ),
                    )
                  }
                >
                  Previous events
                </Button>
                <span className="tabular-nums">
                  {trace.event_page.offset + 1}–
                  {Math.min(
                    trace.event_page.offset + trace.event_page.limit,
                    trace.event_page.total,
                  )}{" "}
                  of {trace.event_page.total}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={
                    trace.event_page.offset + trace.event_page.limit >=
                    trace.event_page.total
                  }
                  onClick={() =>
                    onEventPage?.(
                      trace.event_page.offset + trace.event_page.limit,
                    )
                  }
                >
                  Next events
                </Button>
              </div>
            ) : null}
          </section>
          <Button
            variant="outline"
            size="sm"
            className="w-fit"
            onClick={() => setShowRaw(!showRaw)}
            aria-expanded={showRaw}
          >
            {showRaw ? "Hide" : "Inspect"} normalized event JSON
          </Button>
          {showRaw ? (
            <pre className="max-h-96 overflow-auto rounded-lg bg-foreground p-3 text-xs text-background">
              {JSON.stringify(trace.events, null, 2)}
            </pre>
          ) : null}
        </TabsContent>
      </Tabs>
      <p
        className="min-h-5 px-5 pb-4 text-xs text-muted-foreground"
        aria-live="polite"
      >
        {seekNotice}
      </p>
    </Card>
  );
}
