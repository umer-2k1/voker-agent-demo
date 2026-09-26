import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

/** Inline spinner built on the shared primary colour token. */
export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("size-4 animate-spin", className)} aria-hidden="true" />;
}

/**
 * Centred loading state for a panel or section: exposes `role="status"` so
 * assistive tech announces progress instead of reading an empty region.
 */
export function LoadingState({
  label = "Loading…",
  className,
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex flex-col items-center justify-center gap-3 px-6 py-12 text-center",
        className,
      )}
    >
      <Spinner className="size-5 text-muted-foreground" />
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}

/** Full-viewport loader used while the app resolves the session or route. */
export function PageLoader({ label = "Loading…" }: { label?: string }) {
  return (
    <main
      className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background"
      aria-label={label}
    >
      <span className="brand-mark">V</span>
      <Spinner className="size-5 text-primary" />
      <p className="text-sm text-muted-foreground">{label}</p>
    </main>
  );
}
