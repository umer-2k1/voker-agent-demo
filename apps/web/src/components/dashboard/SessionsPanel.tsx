import { Card, CardHeader } from "@/components/ui/card";
import { useState } from "react";
import { LoadingSkeleton } from "@/components/dashboard/LoadingSkeleton";
import type { SessionPage, VoiceSession } from "@/components/dashboard/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type SavedFilter = {
  name: string;
  search: string;
  status: string;
  source: string;
  environment: string;
  agent: string;
  version: string;
  outcome: string;
  hasError: string;
  startedAfter: string;
  startedBefore: string;
  minLatency: string;
  sort: string;
};
const savedFiltersKey = "voker-session-filters";

function outcomeLabel(session: VoiceSession) {
  if (session.outcome === "resolved" || session.outcome === "success") return "Resolved";
  if (session.outcome === "escalated") return "Escalated";
  if (session.outcome === "abandoned") return "Abandoned";
  return "Unknown";
}

function statusVariant(session: VoiceSession) {
  if (session.error_count || session.status === "failed") return "destructive" as const;
  if (session.outcome === "resolved" || session.outcome === "success") return "default" as const;
  return "secondary" as const;
}

function readSavedFilters(): SavedFilter[] {
  try {
    return JSON.parse(
      localStorage.getItem(savedFiltersKey) ?? "[]",
    ) as SavedFilter[];
  } catch {
    return [];
  }
}

