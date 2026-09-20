# Component specification

## App shell
- 224px left sidebar on desktop.
- Main content uses 24px page padding and a 16px card grid.
- Page background `#F8FAFC`; cards remain white.

## Sidebar
- Active row: `#004D43`, white label/icon.
- Inactive row: transparent, text `#334155`; hover `#EAF5F3`.
- Recommended width: 224px; 40px row height.

## MetricCard
Use for Total Calls, Resolution, Correction, Escalation, and p90 latency.
- Height: 88–104px.
- Label: 12–14px muted.
- Value: 24–28px semibold.
- Delta sits next to value; semantic color only after the direction is understood.

## ImpactAlert
A full-width insight banner placed directly below KPI cards.
- Strong statement first: “3 voice issues are significantly impacting resolution.”
- Supporting text describes the kind of evidence.
- CTA: `View insights`.

## IntentImpactTable
Columns: Intent, Resolution Rate, Correction Rate, Top Voice Issue, Affected Calls, View.
- Failed/problematic rows can use a very light red surface, never a saturated fill.
- Sort by impact by default.

## VoiceIssueImpact
Ranked list of voice factors with effect size, e.g. `High interruption rate — -44 pp`.
- Show “associated with” rather than making unsupported causal claims.

## Scatter / comparison chart
- Green = resolved or healthy cohort.
- Red = failed/problem cohort.
- Always label axes and cohort thresholds.
- Put the key insight next to the chart, not buried in a tooltip.

## IntentDetail
Header with intent name and top KPIs. Tabs: Overview, Voice Issues, Example Calls, User Journey.
Primary content: factor comparison + scatter plot + example calls.

## CallPlayback
Audio waveform + transcript + timeline + key takeaways.
Root-cause panel must show evidence bullets and avoid claiming certainty when only correlation is available.

## STTBenchmark
Table: Provider, WER, Critical Entity Accuracy, Finalization p90, Intent Recovery.
Highlight the recommended tradeoff, not simply the numerically lowest WER.

## Badges
- Resolved: success surface/text.
- Failed: danger surface/text.
- In Progress: info.
- Escalated: warning.
