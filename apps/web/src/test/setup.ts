import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

// Lazy-loaded routes/components resolve asynchronously; give `findBy*` queries
// room instead of the 1s default.
configure({ asyncUtilTimeout: 5000 });

// jsdom does not implement matchMedia, which sonner (toasts) and several
// shadcn primitives read during mount.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}
