# Development handoff

## Suggested stack
- Next.js / React / TypeScript
- Tailwind CSS
- shadcn/ui primitives
- lucide-react icons
- Recharts or Tremor for charts

## Route structure
- `/voice-impact` — overview
- `/voice-impact/intents/[intent]` — intent drill-down
- `/voice-impact/sessions/[id]` — call playback / evidence
- `/voice-impact/benchmark` — optional STT benchmark

## Recommended component tree
- `AppShell`
- `SidebarNav`
- `PageHeader`
- `MetricCard`
- `ImpactAlert`
- `IntentResolutionList`
- `VoiceIssueImpactList`
- `ResolutionCohortChart`
- `IntentImpactTable`
- `VoiceFactorTable`
- `InsightCard`
- `CallPlayer`
- `TranscriptTimeline`
- `RootCausePanel`
- `BenchmarkTable`

## Data model minimum
```ts
type VoiceSession = {
  id: string;
  intent: string;
  resolved: boolean;
  corrected: boolean;
  escalated: boolean;
  interruptionCount: number;
  deadAirMs: number;
  talkOverMs: number;
  sttFinalizationMs: number;
  llmTtftMs: number;
  ttsFirstAudioMs: number;
  endToEndMs: number;
  transcript?: Array<{speaker:'user'|'agent'; text:string; atMs:number}>;
};
```

## Important analytics rule
The prototype can demonstrate correlations and cohorts. Do not label a factor as causal unless your dataset/experiment actually supports causality.
