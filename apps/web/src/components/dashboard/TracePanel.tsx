import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Download,
  ExternalLink,
  RotateCcw,
  Share2,
  Waypoints,
  Zap,
} from "lucide-react";
import WaveSurfer from "wavesurfer.js";

import type { Trace } from "@/components/dashboard/types";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

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
    <div className="grid min-w-[560px] gap-2" aria-label="Nested trace waterfall">
      <div className="grid grid-cols-[minmax(150px,260px)_minmax(260px,1fr)_88px] gap-3 px-3 text-xs font-semibold text-slate-500">
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
        return (
          <details
            className="group grid grid-cols-[minmax(150px,260px)_minmax(260px,1fr)_88px] gap-3 rounded-lg px-3 py-2 hover:bg-emerald-50/60"
            id={`span-${span.id}`}
            key={span.id}
          >
            <summary className="contents cursor-pointer list-none">
              <span
                className="min-w-0"
                style={{ paddingInlineStart: `${depthFor(span) * 14}px` }}
              >
                <b className="block truncate text-sm text-slate-800">
                  {span.name}
                </b>
                <small className="block truncate text-xs text-slate-500">
                  {span.kind}
                  {identity ? ` · ${identity}` : ""}
                </small>
              </span>
              <span className="relative my-1 min-h-8 overflow-hidden rounded bg-slate-100">
                <i
                  className={`absolute top-1/2 h-3 -translate-y-1/2 rounded ${span.status === "error" || span.status === "timeout" ? "bg-red-500" : "bg-emerald-600"}`}
                  style={{
                    left: `${Math.min(left, 98)}%`,
                    width: `${Math.min(width, 100 - Math.min(left, 98))}%`,
                  }}
                />
              </span>
              <span className="self-center text-right text-xs tabular-nums text-slate-600">
                {formatLatency(span.duration_ms)}
              </span>
            </summary>
            <div className="col-span-3 mt-1 grid gap-2 rounded-lg bg-slate-950 p-3 text-xs text-slate-200">
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
  apiBaseUrl,
  projectSlug,
  reanalyzing,
  reanalysisError,
  onReanalyze,
  onEventPage,
}: {
  trace: Trace | null;
  apiBaseUrl: string;
  projectSlug: string;
  reanalyzing: boolean;
  reanalysisError: string | null;
  onReanalyze(): void;
  onEventPage?(offset: number): void;
}) {
  if (!trace)
    return (
      <Card className="panel trace-panel" id="trace">
        <CardHeader className="panel-heading">
          <h2>Select a session</h2>
        </CardHeader>
        <p className="empty-state">
          Choose a persisted session to inspect its timeline.
        </p>
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
  const [activeTab, setActiveTab] = useState("playback");
  const [activeRecordingId] = useState(
    () =>
      trace.recordings.find((item) => item.status === "available")?.id ?? null,
  );
  const [playheadSeconds, setPlayheadSeconds] = useState(0);
  const [seekNotice, setSeekNotice] = useState("");
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

  function seekToTurn(turn: Trace["turns"][number]) {
    if (!activeRecording) return;
    const offset = turnOffsetSeconds(turn, trace);
    setPlayheadSeconds(offset);
    setSeekNotice(`Seeking to ${turn.speaker} at ${formatClock(offset)}.`);
    if (waveformRef.current) {
      waveformRef.current.setTime(offset);
      void waveformRef.current.play();
    } else {
      pendingSeekRef.current = offset;
      setActiveTab("playback");
    }
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
    <Card className="panel trace-panel" id="trace">
      <CardHeader className="panel-heading">
        <div className="min-w-0">
          <p className="eyebrow">Session detail</p>
          <h2 className="truncate">{trace.session.external_session_id}</h2>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            void navigator.clipboard?.writeText(window.location.href)
          }
        >
          <Share2 size={14} /> Share
        </Button>
      </CardHeader>

      <dl className="grid grid-cols-2 gap-px border-y border-slate-200 bg-slate-200 sm:grid-cols-3 lg:grid-cols-6">
        {[
          ["Status", trace.session.status],
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
          <div className="min-w-0 bg-white px-4 py-3" key={label}>
            <dt className="text-xs font-medium text-slate-500">{label}</dt>
            <dd className="mt-1 truncate text-sm font-semibold text-slate-800">
              {value}
            </dd>
          </div>
        ))}
      </dl>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="p-5">
        <TabsList variant="line" className="mb-5 gap-5 p-0">
          <TabsTrigger value="playback" className="px-0">
            Playback
          </TabsTrigger>
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
            <div className="recording-player">
              <div>
                <b>Call recording</b>
                <small>
                  {activeRecording.source} ·{" "}
                  {formatLatency(activeRecording.duration_ms)}
                </small>
              </div>
              <WaveformPlayer
                onReady={handleWaveReady}
                onTimeUpdate={handleWaveTimeUpdate}
                src={`${apiBaseUrl}/api/projects/${projectSlug}/sessions/${trace.session.id}/recordings/${activeRecording.id}/playback`}
              />
              <Button
                asChild
                className="recording-download"
                size="sm"
                variant="outline"
              >
                <a
                  href={`${apiBaseUrl}/api/projects/${projectSlug}/sessions/${trace.session.id}/recordings/${activeRecording.id}/playback`}
                >
                  <Download aria-hidden="true" size={13} /> Download
                </a>
              </Button>
              {activeRecording.expires_at ? (
                <small>
                  Available until{" "}
                  {new Intl.DateTimeFormat().format(
                    new Date(activeRecording.expires_at),
                  )}
                </small>
              ) : null}
            </div>
          ) : (
            <p className="analysis-pending">
              {trace.recordings.length
                ? `Recording is ${trace.recordings[0].status}; playback is unavailable.`
                : "No recording was attached. Trace investigation remains fully available."}
            </p>
          )}
        </TabsContent>

        <TabsContent value="transcript">
          <section className="transcript-panel !p-0" aria-label="Transcript">
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
                  <Button
                    variant="ghost"
                    className={`transcript-turn ${active ? "playing" : ""}`}
                    disabled={!activeRecording}
                    id={`turn-${turn.id}`}
                    key={turn.id}
                    onClick={() => seekToTurn(turn)}
                  >
                    <b>
                      {turn.speaker} · {formatLatency(offset * 1000)}
                    </b>
                    <span>
                      {turn.transcript ?? "Transcript omitted or not captured"}
                    </span>
                  </Button>
                );
              })
            ) : (
              <p className="analysis-pending">
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
              <div className="rounded-lg bg-slate-50 p-3" key={label}>
                <b className="block text-lg tabular-nums text-slate-800">
                  {value}
                </b>
                <span className="text-xs capitalize text-slate-500">
                  {label.replaceAll("_", "-")}
                </span>
              </div>
            ))}
          </section>
          {primaryFinding ? (
            <section
              className="grid gap-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-950 md:grid-cols-[minmax(0,1fr)_190px]"
              aria-label="Key takeaway"
            >
              <div>
                <div className="mb-2 flex items-center gap-2 font-semibold text-red-800">
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
              <div className="rounded-md bg-white p-3 text-emerald-950">
                <div className="flex items-center gap-2 text-xs font-semibold">
                  <Zap size={15} /> Next inspection
                </div>
                <p className="mt-2 text-xs leading-5">
                  {String(
                    primaryFinding.attributes.next_step ??
                      "Review the linked evidence before changing the agent configuration.",
                  )}
                </p>
              </div>
            </section>
          ) : (
            <p className="analysis-pending">
              No findings yet. The canonical trace remains the source of truth.
            </p>
          )}
          <div className="finding-list">
            {trace.findings.map((finding) => (
              <div className="finding" key={finding.id}>
                <b>
                  {certaintyLabel(finding.certainty)}
                  {finding.severity ? ` · ${finding.severity}` : ""}
                </b>
                <span>{finding.statement}</span>
                {finding.evidence.length ? (
                  <div className="finding-evidence">
                    {finding.evidence.map((evidence) => (
                      <Button
                        key={`${evidence.entity_type}-${evidence.entity_id}`}
                        type="button"
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
          <div className="analysis-history">
            <div>
              <b>Analysis history</b>
              <span>{trace.analysis_runs.length} immutable runs</span>
            </div>
            <Button disabled={reanalyzing} onClick={onReanalyze}>
              <RotateCcw size={13} />
              {reanalyzing ? "Queueing…" : "Re-analyze"}
            </Button>
            {trace.analysis_runs.map((run) => (
              <small className="flex flex-wrap gap-x-2" key={run.id}>
                <b className={`analysis-status-${run.status}`}>
                  {run.status.replaceAll("_", " ")}
                </b>
                <span>
                  v{run.analysis_version} · {run.prompt_version}
                  {run.model ? ` · ${run.model}` : ""}
                </span>
                {run.evaluator_latency_ms !== null ? (
                  <span>{formatLatency(run.evaluator_latency_ms)}</span>
                ) : null}
                {run.error ? (
                  <span className="text-red-700">{run.error}</span>
                ) : null}
              </small>
            ))}
            {reanalysisError ? (
              <p className="trace-action-error" role="alert">
                Analysis could not be queued: {reanalysisError}
              </p>
            ) : null}
          </div>
        </TabsContent>

        <TabsContent value="events" className="grid gap-5">
          <section>
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold text-slate-800">
                  Execution waterfall
                </h3>
                <p className="mt-1 text-xs text-slate-500">
                  Nested spans share one relative timeline; overlaps remain
                  visible.
                </p>
              </div>
              <Waypoints className="text-emerald-700" size={20} />
            </div>
            <div className="overflow-x-auto">
              <TraceWaterfall trace={trace} />
            </div>
          </section>
          {trace.errors.length ? (
            <section className="grid gap-2" aria-label="Trace errors">
              {trace.errors.map((item) => (
                <Button
                  className="h-auto justify-start whitespace-normal border-red-200 bg-red-50 p-3 text-left text-red-900 hover:bg-red-100"
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
              <h3 className="text-base font-semibold text-slate-800">
                Normalized events
              </h3>
              <span className="text-xs text-slate-500">
                {trace.event_page.total} total
              </span>
            </div>
            <ol className="timeline">
              {trace.events.map((event) => (
                <li id={`event-${event.id}`} key={event.id}>
                  <span className={`timeline-dot ${event.status}`} />
                  <div>
                    <b>{event.event_type}</b>
                    <small>
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
              <div className="pagination">
                <Button
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
                <span>
                  {trace.event_page.offset + 1}–
                  {Math.min(
                    trace.event_page.offset + trace.event_page.limit,
                    trace.event_page.total,
                  )}{" "}
                  of {trace.event_page.total}
                </span>
                <Button
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
            className="raw-toggle"
            onClick={() => setShowRaw(!showRaw)}
            aria-expanded={showRaw}
          >
            {showRaw ? "Hide" : "Inspect"} normalized event JSON
          </Button>
          {showRaw ? (
            <pre className="raw-inspector">
              {JSON.stringify(trace.events, null, 2)}
            </pre>
          ) : null}
        </TabsContent>
      </Tabs>
      <p className="seek-feedback px-5 pb-4" aria-live="polite">
        {seekNotice}
      </p>
    </Card>
  );
}