export function SessionsPanel({
  sessions,
  page,
  loading,
  selectedId,
  search,
  status,
  source,
  environment,
  agent,
  version,
  outcome,
  hasError,
  startedAfter,
  startedBefore,
  minLatency,
  sort,
  onSearch,
  onStatus,
  onSource,
  onEnvironment,
  onAgent,
  onVersion,
  onOutcome,
  onHasError,
  onStartedAfter,
  onStartedBefore,
  onMinLatency,
  onSort,
  onSelect,
  onPage,
}: {
  sessions: VoiceSession[];
  page: SessionPage;
  loading: boolean;
  selectedId?: string;
  search: string;
  status: string;
  source: string;
  environment: string;
  agent: string;
  version: string;
  outcome: string;
  hasError: string;
  startedAfter: string;
  startedBefore: string;
  minLatency: string;
  sort: string;
  onSearch(value: string): void;
  onStatus(value: string): void;
  onSource(value: string): void;
  onEnvironment(value: string): void;
  onAgent(value: string): void;
  onVersion(value: string): void;
  onOutcome(value: string): void;
  onHasError(value: string): void;
  onStartedAfter(value: string): void;
  onStartedBefore(value: string): void;
  onMinLatency(value: string): void;
  onSort(value: string): void;
  onSelect(id: string): void;
  onPage(offset: number): void;
}) {
  const [savedFilters, setSavedFilters] =
    useState<SavedFilter[]>(readSavedFilters);
  const triagedSessions = [...sessions].sort((left, right) => {
    const leftPriority =
      left.error_count > 0 ? 0 : left.status === "in_progress" ? 1 : 2;
    const rightPriority =
      right.error_count > 0 ? 0 : right.status === "in_progress" ? 1 : 2;
    return leftPriority - rightPriority;
  });
  const needsAttention = sessions.filter(
    (session) => session.error_count > 0,
  ).length;
  function saveCurrentFilter() {
    const name = `Filter ${savedFilters.length + 1}`;
    const next = [
      ...savedFilters,
      {
        name,
        search,
        status,
        source,
        environment,
        agent,
        version,
        outcome,
        hasError,
        startedAfter,
        startedBefore,
        minLatency,
        sort,
      },
    ].slice(-5);
    localStorage.setItem(savedFiltersKey, JSON.stringify(next));
    setSavedFilters(next);
  }
  return (
    <Card className="panel sessions-panel" id="sessions">
      <CardHeader className="panel-heading">
        <div>
          <p className="eyebrow">Investigation queue</p>
          <h2>Sessions needing attention</h2>
        </div>
        <span>
          {needsAttention
            ? `${needsAttention} need review`
            : `${page.total} captured`}
        </span>
      </CardHeader>
      {loading ? <LoadingSkeleton rows={5} /> : null}
      <div className="session-controls">
        <div className="session-filters">
          <Input
            aria-label="Search sessions"
            placeholder="Search session ID"
            value={search}
            onChange={(event) => onSearch(event.target.value)}
          />
          <NativeSelect
            aria-label="Filter by status"
            value={status}
            onChange={(event) => onStatus(event.target.value)}
          >
            <option value="">All statuses</option>
            <option value="in_progress">In progress</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </NativeSelect>
          <Input
            aria-label="Filter by source"
            placeholder="Source"
            value={source}
            onChange={(event) => onSource(event.target.value)}
          />
          <NativeSelect
            aria-label="Sort sessions"
            value={sort}
            onChange={(event) => onSort(event.target.value)}
          >
            <option value="started_at_desc">Newest first</option>
            <option value="started_at_asc">Oldest first</option>
            <option value="errors_desc">Most errors</option>
            <option value="events_desc">Most activity</option>
          </NativeSelect>
        </div>
        <details className="rounded-lg border border-emerald-950/10 bg-emerald-50/30 p-3">
          <summary className="cursor-pointer text-sm font-semibold text-emerald-900">
            More filters
          </summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Input
              aria-label="Filter by environment"
              placeholder="Environment"
              value={environment}
              onChange={(event) => onEnvironment(event.target.value)}
            />
            <Input
              aria-label="Filter by agent"
              placeholder="Agent"
              value={agent}
              onChange={(event) => onAgent(event.target.value)}
            />
            <Input
              aria-label="Filter by agent version"
              placeholder="Agent version"
              value={version}
              onChange={(event) => onVersion(event.target.value)}
            />
            <NativeSelect
              aria-label="Filter by outcome"
              value={outcome}
              onChange={(event) => onOutcome(event.target.value)}
            >
              <option value="">All outcomes</option>
              <option value="success">Success</option>
              <option value="failed">Failed</option>
              <option value="escalated">Escalated</option>
              <option value="abandoned">Abandoned</option>
            </NativeSelect>
            <NativeSelect
              aria-label="Filter by errors"
              value={hasError}
              onChange={(event) => onHasError(event.target.value)}
            >
              <option value="">With or without errors</option>
              <option value="true">Has errors</option>
              <option value="false">No errors</option>
            </NativeSelect>
            <Input
              aria-label="Started after"
              type="date"
              value={startedAfter}
              onChange={(event) => onStartedAfter(event.target.value)}
            />
            <Input
              aria-label="Started before"
              type="date"
              value={startedBefore}
              onChange={(event) => onStartedBefore(event.target.value)}
            />
            <Input
              aria-label="Minimum span latency in milliseconds"
              inputMode="numeric"
              min="0"
              type="number"
              placeholder="Min latency (ms)"
              value={minLatency}
              onChange={(event) => onMinLatency(event.target.value)}
            />
          </div>
        </details>
        <div className="saved-filter-row">
          <span>Saved views</span>
          {savedFilters.map((filter) => (
            <Button
              key={`${filter.name}-${filter.sort}`}
              type="button"
              onClick={() => {
                onSearch(filter.search);
                onStatus(filter.status);
                onSource(filter.source);
                onEnvironment(filter.environment ?? "");
                onAgent(filter.agent ?? "");
                onVersion(filter.version ?? "");
                onOutcome(filter.outcome ?? "");
                onHasError(filter.hasError ?? "");
                onStartedAfter(filter.startedAfter ?? "");
                onStartedBefore(filter.startedBefore ?? "");
                onMinLatency(filter.minLatency ?? "");
                onSort(filter.sort);
              }}
            >
              {filter.name}
            </Button>
          ))}
          <Button
            className="save-filter"
            size="sm"
            variant="outline"
            type="button"
            onClick={saveCurrentFilter}
          >
            Save current view
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 px-5 pb-3 text-xs text-muted-foreground" aria-label="Session status legend">
        <Badge variant="destructive">Needs review</Badge>
        <Badge variant="secondary">In progress</Badge>
        <Badge variant="outline">Complete</Badge>
        <span>Intent and resolution are captured on the same session record.</span>
      </div>
      {!loading && !sessions.length ? (
        <div className="session-empty-state">
          <strong>
            {search ||
            status ||
            source ||
            environment ||
            agent ||
            version ||
            outcome ||
            hasError ||
            startedAfter ||
            startedBefore ||
            minLatency
              ? "No sessions match this view."
              : "Your investigation queue is ready."}
          </strong>
          <p>
            {search ||
            status ||
            source ||
            environment ||
            agent ||
            version ||
            outcome ||
            hasError ||
            startedAfter ||
            startedBefore ||
            minLatency
              ? "Clear a filter or try a saved view to broaden the queue."
              : "Connect the Python SDK or send canonical events. The first call will appear here with its trace, transcript, and evidence."}
          </p>
        </div>
      ) : null}
      {sessions.length ? (
        <div className="px-3 pb-3">
          <Table aria-label="Session investigation queue">
            <TableHeader>
              <TableRow>
                <TableHead>Session</TableHead>
                <TableHead>Intent</TableHead>
                <TableHead>Resolution</TableHead>
                <TableHead className="text-right">Signals</TableHead>
                <TableHead className="text-right">Events</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {triagedSessions.map((session) => (
                <TableRow data-state={selectedId === session.id ? "selected" : undefined} key={session.id}>
                  <TableCell className="min-w-64">
                    <button
                      className="group flex w-full flex-col items-start gap-1 rounded-sm text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={() => onSelect(session.id)}
                    >
                      <span className="font-medium text-foreground group-hover:underline">
                        {session.external_session_id}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {session.source} · {session.environment ?? "default"} · {new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date(session.started_at))}
                      </span>
                    </button>
                  </TableCell>
                  <TableCell>
                    {session.intent ? (
                      <div className="space-y-1">
                        <p className="max-w-44 truncate font-medium text-foreground">{session.intent.replaceAll("_", " ")}</p>
                        <p className="text-xs text-muted-foreground">
                          {session.intent_confidence != null ? `${Math.round(session.intent_confidence * 100)}% confidence` : session.intent_source ?? "observed"}
                        </p>
                      </div>
                    ) : <span className="text-muted-foreground">Not observed</span>}
                  </TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(session)}>{outcomeLabel(session)}</Badge>
                    <p className="mt-1 text-xs text-muted-foreground">{session.outcome_source ?? "No resolution evidence"}</p>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    <p className={session.error_count ? "font-semibold text-destructive" : "text-foreground"}>
                      {session.error_count ? `${session.error_count} error${session.error_count === 1 ? "" : "s"}` : session.status.replaceAll("_", " ")}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {session.duration_ms == null ? "Live" : `${(session.duration_ms / 1000).toFixed(1)}s`}
                    </p>
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs tabular-nums text-muted-foreground">{session.event_count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
      {page.total > page.limit ? (
        <div className="pagination">
          <Button
            disabled={page.offset === 0}
            onClick={() => onPage(Math.max(0, page.offset - page.limit))}
          >
            Previous
          </Button>
          <span>
            {page.offset + 1}–{Math.min(page.offset + page.limit, page.total)}{" "}
            of {page.total}
          </span>
          <Button
            disabled={page.offset + page.limit >= page.total}
            onClick={() => onPage(page.offset + page.limit)}
          >
            Next
          </Button>
        </div>
      ) : null}
    </Card>
  );
}
