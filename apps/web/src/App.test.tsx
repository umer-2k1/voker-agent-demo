import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";

import { App } from "./App";

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
