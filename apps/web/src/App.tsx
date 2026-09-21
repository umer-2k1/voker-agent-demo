import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BrowserRouter,
  Link,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams,
  useParams,
} from "react-router-dom";

import { AppShell } from "@/components/dashboard/AppShell";
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
import { Button } from "@/components/ui/button";
import type { Account } from "@/pages/AccountPage";
import { LoginPage } from "@/pages/LoginPage";
import { SettingsPage } from "@/pages/SettingsPage";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8001";
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

function DashboardPage({ sessionsOnly = false }: { sessionsOnly?: boolean }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { sessionId: routeSessionId } = useParams();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState(() => searchParams.get("status") ?? "");
  const [sourceFilter, setSourceFilter] = useState(() => searchParams.get("source") ?? "");
  const [search, setSearch] = useState(() => searchParams.get("search") ?? "");
  const [sort, setSort] = useState(() => searchParams.get("sort") ?? "started_at_desc");
  const [offset, setOffset] = useState(() => Number(searchParams.get("offset") ?? 0));
  const selectedSessionId = routeSessionId;
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
      sort,
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
      if (sort !== "started_at_desc") query.set("sort", sort);
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
  const activeSessionId = selectedSessionId;
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

  function syncFilterUrl(next: {
    status?: string;
    source?: string;
    search?: string;
    sort?: string;
    offset?: number;
  }) {
    const params = new URLSearchParams(searchParams);
    Object.entries(next).forEach(([key, value]) => {
      if (value === undefined || value === "" || value === 0 || (key === "sort" && value === "started_at_desc")) params.delete(key);
      else params.set(key, String(value));
    });
    setSearchParams(params, { replace: true });
  }

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
    <>
      <section className="content" id={sessionsOnly ? "sessions" : "overview"}>
        <header className="page-header">
          <div>
            <p className="eyebrow">Voice-agent observability</p>
            <h1>
              {sessionsOnly
                ? "Investigate sessions with evidence."
                : "Workspace health at a glance."}
            </h1>
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
                Start the API at <code>localhost:8001</code> and refresh.
              </>
            )}
          </div>
        ) : null}
        {!sessionsOnly ? (
          <OverviewPanel
            overview={overview}
            analytics={analytics}
            findingsCount={trace?.findings.length ?? 0}
            loading={overviewQuery.isPending || analyticsQuery.isPending}
          />
        ) : null}
        {sessionsOnly ? (
          <section className="sessions-workspace">
            {activeSessionId ? (
              <>
                <Button
                  className="back-to-sessions"
                  onClick={() => {
                    navigate(`/sessions${searchParams.toString() ? `?${searchParams}` : ""}`);
                  }}
                  type="button"
                >
                  Back to sessions
                </Button>
                <TracePanel
                  trace={trace}
                  apiBaseUrl={apiBaseUrl}
                  projectSlug={projectSlug}
                  reanalyzing={reanalysisMutation.isPending}
                  reanalysisError={
                    reanalysisMutation.error instanceof Error
                      ? reanalysisMutation.error.message
                      : null
                  }
                  onReanalyze={() =>
                    trace && reanalysisMutation.mutate(trace.session.id)
                  }
                />
              </>
            ) : (
              <SessionsPanel
                sessions={sessions}
                page={page}
                loading={sessionsQuery.isPending}
                search={search}
                status={statusFilter}
                source={sourceFilter}
                sort={sort}
                onSearch={(value) => {
                  setSearch(value);
                  setOffset(0);
                  syncFilterUrl({ search: value, offset: 0 });
                }}
                onStatus={(value) => {
                  setStatusFilter(value);
                  setOffset(0);
                  syncFilterUrl({ status: value, offset: 0 });
                }}
                onSource={(value) => {
                  setSourceFilter(value);
                  setOffset(0);
                  syncFilterUrl({ source: value, offset: 0 });
                }}
                onSort={(value) => {
                  setSort(value);
                  setOffset(0);
                  syncFilterUrl({ sort: value, offset: 0 });
                }}
                onSelect={(id) => {
                  navigate(`/sessions/${id}${searchParams.toString() ? `?${searchParams}` : ""}`);
                }}
                onPage={(value) => {
                  setOffset(value);
                  syncFilterUrl({ offset: value });
                }}
              />
            )}
          </section>
        ) : null}
      </section>
    </>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireDashboardUser />}>
          <Route element={<DashboardLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/sessions" element={<DashboardPage sessionsOnly />} />
            <Route path="/sessions/:sessionId" element={<DashboardPage sessionsOnly />} />
            <Route path="/settings" element={<SettingsRoute />} />
            <Route
              path="/account"
              element={<Navigate replace to="/settings#profile" />}
            />
          </Route>
        </Route>
        <Route path="*" element={<Navigate replace to="/" />} />
      </Routes>
    </BrowserRouter>
  );
}

function accountRequest(): Promise<Account | null> {
  return fetch(`${apiBaseUrl}/auth/me`, { credentials: "include" }).then(
    async (response) => {
      if (response.status === 401) return null;
      if (!response.ok) throw new Error("Unable to verify your session");
      return response.json() as Promise<Account>;
    },
  );
}

function RequireDashboardUser() {
  const location = useLocation();
  const account = useQuery({
    queryKey: ["account"],
    queryFn: accountRequest,
    retry: false,
  });
  if (account.isPending)
    return (
      <main className="auth-loading" aria-label="Checking your sign-in">
        <span className="brand-mark">V</span>
        <p>Checking your secure session…</p>
      </main>
    );
  if (account.data === null)
    return <Navigate replace to="/login" state={{ from: location.pathname }} />;
  if (account.isError)
    return (
      <main className="auth-loading">
        <p>We could not verify your session. Please refresh.</p>
      </main>
    );
  return <AppShell account={account.data} />;
}

function DashboardLayout() {
  return <Outlet />;
}

function SettingsRoute() {
  const account = useQuery({
    queryKey: ["account"],
    queryFn: accountRequest,
    retry: false,
  });
  return account.data ? <SettingsPage account={account.data} /> : null;
}
