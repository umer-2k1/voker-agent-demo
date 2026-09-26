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
  filters: {
    environment: string | null;
    started_after: string | null;
    started_before: string | null;
  };
  session_count: number;
  completed_session_count: number;
  outcomes: Record<string, number>;
  sources: Record<string, number>;
  cost: {
    amount_micros: number | null;
    exact_amount_micros: number;
    estimated_amount_micros: number;
    currency: string | null;
    record_count: number;
    exact_record_count: number;
    estimated_record_count: number;
  };
  usage: {
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
    audio_seconds: number | null;
    tts_characters: number | null;
  };
  voice_impact_cohorts: Record<
    string,
    {
      sample_size: number;
      resolved: number;
      resolution_rate: number;
      session_ids: string[];
    } | null
  >;
  latency: Record<
    string,
    {
      sample_size: number;
      p50_ms: number;
      p90_ms: number;
      p95_ms: number;
      max_ms: number;
    } | null
  >;
  volume_trend: Array<{ date: string; sessions: number }>;
  intent_comparisons: ComparisonItem[];
  interruption_resolution_points: Array<{
    session_id: string;
    intent: string;
    interruptions: number;
    resolution: number;
    outcome: string;
  }>;
  voice_issue_impacts: Array<{
    key: string;
    label: string;
    affected_resolution_rate: number;
    baseline_resolution_rate: number;
    impact_percentage_points: number;
    sample_size: number;
    session_ids: string[];
  }>;
  rates: Record<
    "resolution" | "correction" | "escalation" | "abandonment" | "error",
    number | null
  >;
  failure_categories: Record<string, number>;
  failure_category_insights: Array<{
    category: string;
    count: number;
    session_ids: string[];
  }>;
  tool_failure_count: number;
  voice_behavior: {
    interruption_sessions: number;
    talk_over_sessions: number;
    dead_air_sessions: number;
    correction_sessions: number;
  };
  insights: Array<{
    key: string;
    label: string;
    count: number;
    session_ids: string[];
  }>;
  comparisons: {
    agents: ComparisonItem[];
    versions: ComparisonItem[];
    platforms: ComparisonItem[];
    providers: ComparisonItem[];
    models: ComparisonItem[];
  };
  outcome_sources: { explicit: number; inferred: number; unknown: number };
};

export type ComparisonItem = {
  label: string;
  sessions: number;
  known_outcomes: number;
  resolved: number;
  resolution_rate: number | null;
  session_ids: string[];
};

export type VoiceSession = {
  id: string;
  external_session_id: string;
  status: string;
  source: string;
  started_at: string;
  ended_at?: string | null;
  error_count: number;
  event_count: number;
  outcome?: string | null;
  outcome_source?: string | null;
  duration_ms?: number | null;
  environment?: string | null;
  agent?: string | null;
  agent_version?: string | null;
};

export type SessionPage = { offset: number; limit: number; total: number };

export type Trace = {
  session: VoiceSession;
  collection: {
    last_event_type: string | null;
    last_event_at: string | null;
    last_received_at: string | null;
    terminal_event_received: boolean;
    diagnostic_log: string;
  };
  event_page: SessionPage;
  voice_behavior: {
    interruptions: number;
    talk_over: number;
    dead_air: number;
    corrections: number;
    abandonment: number;
  };
  events: Array<{
    id: string;
    event_id: string;
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
    ended_at: string | null;
    transcript: string | null;
    attributes: Record<string, unknown>;
  }>;
  spans: Array<{
    id: string;
    external_span_id: string;
    parent_external_span_id: string | null;
    name: string;
    kind: string;
    status: string;
    source: string | null;
    turn_id: string | null;
    agent_run_id: string | null;
    started_at: string;
    ended_at: string | null;
    duration_ms: number | null;
    attributes: Record<string, unknown>;
    input: Record<string, unknown> | null;
    output: Record<string, unknown> | null;
  }>;
  agent_runs: Array<{
    id: string;
    external_run_id: string;
    parent_run_id: string | null;
    turn_id: string | null;
    name: string;
    status: string;
    started_at: string;
    ended_at: string | null;
    agent: string | null;
    version: string | null;
    attributes: Record<string, unknown>;
  }>;
  errors: Array<{
    id: string;
    type: string;
    code: string | null;
    message: string;
    retryable: boolean;
    retry_count: number;
    event_id: string | null;
    span_id: string | null;
    created_at: string;
  }>;
  usage: Array<{
    provider: string | null;
    model: string | null;
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
    audio_seconds: number | null;
    tts_characters: number | null;
  }>;
  costs: Array<{
    amount_micros: number;
    currency: string;
    source: string;
    is_estimate: boolean;
    rate_card_version: string | null;
    span_id: string | null;
  }>;
  findings: Array<{
    id: string;
    certainty: string;
    severity: string | null;
    statement: string;
    confidence: number | null;
    rule_id: string | null;
    rule_version: string | null;
    attributes: Record<string, unknown>;
    evidence: Array<{
      entity_type: string;
      entity_id: string;
      event_id: string | null;
      span_id: string | null;
      turn_id: string | null;
    }>;
  }>;
  analysis_runs: Array<{
    id: string;
    status: string;
    analysis_version: number;
    prompt_version: string;
    model: string | null;
    schema_version: string;
    evaluator_latency_ms: number | null;
    input_tokens: number | null;
    output_tokens: number | null;
    cost_micros: number | null;
    result: Record<string, unknown> | null;
    error: string | null;
    started_at: string | null;
    completed_at: string | null;
    created_at: string;
  }>;
  recordings: Array<{
    id: string;
    source: string;
    duration_ms: number | null;
    media_type: string | null;
    status: string;
    expires_at: string | null;
  }>;
};

export type ProjectSetup = {
  project: { id: string; name: string; slug: string };
  environments: Array<{ id: string; name: string; slug: string }>;
  integrations: Array<{
    id: string;
    provider: string;
    name: string;
    status: string;
    selected_resources: ProviderResource[];
    webhook_url: string | null;
    forwarding_enabled: boolean;
    forwarding_destinations: string[];
    forwarding_failures: number;
    last_delivery_at: string | null;
    normalization_state: "processed" | "pending" | "not_yet_observed";
  }>;
  last_received_event_at: string | null;
  observed_stages: string[];
};

export type ProviderResource = {
  id: string;
  name: string;
  version: string | null;
  existing_webhook_url: string | null;
};
