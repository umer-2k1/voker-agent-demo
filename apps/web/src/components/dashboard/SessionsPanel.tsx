import { useEffect, useState } from "react";
import {
  BookmarkPlus,
  ChevronLeft,
  ChevronRight,
  Download,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Waves,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { LoadingSkeleton } from "@/components/dashboard/LoadingSkeleton";
import type { SessionPage, VoiceSession } from "@/components/dashboard/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Eyebrow, H2 } from "@/components/ui/typography";
import { cn } from "@/lib/utils";

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

type Option = { value: string; label: string };

const STATUS_OPTIONS: Option[] = [
  { value: "", label: "All statuses" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
];

const SORT_OPTIONS: Option[] = [
  { value: "started_at_desc", label: "Newest first" },
  { value: "started_at_asc", label: "Oldest first" },
  { value: "errors_desc", label: "Most errors" },
  { value: "events_desc", label: "Most activity" },
];

const OUTCOME_OPTIONS: Option[] = [
  { value: "", label: "All outcomes" },
  { value: "success", label: "Success" },
  { value: "failed", label: "Failed" },
  { value: "escalated", label: "Escalated" },
  { value: "abandoned", label: "Abandoned" },
];

const ERROR_OPTIONS: Option[] = [
  { value: "", label: "With or without errors" },
  { value: "true", label: "Has errors" },
  { value: "false", label: "No errors" },
];

function outcomeLabel(session: VoiceSession) {
  if (session.outcome === "resolved" || session.outcome === "success") return "Resolved";
  if (session.outcome === "escalated") return "Escalated";
  if (session.outcome === "abandoned") return "Abandoned";
  return "Unknown";
}

function outcomeVariant(session: VoiceSession) {
  if (session.outcome === "resolved" || session.outcome === "success")
    return "success" as const;
  if (session.outcome === "escalated") return "warning" as const;
  if (session.outcome === "abandoned" || session.outcome === "failed")
    return "destructive" as const;
  return "secondary" as const;
}

/** Coarse review state drives the leading status dot. */
function reviewState(session: VoiceSession) {
  if (session.error_count > 0 || session.status === "failed")
    return { tone: "bg-destructive", label: "Needs review" };
  if (session.status === "in_progress")
    return { tone: "bg-warning", label: "In progress" };
  return { tone: "bg-success", label: "Complete" };
}

function formatStarted(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDuration(ms: number | null | undefined) {
  if (ms == null) return "Live";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

const STATUS_LABELS: Record<string, string> = {
  in_progress: "In progress",
  completed: "Completed",
  failed: "Failed",
};
const OUTCOME_LABELS: Record<string, string> = {
  success: "Success",
  failed: "Failed",
  escalated: "Escalated",
  abandoned: "Abandoned",
};
const SORT_LABELS: Record<string, string> = {
  started_at_asc: "Oldest first",
  errors_desc: "Most errors",
  events_desc: "Most activity",
};
const GENERIC_VIEW_NAME = /^(filter|view)\s+\d+$/i;

/** A saved view is only worth keeping when it actually narrows the queue. */
function isMeaningfulFilter(filter: SavedFilter) {
  return Boolean(
    filter.search ||
      filter.status ||
      filter.source ||
      filter.environment ||
      filter.agent ||
      filter.version ||
      filter.outcome ||
      filter.hasError ||
      filter.startedAfter ||
      filter.startedBefore ||
      filter.minLatency,
  ) || Boolean(filter.sort && filter.sort !== "started_at_desc");
}

/** Turn a stored filter into a human label such as "Failed · livekit". */
function describeFilter(filter: SavedFilter) {
  const parts: string[] = [];
  if (filter.search) parts.push(`“${filter.search}”`);
  if (filter.status) parts.push(STATUS_LABELS[filter.status] ?? filter.status);
  if (filter.outcome) parts.push(OUTCOME_LABELS[filter.outcome] ?? filter.outcome);
  if (filter.hasError === "true") parts.push("Has errors");
  if (filter.hasError === "false") parts.push("No errors");
  if (filter.source) parts.push(filter.source);
  if (filter.agent) parts.push(`Agent: ${filter.agent}`);
  if (filter.version) parts.push(`Version: ${filter.version}`);
  if (filter.environment) parts.push(filter.environment);
  if (filter.startedAfter || filter.startedBefore)
    parts.push(`${filter.startedAfter || "…"} → ${filter.startedBefore || "…"}`);
  if (filter.minLatency) parts.push(`≥ ${filter.minLatency} ms`);
  if (filter.sort && filter.sort !== "started_at_desc")
    parts.push(SORT_LABELS[filter.sort] ?? filter.sort);
  return parts.join(" · ") || "All sessions";
}

/**
 * Drop empty views, rename legacy auto-names ("Filter 1", "View 2") from their
 * filters, and de-duplicate so the chip row stays trustworthy.
 */
function normalizeSavedFilters(rows: SavedFilter[]): SavedFilter[] {
  const seen = new Set<string>();
  const kept: SavedFilter[] = [];
  for (const row of rows) {
    if (!isMeaningfulFilter(row)) continue;
    const needsName =
      !row.name || GENERIC_VIEW_NAME.test(row.name.trim());
    const name = needsName ? describeFilter(row) : row.name;
    if (seen.has(name)) continue;
    seen.add(name);
    kept.push({ ...row, name });
  }
  return kept.slice(-5);
}

function readSavedFilters(): SavedFilter[] {
  try {
    const rows = JSON.parse(
      localStorage.getItem(savedFiltersKey) ?? "[]",
    ) as SavedFilter[];
    return normalizeSavedFilters(rows);
  } catch {
    return [];
  }
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
  className,
}: {
  label: string;
  value: string;
  options: Option[];
  onChange(value: string): void;
  className?: string;
}) {
  return (
    <Select
      value={value === "" ? "all" : value}
      onValueChange={(next) => onChange(next === "all" ? "" : next)}
    >
      <SelectTrigger aria-label={label} className={cn("w-full", className)}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value || "all"} value={option.value || "all"}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function StatChip({
  tone,
  label,
  value,
}: {
  tone: string;
  label: string;
  value: number;
}) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-border bg-muted/60 px-3 py-1 text-xs text-muted-foreground">
      <i className={cn("size-2 rounded-full", tone)} aria-hidden="true" />
      <span className="font-medium text-foreground">{value}</span>
      {label}
    </span>
  );
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
  const [filtersOpen, setFiltersOpen] = useState(false);

  // Persist the normalised list so stale auto-named or empty views do not
  // resurface on the next visit.
  useEffect(() => {
    localStorage.setItem(savedFiltersKey, JSON.stringify(savedFilters));
  }, [savedFilters]);

  // The queue renders in the order the API returns it so the chosen sort
  // (newest first by default) is honoured. "Needs review" is conveyed by the
  // status dot, summary chips, and the dedicated "Most errors" sort.
  const needsReview = sessions.filter((s) => s.error_count > 0).length;
  const inProgress = sessions.filter((s) => s.status === "in_progress").length;
  const complete = sessions.filter(
    (s) => s.status !== "in_progress" && s.error_count === 0,
  ).length;

  const advancedFilterCount = [
    environment,
    agent,
    version,
    outcome,
    hasError,
    startedAfter,
    startedBefore,
    minLatency,
  ].filter(Boolean).length;
  const hasFilters = Boolean(
    search ||
      status ||
      source ||
      environment ||
      agent ||
      version ||
      outcome ||
      hasError ||
      startedAfter ||
      startedBefore ||
      minLatency,
  );

  function clearFilters() {
    onSearch("");
    onStatus("");
    onSource("");
    onEnvironment("");
    onAgent("");
    onVersion("");
    onOutcome("");
    onHasError("");
    onStartedAfter("");
    onStartedBefore("");
    onMinLatency("");
  }

  const filterSnapshot: SavedFilter = {
    name: "",
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
  };
  const canSaveView = isMeaningfulFilter(filterSnapshot);

  function applySavedFilter(filter: SavedFilter) {
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
  }

  function saveCurrentFilter() {
    if (!isMeaningfulFilter(filterSnapshot)) return;
    const named = { ...filterSnapshot, name: describeFilter(filterSnapshot) };
    const next = normalizeSavedFilters([...savedFilters, named]);
    localStorage.setItem(savedFiltersKey, JSON.stringify(next));
    setSavedFilters(next);
    const saved = next.find((filter) => filter.name === named.name);
    toast.success(`Saved view “${saved?.name ?? named.name}”`);
  }

  function removeSavedFilter(name: string) {
    const next = savedFilters.filter((filter) => filter.name !== name);
    localStorage.setItem(savedFiltersKey, JSON.stringify(next));
    setSavedFilters(next);
    toast(`Removed view “${name}”`);
  }

  function exportSessions() {
    if (!sessions.length) return;
    const header = [
      "external_session_id",
      "status",
      "outcome",
      "intent",
      "source",
      "environment",
      "started_at",
      "duration_ms",
      "errors",
      "events",
    ];
    const rows = sessions.map((s) => [
      s.external_session_id,
      s.status,
      s.outcome ?? "",
      s.intent ?? "",
      s.source,
      s.environment ?? "",
      s.started_at,
      s.duration_ms ?? "",
      s.error_count,
      s.event_count,
    ]);
    const cell = (value: string | number) => {
      const text = String(value);
      return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
    };
    const csv = [header, ...rows]
      .map((row) => row.map(cell).join(","))
      .join("\n");
    const url = URL.createObjectURL(
      new Blob([csv], { type: "text/csv;charset=utf-8" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `voker-sessions-${new Date().toISOString().slice(0, 10)}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
    toast.success(`Exported ${sessions.length} sessions`);
  }

  return (
    <Card className="overflow-hidden" id="sessions-queue">
      <CardHeader className="flex flex-col gap-4 border-b border-border sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1">
          <Eyebrow>Investigation queue</Eyebrow>
          <H2>Sessions needing attention</H2>
          <p className="text-sm text-muted-foreground">
            {needsReview
              ? `${needsReview} of ${page.total} captured sessions need review.`
              : `${page.total} captured sessions are healthy.`}
          </p>
        </div>
        <div
          className="flex flex-wrap items-center gap-2"
          aria-label="Session review summary"
        >
          <StatChip tone="bg-destructive" label="need review" value={needsReview} />
          <StatChip tone="bg-warning" label="in progress" value={inProgress} />
          <StatChip tone="bg-success" label="complete" value={complete} />
          <Button
            variant="outline"
            size="sm"
            type="button"
            disabled={!sessions.length}
            onClick={exportSessions}
          >
            <Download data-icon="inline-start" />
            Export
          </Button>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        <div className="flex flex-col gap-3 border-b border-border p-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(0,1.6fr)_11rem_10rem_11rem]">
            <div className="relative min-w-0 sm:col-span-2 xl:col-span-1">
              <Search
                className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                aria-label="Search sessions"
                className="pl-9"
                placeholder="Search session ID"
                value={search}
                onChange={(event) => onSearch(event.target.value)}
              />
            </div>
            <FilterSelect
              label="Filter by status"
              value={status}
              options={STATUS_OPTIONS}
              onChange={onStatus}
            />
            <Input
              aria-label="Filter by source"
              placeholder="Source"
              value={source}
              onChange={(event) => onSource(event.target.value)}
            />
            <FilterSelect
              label="Sort sessions"
              value={sort}
              options={SORT_OPTIONS}
              onChange={onSort}
            />
          </div>

          <Collapsible open={filtersOpen} onOpenChange={setFiltersOpen}>
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="w-fit text-muted-foreground"
              >
                <SlidersHorizontal data-icon="inline-start" />
                More filters
                {advancedFilterCount ? (
                  <Badge variant="info" className="ml-1">
                    {advancedFilterCount}
                  </Badge>
                ) : null}
                <ChevronRight
                  data-icon="inline-end"
                  className={cn(
                    "transition-transform",
                    filtersOpen && "rotate-90",
                  )}
                />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-3">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
                <FilterSelect
                  label="Filter by outcome"
                  value={outcome}
                  options={OUTCOME_OPTIONS}
                  onChange={onOutcome}
                />
                <FilterSelect
                  label="Filter by errors"
                  value={hasError}
                  options={ERROR_OPTIONS}
                  onChange={onHasError}
                />
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
            </CollapsibleContent>
          </Collapsible>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              Saved views
            </span>
            {savedFilters.length ? (
              savedFilters.map((filter) => (
                <span
                  key={filter.name}
                  className="inline-flex items-center overflow-hidden rounded-full border border-border bg-secondary text-xs text-secondary-foreground"
                >
                  <button
                    type="button"
                    className="max-w-52 truncate px-2.5 py-1 font-medium hover:bg-accent"
                    onClick={() => applySavedFilter(filter)}
                    title={filter.name}
                  >
                    {filter.name}
                  </button>
                  <button
                    type="button"
                    aria-label={`Remove saved view ${filter.name}`}
                    className="border-l border-border/70 px-1.5 py-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                    onClick={() => removeSavedFilter(filter.name)}
                  >
                    <X className="size-3" aria-hidden="true" />
                  </button>
                </span>
              ))
            ) : (
              <span className="text-xs text-muted-foreground">
                No saved views yet.
              </span>
            )}
            <Button
              className="rounded-full"
              size="xs"
              variant="outline"
              type="button"
              onClick={saveCurrentFilter}
              disabled={!canSaveView}
              title={
                canSaveView
                  ? "Save the current filters"
                  : "Set at least one filter to save a view"
              }
            >
              <BookmarkPlus data-icon="inline-start" />
              Save current view
            </Button>
            {hasFilters ? (
              <Button
                className="rounded-full text-muted-foreground"
                size="xs"
                variant="ghost"
                type="button"
                onClick={clearFilters}
              >
                <RotateCcw data-icon="inline-start" />
                Reset
              </Button>
            ) : null}
          </div>
        </div>

        <div
          className="flex flex-wrap items-center gap-2 px-4 py-3 text-xs text-muted-foreground"
          aria-label="Session status legend"
        >
          <Badge variant="destructive">Needs review</Badge>
          <Badge variant="warning">In progress</Badge>
          <Badge variant="success">Complete</Badge>
          <Badge variant="secondary">Unknown outcome</Badge>
          <span>Intent and resolution are captured on the same session record.</span>
        </div>

        {loading ? <LoadingSkeleton rows={5} /> : null}

        {!loading && !sessions.length ? (
          <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
            <span className="flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <Waves className="size-5" aria-hidden="true" />
            </span>
            <strong className="text-base font-semibold">
              {hasFilters
                ? "No sessions match this view."
                : "Your investigation queue is ready."}
            </strong>
            <p className="max-w-md text-sm leading-6 text-muted-foreground">
              {hasFilters
                ? "Clear a filter or try a saved view to broaden the queue."
                : "Connect the Python SDK or send canonical events. The first call will appear here with its trace, transcript, and evidence."}
            </p>
            {hasFilters ? (
              <Button variant="outline" size="sm" onClick={clearFilters}>
                <RotateCcw data-icon="inline-start" />
                Reset filters
              </Button>
            ) : null}
          </div>
        ) : null}

        {sessions.length ? (
          <Table aria-label="Session investigation queue">
            <TableHeader className="[&_tr]:border-border">
              <TableRow className="hover:bg-transparent">
                <TableHead>Session</TableHead>
                <TableHead>Intent</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead className="text-right">Signals</TableHead>
                <TableHead className="text-right">Events</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sessions.map((session) => {
                const review = reviewState(session);
                return (
                  <TableRow
                    key={session.id}
                    data-state={selectedId === session.id ? "selected" : undefined}
                  >
                    <TableCell className="min-w-64">
                      <button
                        className="group flex w-full items-center justify-between gap-3 rounded-sm text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => onSelect(session.id)}
                      >
                        <span className="flex min-w-0 items-center gap-2.5">
                          <i
                            className={cn("size-2 shrink-0 rounded-full", review.tone)}
                            aria-hidden="true"
                          />
                          <span className="flex min-w-0 flex-col">
                            <span
                              className="truncate font-medium text-foreground group-hover:underline"
                              title={session.external_session_id}
                            >
                              {session.external_session_id}
                            </span>
                            <span
                              className="truncate text-xs text-muted-foreground"
                              title={`${session.source} · ${session.environment ?? "default"} · ${formatStarted(session.started_at)}`}
                            >
                              {session.source} · {session.environment ?? "default"} ·{" "}
                              {formatStarted(session.started_at)}
                            </span>
                          </span>
                        </span>
                        <ChevronRight
                          className="size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
                          aria-hidden="true"
                        />
                      </button>
                    </TableCell>
                    <TableCell>
                      {session.intent ? (
                        <div className="space-y-1">
                          <p
                            className="max-w-44 truncate font-medium text-foreground"
                            title={session.intent.replaceAll("_", " ")}
                          >
                            {session.intent.replaceAll("_", " ")}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {session.intent_confidence != null
                              ? `${Math.round(session.intent_confidence * 100)}% confidence`
                              : session.intent_source ?? "observed"}
                          </p>
                        </div>
                      ) : (
                        <span className="text-muted-foreground">Not observed</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant={outcomeVariant(session)}>
                        {outcomeLabel(session)}
                      </Badge>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {session.outcome_source ?? "No resolution evidence"}
                      </p>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <p
                        className={cn(
                          session.error_count && "font-semibold text-destructive",
                        )}
                      >
                        {session.error_count
                          ? `${session.error_count} error${session.error_count === 1 ? "" : "s"}`
                          : review.label}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatDuration(session.duration_ms)}
                      </p>
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs tabular-nums text-muted-foreground">
                      {session.event_count}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        ) : null}

        {page.total > page.limit ? (
          <div className="flex items-center justify-between border-t border-border px-4 py-3 text-xs text-muted-foreground">
            <Button
              variant="outline"
              size="sm"
              disabled={page.offset === 0}
              onClick={() => onPage(Math.max(0, page.offset - page.limit))}
            >
              <ChevronLeft data-icon="inline-start" />
              Previous
            </Button>
            <span className="tabular-nums">
              {page.offset + 1}–{Math.min(page.offset + page.limit, page.total)} of{" "}
              {page.total}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page.offset + page.limit >= page.total}
              onClick={() => onPage(page.offset + page.limit)}
            >
              Next
              <ChevronRight data-icon="inline-end" />
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
