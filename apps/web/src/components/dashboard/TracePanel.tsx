import { useCallback, useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import { AlertTriangle, Download, MoreHorizontal, RotateCcw, Share2, Zap } from "lucide-react";

import { Card, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Trace } from "@/components/dashboard/types";

type TraceFilter = "all" | "agent" | "handoff";

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

function formatClock(seconds: number) {
  const rounded = Math.max(0, Math.floor(seconds));
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
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
    wave.load(src);
    setState("loading");
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
      waveRef.current = null;
      onReady(null);
      wave.destroy();
    };
  }, [onReady, onTimeUpdate, src]);
  return (
    <div className="waveform-player">
      <Button
        className="waveform-toggle"
        onClick={() => waveRef.current?.playPause()}
        type="button"
        aria-label={playing ? "Pause call recording" : "Play call recording"}
      >
        {state === "loading" ? "Loading…" : playing ? "Pause" : "Play"}
      </Button>
      <div className="waveform-track" ref={containerRef} aria-label="Call recording waveform" />
      <output className="recording-clock" aria-live="polite">
        {state === "loading" ? "Preparing waveform…" : `${formatClock(current)} / ${formatClock(duration)}`}
      </output>
      {state === "error" ? <p className="waveform-error" role="alert">Recording could not be loaded. Try downloading it instead.</p> : null}
    </div>
  );
}

function turnOffsetSeconds(
  turn: Trace["turns"][number],
  session: Trace["session"],
) {
  return Math.max(
    0,
    (new Date(turn.started_at).getTime() -
      new Date(session.started_at).getTime()) /
      1000,
  );
}

