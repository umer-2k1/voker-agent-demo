import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const jsonResponse = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

function dashboardFetch(url: string | URL | Request) {
  const path = String(url);
  if (path.endsWith("/auth/me"))
    return Promise.resolve(
      jsonResponse({
        id: "user-1",
        email: "ops@example.test",
        display_name: "Ops",
      }),
    );
  if (path.endsWith("/api/projects"))
    return Promise.resolve(
      jsonResponse({
        items: [{ id: "project-1", name: "Voice", slug: "voker-voice" }],
      }),
    );
  if (path.includes("/analytics/overview"))
    return Promise.resolve(
      jsonResponse({
        filters: {
          environment: null,
          started_after: null,
          started_before: null,
        },
        session_count: 1,
        completed_session_count: 1,
        outcomes: { resolved: 1 },
        sources: { sdk: 1 },
        cost: {
          amount_micros: null,
          exact_amount_micros: 0,
          estimated_amount_micros: 0,
          currency: null,
          record_count: 0,
          exact_record_count: 0,
          estimated_record_count: 0,
        },
        usage: {
          input_tokens: null,
          output_tokens: null,
          total_tokens: null,
          audio_seconds: null,
          tts_characters: null,
        },
        voice_impact_cohorts: {},
        latency: {},
        rates: {
          resolution: 1,
          correction: 0,
          escalation: 0,
          abandonment: 0,
          error: 0,
        },
        failure_categories: {},
        failure_category_insights: [],
        tool_failure_count: 0,
        voice_behavior: {
          interruption_sessions: 0,
          talk_over_sessions: 0,
          dead_air_sessions: 0,
          correction_sessions: 0,
        },
        insights: [],
        comparisons: {
          agents: [],
          versions: [],
          platforms: [],
          providers: [],
          models: [],
        },
        outcome_sources: { explicit: 1, inferred: 0, unknown: 0 },
      }),
    );
  if (path.includes("/overview"))
    return Promise.resolve(
      jsonResponse({
        project: { name: "Voice", slug: "voker-voice" },
        metrics: {
          total_sessions: 1,
          active_sessions: 0,
          error_count: 0,
          average_span_duration_ms: 220,
        },
      }),
    );
  if (path.endsWith("/setup"))
    return Promise.resolve(
      jsonResponse({
        project: { id: "project-1", name: "Voice", slug: "voker-voice" },
        environments: [
          { id: "environment-1", name: "Development", slug: "development" },
        ],
        integrations: [],
        last_received_event_at: null,
        observed_stages: [],
      }),
    );
  if (path.includes("/sessions?"))
    return Promise.resolve(
      jsonResponse({
        items: [
          {
            id: "session-1",
            external_session_id: "call-001",
            status: "completed",
            source: "sdk",
            started_at: "2026-01-01T12:00:00Z",
            error_count: 0,
            event_count: 2,
          },
        ],
        page: { offset: 0, limit: 30, total: 1 },
      }),
    );
  if (path.includes("/sessions/session-1"))
    return Promise.resolve(
      jsonResponse({
        session: {
          id: "session-1",
          external_session_id: "call-001",
          status: "completed",
          source: "sdk",
          started_at: "2026-01-01T12:00:00Z",
          error_count: 0,
          event_count: 2,
        },
        event_page: { offset: 0, limit: 250, total: 0 },
        voice_behavior: {
          interruptions: 0,
          talk_over: 0,
          dead_air: 0,
          corrections: 0,
          abandonment: 0,
        },
        events: [],
        turns: [],
        spans: [],
        agent_runs: [],
        errors: [],
        usage: [],
        costs: [],
        findings: [],
        analysis_runs: [],
        recordings: [],
      }),
    );
  return Promise.resolve(jsonResponse({}));
}

test("redirects an unsigned visitor to the polished sign-in page", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );

  expect(
    await screen.findByRole("heading", { name: /welcome back/i }),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: /continue with google/i }),
  ).toBeVisible();
});

test("acknowledges the Google redirect immediately and prevents duplicate submits", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );

  const button = await screen.findByRole("button", {
    name: /continue with google/i,
  });
  vi.useFakeTimers();
  try {
    fireEvent.click(button);

    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("Opening Google…");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Redirecting to Google sign-in",
    );
  } finally {
    vi.clearAllTimers();
    vi.useRealTimers();
  }
});

test("selecting a session uses a shareable session detail URL", async () => {
  window.history.pushState({}, "", "/sessions?status=completed");
  vi.stubGlobal("fetch", vi.fn(dashboardFetch));
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );

  fireEvent.click(await screen.findByRole("button", { name: /call-001/i }));

  expect(window.location.pathname).toBe("/sessions/session-1");
  expect(window.location.search).toContain("status=completed");
});

test("opens a session detail route directly from its URL", async () => {
  window.history.pushState({}, "", "/sessions/session-1");
  vi.stubGlobal("fetch", vi.fn(dashboardFetch));
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );

  expect(
    await screen.findByRole("heading", { name: "call-001" }),
  ).toBeVisible();
});

test("analytics environment and date filters are shareable and sent to the API", async () => {
  window.history.pushState({}, "", "/");
  const fetchMock = vi.fn(dashboardFetch);
  vi.stubGlobal("fetch", fetchMock);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );

  fireEvent.change(await screen.findByLabelText("Environment"), {
    target: { value: "development" },
  });
  fireEvent.change(screen.getByLabelText("Started after"), {
    target: { value: "2026-09-01" },
  });

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(
        /analytics\/overview\?[^ ]*environment=development[^ ]*started_after=/,
      ),
      expect.anything(),
    ),
  );
  expect(window.location.search).toContain("environment=development");
  expect(window.location.search).toContain("started_after=2026-09-01");
});
