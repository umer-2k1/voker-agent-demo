import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test } from "vitest";

import { App } from "./App";

test("renders the Voker Voice foundation", () => {
  render(<QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider>);

  expect(
    screen.getByRole("heading", { name: /voice-agent intelligence/i }),
  ).toBeVisible();
});
