import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, test, vi } from "vitest";

import { SettingsPage } from "@/pages/SettingsPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

test("creates an ingest key for the selected authorized project environment", async () => {
  const fetchMock = vi.fn((url: string | URL | Request, init?: RequestInit) => {
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
          environments: [
            { id: "environment-2", name: "Staging", slug: "staging" },
          ],
        }),
      );
    if (path.endsWith("/api/projects/support/api-keys"))
      return Promise.resolve(
        init?.method === "POST"
          ? jsonResponse({ api_key: "vkr_test_once" }, 201)
          : jsonResponse({ items: [] }),
      );
    return Promise.resolve(jsonResponse({ detail: "Project not found" }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <SettingsPage
        account={{
          id: "user-1",
          email: "owner@example.test",
          display_name: "Owner",
        }}
      />
    </QueryClientProvider>,
  );

  await screen.findByText("Support");
  await screen.findByText("Staging");
  fireEvent.change(screen.getByLabelText("Key label for staging"), {
    target: { value: "Staging agent" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create key" }));

  expect(await screen.findByText("vkr_test_once")).toBeVisible();
  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining("/api/projects/support/api-keys"),
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ label: "Staging agent", environment: "staging" }),
    }),
  );
});
