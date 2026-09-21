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
        session: { id: "session-1", external_session_id: "call-1", status: "completed", source: "sdk", started_at: "2026-01-01T12:00:00Z", error_count: 0, event_count: 1 },
        events: [{ id: "event-1", event_type: "agent.reply", status: "ok", occurred_at: "2026-01-01T12:00:05Z", duration_ms: 10, payload: {} }],
        turns: [{ id: "turn-1", external_turn_id: "external-turn-1", sequence: 1, speaker: "customer", started_at: "2026-01-01T12:00:05Z", transcript: "I need help" }],
        errors: [], findings: [{ id: "finding-1", certainty: "observed", severity: "high", statement: "An error occurred", evidence: [{ entity_type: "event", entity_id: "event-1", event_id: "event-1", turn_id: "turn-1" }] }], analysis_runs: [],
        recordings: [{ id: "recording-1", source: "cloudinary", duration_ms: 90000, media_type: "audio/mpeg", status: "available" }],
      }}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: /customer/i }));
  expect(wave.setTime).toHaveBeenCalledWith(5);
  expect(wave.play).toHaveBeenCalled();
  expect(screen.getByText(/seeking to customer at 0:05/i)).toBeVisible();

  fireEvent.click(screen.getByRole("button", { name: /view transcript turn/i }));
  expect(document.getElementById("turn-turn-1")).toBeTruthy();
});
