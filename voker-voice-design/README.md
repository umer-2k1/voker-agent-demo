# Voker Voice Impact — Design Package

A developer-ready design handoff for the **Voice Impact** prototype.

## What the prototype does
Voice Impact connects voice-specific telemetry (interruptions, STT finalization, dead air, talk-over, latency) with Voker-style outcome analytics (intent, resolution, correction, escalation). The central question is:

> Which voice behavior is most associated with low resolution for this intent?

## Package contents
- `screens/` — separate UI mockups for the main demo flow.
- `design-system/` — palette, typography samples, JSON tokens, CSS variables, Tailwind theme.
- `icons/` — Lucide icon mapping and usage rules.
- `assets/` — reusable SVG illustration/background assets.
- `docs/` — component specs, data/copy guidance, demo flow, and dev handoff.
- `reference/` — the supplied Voker visual reference plus earlier concept image.

## Primary screens
1. Voice Impact overview.
2. Intent detail / voice issue correlation.
3. Call playback + evidence / likely contributing factors.
4. Optional STT provider benchmark.

## Brand direction
- Primary: `#004D43`
- Light primary: `#DDEAED`
- Typography: Inter (recommended; font files are intentionally not bundled).
- Design language: light product UI, clean white cards, low-noise borders, dark teal navigation, data-first layouts.

## Development note
This is a prototype design kit, not an official Voker brand package. Replace any placeholder logos/branding with authorized production assets before shipping publicly.
