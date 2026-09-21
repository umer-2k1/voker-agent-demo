import { Card, CardHeader } from "@/components/ui/card";
import { LoadingSkeleton } from "@/components/dashboard/LoadingSkeleton";
import type { SessionPage, VoiceSession } from "@/components/dashboard/types";

export function SessionsPanel({
  sessions,
  page,
  loading,
  selectedId,
  search,
  status,
  source,
  onSearch,
  onStatus,
  onSource,
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
  onSearch(value: string): void;
  onStatus(value: string): void;
  onSource(value: string): void;
  onSelect(id: string): void;
  onPage(offset: number): void;
}) {
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
      {!loading && !sessions.length ? (
        <p className="empty-state">
          No sessions yet. Connect the Python SDK or send canonical events to
          begin.
        </p>
      ) : null}
      <div className="session-filters">
        <input
          aria-label="Search sessions"
          placeholder="Search session ID"
          value={search}
          onChange={(event) => onSearch(event.target.value)}
        />
        <select
          aria-label="Filter by status"
          value={status}
          onChange={(event) => onStatus(event.target.value)}
        >
          <option value="">All statuses</option>
          <option value="in_progress">In progress</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </select>
        <input
          aria-label="Filter by source"
          placeholder="Source"
          value={source}
          onChange={(event) => onSource(event.target.value)}
        />
      </div>
      <div className="session-list">
        {triagedSessions.map((session) => (
          <button
            key={session.id}
            className={`session-row ${selectedId === session.id ? "selected" : ""}`}
            onClick={() => onSelect(session.id)}
          >
            <span
              className={`status-dot ${session.error_count ? "error" : session.status}`}
            />
            <span className="session-name">
              {session.external_session_id}
              <small>
                {session.source} ·{" "}
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
                  : session.status}
              </small>
            </span>
          </button>
        ))}
      </div>
      {page.total > page.limit ? (
        <div className="pagination">
          <button
            disabled={page.offset === 0}
            onClick={() => onPage(Math.max(0, page.offset - page.limit))}
          >
            Previous
          </button>
          <span>
            {page.offset + 1}–{Math.min(page.offset + page.limit, page.total)}{" "}
            of {page.total}
          </span>
          <button
            disabled={page.offset + page.limit >= page.total}
            onClick={() => onPage(page.offset + page.limit)}
          >
            Next
          </button>
        </div>
      ) : null}
    </Card>
  );
}
