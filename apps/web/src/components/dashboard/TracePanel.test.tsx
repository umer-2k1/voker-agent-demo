import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

const wave = {
  load: vi.fn(),
  on: vi.fn((event: string, callback: (value?: number) => void) => {
    if (event === "ready") callback(90);
  }),
  playPause: vi.fn(),
  setTime: vi.fn(),
  play: vi.fn(),
  destroy: vi.fn(),
};

vi.mock("wavesurfer.js", () => ({ default: { create: vi.fn(() => wave) } }));

import { TracePanel } from "./TracePanel";

afterEach(() => vi.clearAllMocks());

const baseProps = {
  apiBaseUrl: "http://api.test",
  projectSlug: "voice",
  reanalyzing: false,
  reanalysisError: null,
  onReanalyze: () => undefined,
};

test("shows a loader while a selected session is still loading", () => {
  render(<TracePanel trace={null} loading {...baseProps} />);

  expect(
    screen.getByRole("heading", { name: /loading session/i }),
  ).toBeVisible();
  expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
  expect(screen.queryByText(/select a session/i)).not.toBeInTheDocument();
});

test("prompts to pick a session only when nothing is loading", () => {
  render(<TracePanel trace={null} {...baseProps} />);

  expect(
    screen.getByRole("heading", { name: /select a session/i }),
  ).toBeVisible();
});

test("seeks the waveform and marks the matching transcript turn", () => {
  render(
    <TracePanel
      apiBaseUrl="http://api.test"
      projectSlug="voice"
      reanalyzing={false}
      reanalysisError={null}
      onReanalyze={() => undefined}
      trace={{
        session: {
          id: "session-1",
          external_session_id: "call-1",
          status: "completed",
          source: "sdk",
          started_at: "2026-01-01T12:00:00Z",
          error_count: 0,
          event_count: 1,
        },
        collection: {
          last_event_type: "session.ended",
          last_event_at: "2026-01-01T12:01:30Z",
          last_received_at: "2026-01-01T12:01:30Z",
          terminal_event_received: true,
          diagnostic_log: "logs/sessions/session-1.jsonl",
          capture_state: "complete",
          highest_seen_sequence: 8,
          highest_contiguous_sequence: 8,
          expected_last_sequence: 8,
          missing_ranges: [],
          raw_event_count: 8,
          projected_event_count: 8,
        },
        event_page: { offset: 0, limit: 250, total: 1 },
        voice_behavior: {
          interruptions: 0,
          talk_over: 0,
          dead_air: 0,
          corrections: 0,
          abandonment: 0,
        },
        voice_behavior_sources: {
          interruptions: {
            source: "voice.interruption events",
            threshold_ms: null,
            method: "event",
          },
          talk_over: {
            source: "voice.talk_over events",
            threshold_ms: null,
            method: "event",
          },
          dead_air: {
            source: "speech.stopped → playback.started",
            threshold_ms: 2500,
            method: "deterministic response-gap rule",
          },
          corrections: {
            source: "correction events",
            threshold_ms: null,
            method: "event",
          },
          abandonment: {
            source: "turn.abandoned events",
            threshold_ms: null,
            method: "event",
          },
        },
        tool_summary: { total: 1, succeeded: 1, failed: 0 },
        tool_calls: [
          {
            id: "tool-span-1",
            call_id: "call-calendar-1",
            name: "reschedule",
            protocol: "function",
            status: "ok",
            started_at: "2026-01-01T12:00:10Z",
            ended_at: "2026-01-01T12:00:11Z",
            duration_ms: 1000,
            turn_id: "turn-1",
            agent_run_id: "run-1",
            input: { arguments: { day: "Tuesday", time: "2 PM" } },
            output: { result: "Appointment rescheduled" },
          },
        ],
        events: [
          {
            id: "event-1",
            event_id: "external-event-1",
            event_type: "agent.reply",
            status: "ok",
            occurred_at: "2026-01-01T12:00:05Z",
            duration_ms: 10,
            payload: {},
          },
        ],
        turns: [
          {
            id: "turn-1",
            external_turn_id: "external-turn-1",
            sequence: 1,
            speaker: "customer",
            started_at: "2026-01-01T12:00:05Z",
            ended_at: null,
            transcript: "I need help",
            attributes: {},
          },
          {
            id: "turn-empty",
            external_turn_id: "external-turn-empty",
            sequence: 2,
            speaker: "agent",
            started_at: "2026-01-01T12:00:06Z",
            ended_at: null,
            transcript: null,
            attributes: {},
          },
        ],
        spans: [],
        agent_runs: [],
        usage: [],
        costs: [],
        errors: [],
        findings: [
          {
            id: "finding-1",
            certainty: "observed",
            severity: "high",
            statement: "An error occurred",
            confidence: null,
            rule_id: "rule",
            rule_version: "1",
            attributes: {},
            evidence: [
              {
                entity_type: "turn",
                entity_id: "turn-1",
                event_id: null,
                span_id: null,
                turn_id: "turn-1",
              },
            ],
          },
        ],
        analysis_runs: [],
        recordings: [
          {
            id: "recording-1",
            source: "cloudinary",
            duration_ms: 90000,
            media_type: "audio/mpeg",
            status: "available",
            expires_at: null,
          },
        ],
      }}
    />,
  );

  fireEvent.mouseDown(screen.getByRole("tab", { name: "Transcript" }), {
    button: 0,
    ctrlKey: false,
  });
  expect(
    screen.getByRole("heading", { name: "Conversation timeline" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole("button", { name: /customer/i }).at(-1)!);
  expect(wave.setTime).toHaveBeenCalledWith(5);
  expect(wave.play).toHaveBeenCalled();
  expect(screen.getByText(/seeking to customer at 0:05/i)).toBeVisible();
  expect(
    screen.queryByText(/transcript omitted or not captured/i),
  ).not.toBeInTheDocument();
  expect(screen.getByText(/threshold 2.5 s/i)).toBeVisible();

  fireEvent.mouseDown(screen.getByRole("tab", { name: "Analysis" }), {
    button: 0,
    ctrlKey: false,
  });
  expect(screen.getByRole("heading", { name: "Tool calls" })).toBeVisible();
  expect(screen.getByText("reschedule")).toBeVisible();
  expect(screen.getByText("1 succeeded")).toBeVisible();
  fireEvent.click(screen.getAllByRole("button", { name: /view turn/i })[0]);
  expect(document.getElementById("turn-turn-1")).toBeTruthy();
});
