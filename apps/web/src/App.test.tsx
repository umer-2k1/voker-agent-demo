import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

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
