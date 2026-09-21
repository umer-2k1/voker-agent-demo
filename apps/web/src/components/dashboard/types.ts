export type Overview = {
  project: { name: string; slug: string };
  metrics: {
    total_sessions: number;
    active_sessions: number;
    error_count: number;
    average_span_duration_ms: number | null;
  };
};

export type Analytics = {
  session_count: number;
  completed_session_count: number;
  outcomes: Record<string, number>;
  sources: Record<string, number>;
  cost: {
    amount_micros: number | null;
    currency: string | null;
    record_count: number;
  };
  voice_impact_cohorts: Record<
    string,
    { sample_size: number; resolved: number; resolution_rate: number } | null
  >;
  latency: Record<
    string,
    {
      sample_size: number;
      p50_ms: number;
      p95_ms: number;
      max_ms: number;
    } | null
  >;
};

export type VoiceSession = {
  id: string;
  external_session_id: string;
  status: string;
  source: string;
  started_at: string;
  error_count: number;
  event_count: number;
  outcome?: string | null;
};

export type SessionPage = { offset: number; limit: number; total: number };

export type Trace = {
  session: VoiceSession;
  events: Array<{
    id: string;
    event_type: string;
    status: string;
    occurred_at: string;
    duration_ms: number | null;
    payload: Record<string, unknown>;
  }>;
  turns: Array<{
    id: string;
    external_turn_id: string;
    sequence: number;
    speaker: string;
    started_at: string;
    transcript: string | null;
  }>;
  errors: Array<{ id: string; type: string; message: string }>;
  findings: Array<{
    id: string;
    certainty: string;
    severity: string | null;
    statement: string;
    evidence: Array<{
      entity_type: string;
      entity_id: string;
      event_id: string | null;
      turn_id: string | null;
    }>;
  }>;
  analysis_runs: Array<{
    id: string;
    status: string;
    prompt_version: string;
    model: string | null;
  }>;
  recordings: Array<{
    id: string;
    source: string;
    duration_ms: number | null;
    media_type: string | null;
    status: string;
  }>;
};
