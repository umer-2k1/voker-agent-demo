import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { SessionsPanel } from "@/components/dashboard/SessionsPanel";
import type { VoiceSession } from "@/components/dashboard/types";

beforeEach(() => localStorage.clear());
afterEach(cleanup);

function session(overrides: Partial<VoiceSession> = {}): VoiceSession {
  return {
    id: "session-1",
    external_session_id: "call-001",
    status: "completed",
    source: "livekit",
    started_at: "2026-09-26T12:00:00Z",
    error_count: 0,
    event_count: 3,
    ...overrides,
  };
}

function props(overrides: Record<string, unknown> = {}) {
  return {
    sessions: [],
    page: { offset: 0, limit: 30, total: 0 },
    loading: false,
    search: "",
    status: "",
    source: "",
    environment: "",
    agent: "",
    version: "",
    outcome: "",
    hasError: "",
    startedAfter: "",
    startedBefore: "",
    minLatency: "",
    sort: "started_at_desc",
    onSearch: vi.fn(),
    onStatus: vi.fn(),
    onSource: vi.fn(),
    onEnvironment: vi.fn(),
    onAgent: vi.fn(),
    onVersion: vi.fn(),
    onOutcome: vi.fn(),
    onHasError: vi.fn(),
    onStartedAfter: vi.fn(),
    onStartedBefore: vi.fn(),
    onMinLatency: vi.fn(),
    onSort: vi.fn(),
    onSelect: vi.fn(),
    onPage: vi.fn(),
    ...overrides,
  } as React.ComponentProps<typeof SessionsPanel>;
}

test("summarises the queue and opens a session trace", () => {
  const onSelect = vi.fn();
  render(
    <SessionsPanel
      {...props({
        onSelect,
        page: { offset: 0, limit: 30, total: 2 },
        sessions: [
          session({ id: "session-1" }),
          session({
            id: "session-2",
            external_session_id: "call-002",
            status: "failed",
            error_count: 2,
          }),
        ],
      })}
    />,
  );

  expect(
    screen.getByRole("heading", { name: "Sessions needing attention" }),
  ).toBeVisible();
  expect(
    screen.getByText("1 of 2 captured sessions need review."),
  ).toBeVisible();
  expect(screen.getByText("call-001")).toBeVisible();

  fireEvent.click(screen.getByRole("button", { name: /call-002/i }));
  expect(onSelect).toHaveBeenCalledWith("session-2");
});

test("offers a reset when filters exclude every session", () => {
  const onSearch = vi.fn();
  render(<SessionsPanel {...props({ search: "nothing", onSearch })} />);

  expect(screen.getByText("No sessions match this view.")).toBeVisible();

  fireEvent.click(screen.getByRole("button", { name: /reset filters/i }));
  expect(onSearch).toHaveBeenCalledWith("");
});

test("describes an empty workspace without a reset action", () => {
  render(<SessionsPanel {...props()} />);

  expect(screen.getByText("Your investigation queue is ready.")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: /reset filters/i }),
  ).not.toBeInTheDocument();
});

test("reports search typing to the caller", () => {
  const onSearch = vi.fn();
  render(<SessionsPanel {...props({ onSearch })} />);

  fireEvent.change(screen.getByLabelText("Search sessions"), {
    target: { value: "call-9" },
  });

  expect(onSearch).toHaveBeenCalledWith("call-9");
});

test("saves and removes a view named from its active filters", () => {
  render(<SessionsPanel {...props({ status: "failed", source: "livekit" })} />);

  fireEvent.click(screen.getByRole("button", { name: /save current view/i }));

  const chip = screen.getByRole("button", { name: "Failed · livekit" });
  expect(chip).toBeVisible();

  fireEvent.click(
    screen.getByRole("button", { name: /remove saved view failed · livekit/i }),
  );

  expect(
    screen.queryByRole("button", { name: "Failed · livekit" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("No saved views yet.")).toBeVisible();
});

test("cannot save a view with no active filters", () => {
  render(<SessionsPanel {...props()} />);

  expect(
    screen.getByRole("button", { name: /save current view/i }),
  ).toBeDisabled();
});

test("drops empty views and renames legacy auto-names on load", () => {
  localStorage.setItem(
    "voker-session-filters",
    JSON.stringify([
      {
        name: "Filter 1",
        search: "",
        status: "",
        source: "",
        environment: "",
        agent: "",
        version: "",
        outcome: "",
        hasError: "",
        startedAfter: "",
        startedBefore: "",
        minLatency: "",
        sort: "started_at_desc",
      },
      {
        name: "Filter 2",
        search: "",
        status: "failed",
        source: "",
        environment: "",
        agent: "",
        version: "",
        outcome: "",
        hasError: "",
        startedAfter: "",
        startedBefore: "",
        minLatency: "",
        sort: "started_at_desc",
      },
    ]),
  );

  render(<SessionsPanel {...props()} />);

  // "Filter 1" was empty and dropped; "Filter 2" becomes a readable label.
  expect(
    screen.queryByRole("button", { name: "Filter 1" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Failed" })).toBeVisible();
});
