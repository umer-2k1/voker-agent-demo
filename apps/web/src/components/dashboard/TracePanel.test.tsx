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
        event_page: { offset: 0, limit: 250, total: 1 },
        voice_behavior: {
          interruptions: 0,
          talk_over: 0,
          dead_air: 0,
          corrections: 0,
          abandonment: 0,
        },
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
  fireEvent.click(screen.getByRole("button", { name: /customer/i }));
  expect(wave.setTime).toHaveBeenCalledWith(5);
  expect(wave.play).toHaveBeenCalled();
  expect(screen.getByText(/seeking to customer at 0:05/i)).toBeVisible();

  fireEvent.mouseDown(screen.getByRole("tab", { name: "Analysis" }), {
    button: 0,
    ctrlKey: false,
  });
  fireEvent.click(screen.getAllByRole("button", { name: /view turn/i })[0]);
  expect(document.getElementById("turn-turn-1")).toBeTruthy();
});
