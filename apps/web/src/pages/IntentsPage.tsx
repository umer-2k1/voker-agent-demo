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
  if (!response.ok) throw new Error("Unable to load intent analytics.");
  return response.json() as Promise<Analytics>;
}

export function IntentsPage() {
  const { intent: encodedIntent } = useParams();
  const selectedName = encodedIntent ? decodeURIComponent(encodedIntent) : null;
  useDocumentTitle(selectedName ? `Intent · ${selectedName}` : "Intents");
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
  const intents = query.data?.intent_comparisons ?? [];
  const selected = selectedName
    ? intents.find((item) => item.label === selectedName)
    : null;

  return (
    <main className="content insights-page">
      <header className="page-header">
        <div>
          {selectedName ? (
            <Link className="back-link" to="/intents">
              <ArrowLeft size={15} /> All intents
            </Link>
          ) : null}
          <H1 as="h1">{selectedName ?? "Intent performance"}</H1>
          <p className="page-intro">
            Compare observed outcomes, then open the exact calls behind each
            result.
          </p>
        </div>
        <Badge>{intents.length} observed intents</Badge>
      </header>
      {query.isError ? (
        <div className="connection-error" role="alert">
          {query.error.message}
        </div>
      ) : null}
      {query.isPending ? (
        <LoadingState label="Loading intent evidence…" className="py-16" />
      ) : null}
      {selectedName ? (
        selected ? (
          <IntentDetail item={selected} />
        ) : (
          <Card className="chart-card">
            <h2>No observed intent</h2>
            <p className="empty-state">
              This intent is not present in the current filters.
            </p>
          </Card>
        )
      ) : intents.length ? (
        <section
          className="evidence-table"
          aria-label="Intent performance list"
        >
          <div className="evidence-table-head">
            <span>Intent</span>
            <span>Calls</span>
            <span>Resolution</span>
            <span>Evidence</span>
          </div>
          {intents.map((item) => (
            <div className="evidence-table-row" key={item.label}>
              <Link
                className="evidence-name"
                to={`/intents/${encodeURIComponent(item.label)}`}
              >
                {item.label}
              </Link>
              <span>{item.sessions}</span>
              <strong>
                {item.resolution_rate === null
                  ? "—"
                  : `${Math.round(item.resolution_rate * 100)}%`}
              </strong>
              {item.session_ids[0] ? (
                <Link to={`/sessions/${item.session_ids[0]}`}>
                  Review call <ExternalLink size={13} />
                </Link>
              ) : (
                <span>Unavailable</span>
              )}
            </div>
          ))}
        </section>
      ) : !query.isPending && !query.isError ? (
        <Card className="first-observation-state">
          <RadioTower aria-hidden="true" />
          <div>
            <h2>No intents observed yet</h2>
            <p>
              This is expected for a new workspace. Intents appear once Voker
              receives calls with observable conversation context.
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

function IntentDetail({
  item,
}: {
  item: Analytics["intent_comparisons"][number];
}) {
  return (
    <>
      <section className="detail-metrics" aria-label="Intent metrics">
        <Card>
          <span>Total sessions</span>
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
        <h2>Example calls</h2>
        <p className="chart-description">
          Representative evidence from the filtered cohort.
        </p>
        <div className="example-call-list">
          {item.session_ids.map((id, index) => (
            <Link key={id} to={`/sessions/${id}`}>
              <span>Example call {index + 1}</span>
              <ExternalLink size={14} />
            </Link>
          ))}
        </div>
      </Card>
    </>
  );
}
