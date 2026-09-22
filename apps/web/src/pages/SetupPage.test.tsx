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

import { SetupPage } from "@/pages/SetupPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

test("selects the first authorized project and environment when defaults are unavailable", async () => {
  const fetchMock = vi.fn((url: string | URL | Request) => {
    const path = String(url);
    if (path.endsWith("/api/projects"))
      return Promise.resolve(
        jsonResponse({
          items: [{ id: "project-2", name: "Support", slug: "support" }],
        }),
      );
    if (path.endsWith("/api/projects/support/setup"))
      return Promise.resolve(
        jsonResponse({
          project: { id: "project-2", name: "Support", slug: "support" },
          environments: [
            { id: "environment-2", name: "Staging", slug: "staging" },
          ],
          integrations: [],
          last_received_event_at: null,
          observed_stages: [],
        }),
      );
    return Promise.resolve(jsonResponse({ detail: "Project not found" }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <SetupPage />
    </QueryClientProvider>,
  );

  await waitFor(() => expect(screen.getByLabelText("Project")).toHaveValue("support"));
  await waitFor(() => expect(screen.getByLabelText("Environment")).toHaveValue("staging"));
  expect(screen.getByText("staging configuration")).toBeVisible();
  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining("/api/projects/support/setup"),
    expect.objectContaining({ credentials: "include" }),
  );
  expect(screen.getByText(/import os[\s\S]*from voker_voice import VokerVoice/)).toBeVisible();

  fireEvent.mouseDown(screen.getByRole("tab", { name: "LangGraph" }), {
    button: 0,
    ctrlKey: false,
  });
  expect(
    screen.getByText(
      /from voker_voice import VokerVoice, observe_langgraph[\s\S]*voker = VokerVoice/,
    ),
  ).toBeVisible();

  fireEvent.mouseDown(screen.getByRole("tab", { name: "LiveKit" }), {
    button: 0,
    ctrlKey: false,
  });
  expect(
    screen.getByText(/from voker_voice import VokerVoice, observe_livekit/),
  ).toBeVisible();
});