export function TracePanel({
  trace,
  apiBaseUrl,
  projectSlug,
  reanalyzing,
  reanalysisError,
  onReanalyze,
}: {
  trace: Trace | null;
  apiBaseUrl: string;
  projectSlug: string;
  reanalyzing: boolean;
  reanalysisError: string | null;
  onReanalyze(): void;
}) {
  if (!trace) {
    return (
      <Card className="panel trace-panel" id="trace">
        <CardHeader className="panel-heading">
          <div>
            <p className="eyebrow">Complete conversation trace</p>
            <h2>Select a session</h2>
          </div>
          <span>0 events</span>
        </CardHeader>
        <p className="empty-state">
          Choose a persisted session to inspect its timeline.
        </p>
      </Card>
    );
  }
  return (
    <TracePanelContent
      key={trace.session.id}
      trace={trace}
      apiBaseUrl={apiBaseUrl}
      projectSlug={projectSlug}
      reanalyzing={reanalyzing}
      reanalysisError={reanalysisError}
      onReanalyze={onReanalyze}
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
}: {
  trace: Trace;
  apiBaseUrl: string;
  projectSlug: string;
  reanalyzing: boolean;
  reanalysisError: string | null;
  onReanalyze(): void;
}) {
  const [showRaw, setShowRaw] = useState(false);
  const [traceFilter, setTraceFilter] = useState<TraceFilter>("all");
  const [activeRecordingId] = useState<string | null>(
    () =>
      trace.recordings.find((item) => item.status === "available")?.id ?? null,
  );
  const [playheadSeconds, setPlayheadSeconds] = useState(0);
  const [seekNotice, setSeekNotice] = useState("");
  const waveformRef = useRef<WaveSurfer | null>(null);
  const handleWaveReady = useCallback((wave: WaveSurfer | null) => {
    waveformRef.current = wave;
  }, []);
  const handleWaveTimeUpdate = useCallback((seconds: number) => {
    setPlayheadSeconds(seconds);
  }, []);

  const visibleEvents = trace?.events.filter((event) => {
    if (traceFilter === "all") return true;
    if (traceFilter === "handoff") return event.event_type === "agent.handoff";
    return (
      event.event_type.startsWith("agent.") ||
      event.event_type.startsWith("graph.")
    );
  });
  const activeRecording = trace?.recordings.find(
    (recording) => recording.id === activeRecordingId,
  );
  const primaryFinding = trace.findings[0];

  function seekToTurn(turn: Trace["turns"][number]) {
    if (!trace || !waveformRef.current || !activeRecording) return;
    const offset = turnOffsetSeconds(turn, trace.session);
    waveformRef.current.setTime(offset);
    setPlayheadSeconds(offset);
    setSeekNotice(`Seeking to ${turn.speaker} at ${formatClock(offset)}.`);
    void waveformRef.current.play();
  }

  function revealEvidence(target: { event_id: string | null; turn_id: string | null }) {
    setTraceFilter("all");
    const targetId = target.turn_id ? `turn-${target.turn_id}` : target.event_id ? `event-${target.event_id}` : null;
    if (!targetId) return;
    requestAnimationFrame(() => {
      const element = document.getElementById(targetId);
      element?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    });
  }

  return (
    <Card className="panel trace-panel" id="trace">
      <CardHeader className="panel-heading">
        <div>
          <p className="eyebrow">Session detail</p>
          <h2>
            {trace ? trace.session.external_session_id : "Select a session"}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" aria-label="Share session"><Share2 size={14} /></Button>
          <Button variant="outline" size="sm" aria-label="More session actions"><MoreHorizontal size={15} /></Button>
        </div>
      </CardHeader>
      {!trace ? (
        <p className="empty-state">
          Choose a persisted session to inspect its timeline.
        </p>
      ) : (
        <>
          <section className="transcript-panel" aria-label="Transcript">
            <Tabs defaultValue="playback" className="mb-4 border-b border-emerald-950/10">
              <TabsList variant="line" className="gap-4 p-0">
                <TabsTrigger value="playback" className="px-0 text-xs data-[state=active]:text-emerald-800">Playback</TabsTrigger>
                <TabsTrigger value="transcript" className="px-0 text-xs">Transcript</TabsTrigger>
                <TabsTrigger value="analysis" className="px-0 text-xs">Analysis</TabsTrigger>
                <TabsTrigger value="events" className="px-0 text-xs">Events</TabsTrigger>
              </TabsList>
            </Tabs>
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
                <Button asChild className="recording-download" size="sm" variant="outline">
                <a
                  href={`${apiBaseUrl}/api/projects/${projectSlug}/sessions/${trace.session.id}/recordings/${activeRecording.id}/playback`}
                >
                  <Download aria-hidden="true" size={13} /> Download
                </a>
                </Button>
              </div>
            ) : trace.recordings.length ? (
              <p className="analysis-pending">
                Recording {trace.recordings[0].status}; playback is unavailable.
              </p>
            ) : null}
            {trace.turns.length ? (
              trace.turns.map((turn, index) => {
                const offset = turnOffsetSeconds(turn, trace.session);
                const nextTurn = trace.turns[index + 1];
                const isActive =
                  activeRecording &&
                  playheadSeconds >= offset &&
                  (!nextTurn ||
                    playheadSeconds <
                      turnOffsetSeconds(nextTurn, trace.session));
                return (
                  <Button
                    variant="ghost"
                    className={`transcript-turn ${isActive ? "playing" : ""}`}
                    disabled={!activeRecording}
                    id={`turn-${turn.id}`}
                    key={turn.id}
                    onClick={() => seekToTurn(turn)}
                  >
                    <b>
                      {turn.speaker} · {formatLatency(offset * 1000)}
                    </b>
                    <span>{turn.transcript ?? "No transcript captured"}</span>
                  </Button>
                );
              })
            ) : (
              <p className="analysis-pending">
                No transcript was captured for this trace.
              </p>
            )}
            <p className="seek-feedback" aria-live="polite">{seekNotice}</p>
          </section>
          {primaryFinding ? (
            <section className="m-5 grid gap-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-950 md:grid-cols-[minmax(0,1fr)_180px]" aria-label="Key takeaways">
              <div>
                <div className="mb-2 flex items-center gap-2 font-semibold text-red-800"><AlertTriangle size={16} aria-hidden="true" /> Key takeaway</div>
                <strong className="block text-base">Likely root cause: {primaryFinding.statement}</strong>
                <p className="mt-2 text-xs leading-5 text-red-900/75">Every assertion links back to a captured transcript turn or trace event.</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {primaryFinding.evidence.map((evidence) => (
                    <Button key={evidence.entity_id} size="sm" variant="outline" className="border-red-200 bg-white text-red-800 hover:bg-red-100" onClick={() => revealEvidence(evidence)}>
                      View {evidence.turn_id ? "turn" : "event"}
                    </Button>
                  ))}
                </div>
              </div>
              <div className="rounded-md border border-emerald-200 bg-white p-3 text-emerald-950">
                <div className="flex items-center gap-2 text-xs font-semibold"><Zap size={15} className="text-emerald-700" aria-hidden="true" /> Suggested action</div>
                <p className="mt-2 text-xs leading-5 text-emerald-900/75">Review the linked evidence, then re-run analysis after changing the agent or provider configuration.</p>
                <Button className="mt-3 w-full" size="sm" onClick={onReanalyze} disabled={reanalyzing}><RotateCcw size={13} aria-hidden="true" /> {reanalyzing ? "Queueing…" : "Re-analyze trace"}</Button>
              </div>
            </section>
          ) : null}
          <div className="finding-list">
            {trace.findings.length ? (
              trace.findings.map((finding) => (
                <div className="finding" key={finding.id}>
                  <b>{finding.severity ?? finding.certainty}</b>
                  {finding.statement}
                  {finding.evidence.length ? (
                    <div className="finding-evidence">
                      {finding.evidence.map((evidence) => (
                        <Button
                          key={`${evidence.entity_type}-${evidence.entity_id}`}
                          type="button"
                          onClick={() => revealEvidence(evidence)}
                        >
                          View {evidence.turn_id ? "transcript turn" : evidence.event_id ? "trace event" : "source evidence"}
                        </Button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            ) : (
              <p className="analysis-pending">
                No analysis findings yet. The trace below remains the source of
                truth.
              </p>
            )}
          </div>
          <div className="analysis-history">
            <div>
              <p className="eyebrow">Analysis history</p>
              <span>{trace.analysis_runs.length} immutable runs</span>
            </div>
            <Button disabled={reanalyzing} onClick={onReanalyze}>
              {reanalyzing ? "Queueing…" : "Re-analyze"}
            </Button>
            {trace.analysis_runs.slice(0, 3).map((run) => (
              <small key={run.id}>
                {run.status} · {run.prompt_version}
                {run.model ? ` · ${run.model}` : ""}
              </small>
            ))}
            {reanalysisError ? (
              <p className="trace-action-error" role="alert">
                Analysis could not be queued: {reanalysisError}
              </p>
            ) : null}
          </div>
          <div className="trace-filters" aria-label="Trace event filters">
            <Button
              className={traceFilter === "all" ? "selected" : ""}
              onClick={() => setTraceFilter("all")}
            >
              All events
            </Button>
            <Button
              className={traceFilter === "agent" ? "selected" : ""}
              onClick={() => setTraceFilter("agent")}
            >
              Graph & agents
            </Button>
            <Button
              className={traceFilter === "handoff" ? "selected" : ""}
              onClick={() => setTraceFilter("handoff")}
            >
              Handoffs
            </Button>
          </div>
          <ol className="timeline">
            {visibleEvents?.map((event) => (
              <li id={`event-${event.id}`} key={event.id}>
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
          <Button
            className="raw-toggle"
            onClick={() => setShowRaw(!showRaw)}
            aria-expanded={showRaw}
          >
            {showRaw ? "Hide" : "Inspect"} normalized events
          </Button>
          {showRaw ? (
            <pre className="raw-inspector">
              {JSON.stringify(trace.events, null, 2)}
            </pre>
          ) : null}
        </>
      )}
    </Card>
  );
}
