import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
  return Promise.resolve(
    jsonResponse({
      session_count: 1,
      completed_session_count: 1,
      outcomes: {},
      sources: {},
      cost: { amount_micros: null, currency: null, record_count: 0 },
      voice_impact_cohorts: {},
      latency: {},
    }),
  );
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
