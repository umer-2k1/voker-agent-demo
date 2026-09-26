import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { H2, Muted } from "@/components/ui/typography";

/**
 * Catches render/lifecycle errors anywhere below it and shows a recoverable
 * fallback instead of a blank screen.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled UI error", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="grid min-h-screen place-items-center bg-background p-6">
          <Card className="max-w-md">
            <CardHeader>
              <H2>Something went wrong</H2>
              <Muted>
                The dashboard hit an unexpected error. Reloading usually fixes
                it — your data is safe.
              </Muted>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <Button onClick={() => window.location.reload()}>Reload</Button>
              <Button
                variant="outline"
                onClick={() => this.setState({ error: null })}
              >
                Try again
              </Button>
            </CardContent>
          </Card>
        </main>
      );
    }
    return this.props.children;
  }
}
