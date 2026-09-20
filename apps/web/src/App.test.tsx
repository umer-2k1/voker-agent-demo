import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "./App";

test("renders the Voker Voice foundation", () => {
  render(<App />);

  expect(
    screen.getByRole("heading", { name: /voice-agent intelligence/i }),
  ).toBeVisible();
});
