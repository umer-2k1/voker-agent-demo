import { useCallback, useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";

import { Card, CardHeader } from "@/components/ui/card";
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
    wave.on("play", () => setPlaying(true));
    wave.on("pause", () => setPlaying(false));
    wave.on("finish", () => setPlaying(false));
    wave.on("timeupdate", onTimeUpdate);
    return () => {
      waveRef.current = null;
      onReady(null);
      wave.destroy();
    };
  }, [onReady, onTimeUpdate, src]);
  return (
    <div className="waveform-player">
      <button
        className="waveform-toggle"
        onClick={() => waveRef.current?.playPause()}
        type="button"
      >
        {playing ? "Pause" : "Play"}
      </button>
      <div ref={containerRef} aria-label="Call recording waveform" />
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

  function seekToTurn(turn: Trace["turns"][number]) {
    if (!trace || !waveformRef.current || !activeRecording) return;
    const offset = turnOffsetSeconds(turn, trace.session);
    waveformRef.current.setTime(offset);
    setPlayheadSeconds(offset);
    void waveformRef.current.play();
  }

  return (
    <Card className="panel trace-panel" id="trace">
      <CardHeader className="panel-heading">
        <div>
          <p className="eyebrow">Complete conversation trace</p>
          <h2>
            {trace ? trace.session.external_session_id : "Select a session"}
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
                  <button
                    className={`transcript-turn ${isActive ? "playing" : ""}`}
                    disabled={!activeRecording}
                    key={turn.id}
                    onClick={() => seekToTurn(turn)}
                  >
                    <b>
                      {turn.speaker} · {formatLatency(offset * 1000)}
                    </b>
                    <span>{turn.transcript ?? "No transcript captured"}</span>
                  </button>
                );
              })
            ) : (
              <p className="analysis-pending">
                No transcript was captured for this trace.
              </p>
            )}
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
            <button disabled={reanalyzing} onClick={onReanalyze}>
              {reanalyzing ? "Queueing…" : "Re-analyze"}
            </button>
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
          <button
            className="raw-toggle"
            onClick={() => setShowRaw(!showRaw)}
            aria-expanded={showRaw}
          >
            {showRaw ? "Hide" : "Inspect"} normalized events
          </button>
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
