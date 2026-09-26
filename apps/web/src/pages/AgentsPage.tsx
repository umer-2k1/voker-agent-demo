import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, RadioTower } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import type { Analytics } from "@/components/dashboard/types";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { LoadingState } from "@/components/ui/loading";
import { H1 } from "@/components/ui/typography";
import { loadProjects, resolveProjectSlug } from "@/lib/projects";
import { useDocumentTitle } from "@/lib/use-document-title";

const apiBaseUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8001";
const preferredProjectSlug = import.meta.env.VITE_PROJECT_SLUG ?? "voker-voice";

async function loadAnalytics(projectSlug: string) {
  const response = await fetch(
    `${apiBaseUrl}/api/projects/${projectSlug}/analytics/overview`,
    { credentials: "include" },
  );
  if (!response.ok) throw new Error("Unable to load agent analytics.");
  return response.json() as Promise<Analytics>;
}

export function AgentsPage() {
  const { agent: encodedAgent } = useParams();
  const selectedName = encodedAgent ? decodeURIComponent(encodedAgent) : null;
  useDocumentTitle(selectedName ? `Agent · ${selectedName}` : "Agents");
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => loadProjects(apiBaseUrl),
  });
  const projectSlug = resolveProjectSlug(
    projectsQuery.data?.items ?? [],
    preferredProjectSlug,
  );
  const query = useQuery({
    queryKey: ["analytics", projectSlug],
    queryFn: () => loadAnalytics(projectSlug),
    enabled: Boolean(projectSlug),
  });
  const agents = query.data?.comparisons.agents ?? [];
  const selected = selectedName
    ? agents.find((item) => item.label === selectedName)
    : null;
  return (
    <main className="content insights-page">
      <header className="page-header">
        <div>
          {selectedName ? (
            <Link className="back-link" to="/agents">
              <ArrowLeft size={15} /> All agents
            </Link>
          ) : null}
          <H1 as="h1">{selectedName ?? "Agent performance"}</H1>
          <p className="page-intro">
            Compare production behavior using observed calls and explicit
            outcome coverage.
          </p>
        </div>
        <Badge>{agents.length} active agents</Badge>
      </header>
      {query.isError ? (
        <div className="connection-error" role="alert">
          {query.error.message}
        </div>
      ) : null}
      {query.isPending ? (
        <LoadingState label="Loading agent evidence…" className="py-16" />
      ) : null}
      {selectedName ? (
        selected ? (
          <AgentDetail item={selected} />
        ) : (
          <Card className="chart-card">
            <h2>No observed agent</h2>
            <p className="empty-state">
              This agent is not present in the current filters.
            </p>
          </Card>
        )
      ) : agents.length ? (
        <section className="agent-grid" aria-label="Agent performance list">
          {agents.map((item) => (
            <Card className="agent-summary" key={item.label}>
              <div>
                <h2>{item.label}</h2>
                <Badge>{item.sessions} calls</Badge>
              </div>
              <strong>
                {item.resolution_rate === null
                  ? "—"
                  : `${Math.round(item.resolution_rate * 100)}%`}{" "}
                <small>resolved</small>
              </strong>
              <p>{item.known_outcomes} calls have known outcomes.</p>
              <Link to={`/agents/${encodeURIComponent(item.label)}`}>
                Open agent detail <ExternalLink size={14} />
              </Link>
            </Card>
          ))}
        </section>
      ) : !query.isPending && !query.isError ? (
        <Card className="first-observation-state">
          <RadioTower aria-hidden="true" />
          <div>
            <h2>No agents observed yet</h2>
            <p>
              This is expected for a new workspace. Connect your agent, then
              make its first call to start building performance evidence.
            </p>
            <Link to="/setup">
              Set up an agent <ExternalLink size={14} />
            </Link>
          </div>
        </Card>
      ) : null}
    </main>
  );
}

function AgentDetail({
  item,
}: {
  item: Analytics["comparisons"]["agents"][number];
}) {
  return (
    <>
      <section className="detail-metrics" aria-label="Agent metrics">
        <Card>
          <span>Total calls</span>
          <strong>{item.sessions}</strong>
        </Card>
        <Card>
          <span>Known outcomes</span>
          <strong>{item.known_outcomes}</strong>
        </Card>
        <Card>
          <span>Resolved</span>
          <strong>{item.resolved}</strong>
        </Card>
        <Card>
          <span>Resolution rate</span>
          <strong>
            {item.resolution_rate === null
              ? "—"
              : `${Math.round(item.resolution_rate * 100)}%`}
          </strong>
        </Card>
      </section>
      <Card className="chart-card">
        <h2>Representative session</h2>
        <p className="chart-description">
          Open the canonical trace for turns, spans, events, recording,
          findings, and costs.
        </p>
        {item.session_ids[0] ? (
          <Link
            className="primary-evidence-link"
            to={`/sessions/${item.session_ids[0]}`}
          >
            Investigate session <ExternalLink size={14} />
          </Link>
        ) : (
          <p className="empty-state">No linked session is available.</p>
        )}
      </Card>
    </>
  );
}
