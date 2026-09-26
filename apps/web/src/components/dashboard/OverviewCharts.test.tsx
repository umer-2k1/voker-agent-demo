import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test } from "vitest";

import { OverviewCharts } from "@/components/dashboard/OverviewCharts";
import type { Analytics } from "@/components/dashboard/types";

afterEach(cleanup);

function analytics(overrides: Partial<Analytics> = {}): Analytics {
  const base = {
    volume_trend: [
      { date: "2026-09-01", sessions: 2 },
      { date: "2026-09-03", sessions: 1 },
    ],
    outcomes: { success: 3, resolved: 1, abandoned: 2 },
    metric_coverage: {
      outcomes: { observed: 6, total: 10 },
    },
    latency: {
      stt: { sample_size: 4, p50_ms: 0, p90_ms: 0, p95_ms: 0, max_ms: 0 },
      llm: {
        sample_size: 5,
        p50_ms: 1200,
        p90_ms: 4000,
        p95_ms: 5000,
        max_ms: 6000,
      },
    },
    voice_issue_impacts: [
      {
        key: "dead_air",
        label: "Excessive dead air",
        affected_resolution_rate: 0.2,
        baseline_resolution_rate: 0.6,
        impact_percentage_points: -40,
        sample_size: 6,
        session_ids: ["session-1"],
      },
    ],
  };
  return { ...base, ...overrides } as unknown as Analytics;
}

function renderCharts(data: Analytics) {
  return render(
    <MemoryRouter>
      <OverviewCharts analytics={data} />
    </MemoryRouter>,
  );
}

test("renders each chart with an accessible summary", () => {
  renderCharts(analytics());

  expect(screen.getByRole("heading", { name: "Call volume" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Outcome mix" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Latency by stage" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Voice issues by impact" })).toBeVisible();

  const images = screen.getAllByRole("img");
  expect(images.map((node) => node.getAttribute("aria-label"))).toEqual(
    expect.arrayContaining([
      expect.stringMatching(/Area chart of call volume: 3 sessions over 3 days/),
      expect.stringMatching(/Donut chart of outcomes: Resolved 4, Abandoned 2/),
      expect.stringMatching(/Bar chart of latency by stage/),
      expect.stringMatching(/Bar chart of voice issue impact/),
    ]),
  );
});

test("collapses success and resolved into a single outcome slice", () => {
  renderCharts(analytics());

  // success:3 + resolved:1 both render as "Resolved · 4".
  expect(screen.getByText(/Resolved · 4 \(67%\)/)).toBeVisible();
  expect(screen.getByText(/Abandoned · 2 \(33%\)/)).toBeVisible();
});

test("explains absent data instead of drawing an empty chart", () => {
  renderCharts(
    analytics({
      volume_trend: [],
      outcomes: {},
      latency: {},
      voice_issue_impacts: [],
      metric_coverage: {
        outcomes: { observed: 0, total: 0 },
        stt_latency: { observed: 0, total: 0 },
        corrections: { observed: 0, total: 0 },
        escalations: { observed: 0, total: 0 },
      },
    }),
  );

  expect(
    screen.getByText("Call volume appears once sessions arrive."),
  ).toBeVisible();
  expect(
    screen.getByText("Outcome mix appears once calls report a terminal result."),
  ).toBeVisible();
  expect(
    screen.getByText("Latency appears once adapters report span timings."),
  ).toBeVisible();
  expect(
    screen.getByText(
      "At least five affected and baseline calls are required per issue.",
    ),
  ).toBeVisible();
  expect(screen.queryAllByRole("img")).toHaveLength(0);
});

test("renders nothing when analytics has not loaded", () => {
  const { container } = render(
    <MemoryRouter>
      <OverviewCharts analytics={null} />
    </MemoryRouter>,
  );
  expect(container).toBeEmptyDOMElement();
});
