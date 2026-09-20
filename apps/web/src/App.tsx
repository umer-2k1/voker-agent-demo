import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";

import { SessionsPanel } from "@/components/dashboard/SessionsPanel";
import { OverviewPanel } from "@/components/dashboard/OverviewPanel";
import { TracePanel } from "@/components/dashboard/TracePanel";
import type {
  Analytics,
  Overview,
  SessionPage,
  Trace,
  VoiceSession,
} from "@/components/dashboard/types";
import { Badge } from "@/components/ui/badge";
import { AccountPage } from "@/pages/AccountPage";
import { LoginPage } from "@/pages/LoginPage";
import { SettingsPage } from "@/pages/SettingsPage";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001";
const projectSlug = import.meta.env.VITE_PROJECT_SLUG ?? "voker-voice";
const ingestKey = import.meta.env.VITE_INGEST_KEY as string | undefined;
const emptyPage: SessionPage = { offset: 0, limit: 30, total: 0 };

async function dashboardRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    credentials: "include",
    ...init,
  });
  if (!response.ok)
    throw new Error(
      response.status === 401
        ? "Sign in required"
        : "Unable to load dashboard data.",
    );
  return response.json() as Promise<T>;
}

function DashboardPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    null,
  );
  const overviewQuery = useQuery({
    queryKey: ["overview", projectSlug],
    queryFn: () =>
      dashboardRequest<Overview>(`/api/projects/${projectSlug}/overview`),
  });
  const analyticsQuery = useQuery({
    queryKey: ["analytics", projectSlug],
    queryFn: () =>
      dashboardRequest<Analytics>(
        `/api/projects/${projectSlug}/analytics/overview`,
      ),
  });
  const sessionsQuery = useQuery({
    queryKey: [
      "sessions",
      projectSlug,
      statusFilter,
      sourceFilter,
      search,
      offset,
    ],
    queryFn: () => {
      const query = new URLSearchParams({
        limit: "30",
        offset: String(offset),
      });
      if (statusFilter) query.set("status", statusFilter);
      if (sourceFilter) query.set("source", sourceFilter);
      if (search.trim()) query.set("search", search.trim());
      return dashboardRequest<{ items: VoiceSession[]; page: SessionPage }>(
        `/api/projects/${projectSlug}/sessions?${query}`,
      );
    },
  });
  const traceQuery = useQuery({
    queryKey: [
      "trace",
      projectSlug,
      selectedSessionId ?? sessionsQuery.data?.items[0]?.id,
    ],
    queryFn: () =>
      dashboardRequest<Trace>(
        `/api/projects/${projectSlug}/sessions/${selectedSessionId ?? sessionsQuery.data?.items[0]?.id}`,
      ),
    enabled: Boolean(selectedSessionId ?? sessionsQuery.data?.items[0]?.id),
  });
  const reanalysisMutation = useMutation({
    mutationFn: (sessionId: string) =>
      dashboardRequest(
        `/api/projects/${projectSlug}/sessions/${sessionId}/analysis`,
        { method: "POST" },
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["trace", projectSlug],
      });
      await queryClient.invalidateQueries({
        queryKey: ["analytics", projectSlug],
      });
    },
  });
  const overview = overviewQuery.data ?? null;
  const analytics = analyticsQuery.data ?? null;
  const sessions = sessionsQuery.data?.items ?? [];
  const page = sessionsQuery.data?.page ?? emptyPage;
  const activeSessionId = selectedSessionId ?? sessions[0]?.id ?? null;
  const trace = traceQuery.data ?? null;
  const { refetch: refetchTrace } = traceQuery;
  const liveSessionExternalId = trace?.session.external_session_id;
  const liveSessionStatus = trace?.session.status;
  const dashboardError =
    overviewQuery.error ??
    analyticsQuery.error ??
    sessionsQuery.error ??
    traceQuery.error ??
    reanalysisMutation.error;

  useEffect(() => {
    if (
      !liveSessionExternalId ||
      !ingestKey ||
      liveSessionStatus !== "in_progress"
    )
      return;
    const controller = new AbortController();
    const externalSessionId = liveSessionExternalId;
    async function stream() {
      try {
        const response = await fetch(
          `${apiBaseUrl}/v1/live/sessions/${encodeURIComponent(externalSessionId)}`,
          {
            headers: { Authorization: `Bearer ${ingestKey}` },
            signal: controller.signal,
          },
        );
        if (!response.ok || !response.body) return;
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        while (!controller.signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;
          if (decoder.decode(value).includes("event: trace"))
            await refetchTrace();
        }
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError"))
          return;
      }
    }
    void stream();
    return () => controller.abort();
  }, [liveSessionExternalId, liveSessionStatus, refetchTrace]);

  const signInRequired =
    dashboardError instanceof Error &&
    dashboardError.message === "Sign in required";
  return (
    <main className="product-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">V</span>
          <span>Voker</span>
        </div>
        <p className="workspace">VOICE INTELLIGENCE</p>
        <nav aria-label="Primary navigation">
          <a className="nav-item active" href="#overview">
            Overview
          </a>
          <a className="nav-item" href="#sessions">
            Sessions
          </a>
          <a className="nav-item" href="#trace">
            Trace explorer
          </a>
          <a className="nav-item" href="#insights">
            Intelligence
          </a>
          <Link className="nav-item" to="/settings">
            Project settings
          </Link>
          <Link className="nav-item" to="/account">
            Account
          </Link>
        </nav>
        <div className="sidebar-foot">
          {overview?.project.name ?? "Voker Voice"}
          <br />
          <span>Development</span>
        </div>
      </aside>
      <section className="content" id="overview">
        <header className="page-header">
          <div>
            <p className="eyebrow">Voice-agent observability</p>
            <h1>Voice-agent intelligence, built on trustworthy traces.</h1>
          </div>
          <Badge className="live-indicator">
            <i /> Live data
          </Badge>
        </header>
        {dashboardError ? (
          <div className="connection-error" role="alert">
            {dashboardError.message}.{" "}
            {signInRequired ? (
              <Link to="/login">Sign in with Google</Link>
            ) : (
              <>
                Start the API at <code>127.0.0.1:8001</code> and refresh.
              </>
            )}
          </div>
        ) : null}
        <OverviewPanel
          overview={overview}
          analytics={analytics}
          findingsCount={trace?.findings.length ?? 0}
          loading={overviewQuery.isPending || analyticsQuery.isPending}
        />
        <section className="workspace-grid">
          <SessionsPanel
            sessions={sessions}
            page={page}
            loading={sessionsQuery.isPending}
            selectedId={activeSessionId ?? undefined}
            search={search}
            status={statusFilter}
            source={sourceFilter}
            onSearch={(value) => {
              setSearch(value);
              setOffset(0);
            }}
            onStatus={(value) => {
              setStatusFilter(value);
              setOffset(0);
            }}
            onSource={(value) => {
              setSourceFilter(value);
              setOffset(0);
            }}
            onSelect={setSelectedSessionId}
            onPage={setOffset}
          />
          <TracePanel
            trace={trace}
            apiBaseUrl={apiBaseUrl}
            projectSlug={projectSlug}
            reanalyzing={reanalysisMutation.isPending}
            onReanalyze={() =>
              trace && reanalysisMutation.mutate(trace.session.id)
            }
          />
        </section>
      </section>
    </main>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/account" element={<AccountPage />} />
        <Route path="*" element={<DashboardPage />} />
      </Routes>
    </BrowserRouter>
  );
}
