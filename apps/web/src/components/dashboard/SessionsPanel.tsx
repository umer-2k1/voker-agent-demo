import { Card, CardHeader } from "@/components/ui/card";
import { useState } from "react";
import { LoadingSkeleton } from "@/components/dashboard/LoadingSkeleton";
import type { SessionPage, VoiceSession } from "@/components/dashboard/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";

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
      <div className="status-legend" aria-label="Session status legend">
        <span>
          <i className="status-dot error" /> Needs review
        </span>
        <span>
          <i className="status-dot in_progress" /> In progress
        </span>
        <span>
          <i className="status-dot completed" /> Completed
        </span>
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
      <div className="session-list">
        {triagedSessions.map((session) => (
          <Button
            key={session.id}
            className={`session-row !h-auto ${selectedId === session.id ? "selected" : ""}`}
            onClick={() => onSelect(session.id)}
          >
            <span
              className={`status-dot ${session.error_count ? "error" : session.status}`}
            />
            <span className="session-name">
              {session.external_session_id}
              <small>
                {session.source} ·{" "}
                {session.environment ? `${session.environment} · ` : ""}
                {new Intl.DateTimeFormat(undefined, {
                  hour: "numeric",
                  minute: "2-digit",
                }).format(new Date(session.started_at))}
              </small>
            </span>
            <span className="session-events">
              {session.event_count} events
              <small>
                {session.error_count
                  ? `${session.error_count} errors`
                  : (session.outcome ?? session.status)}
              </small>
            </span>
          </Button>
        ))}
      </div>
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
