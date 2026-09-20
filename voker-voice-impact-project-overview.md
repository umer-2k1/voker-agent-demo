# Voker Voice Impact — Project Overview

## Abstract

**Voker Voice Impact** is a focused prototype that extends Voker's agent analytics into the voice-agent domain.

The core problem is simple: traditional voice observability tools can tell teams that a call had high latency, interruptions, dead air, or slow speech finalization, while Voker can tell teams whether an agent resolved the user's intent. What is often missing is the bridge between those two layers.

This prototype answers:

> **Which voice-quality issues are actually associated with failed resolutions, user corrections, escalations, or abandoned conversations?**

Instead of building a complete voice observability platform, the demo focuses on correlating a small set of voice telemetry signals with Voker-style product outcomes and presenting those relationships in a way that is immediately understandable to product and engineering teams.

The project is intentionally narrow so it can be built quickly, demonstrated clearly, and feel like a feature Voker could realistically add to its product.

---

## Background

Voker focuses on **Agent Analytics**: understanding what users are trying to do, whether the agent succeeds, where users correct the agent, what intents are common, and how agent behavior affects outcomes.

Voice-agent platforms introduce another layer of failure modes that do not exist in text-only agents. A voice conversation can fail even when the underlying LLM is capable of answering correctly.

Examples include:

- the speech-to-text provider finalizes too slowly;
- the agent interrupts the user before the user finishes speaking;
- the user and agent talk over each other;
- long periods of dead air make the experience feel broken;
- a critical entity such as a date, amount, name, or order number is misheard;
- the voice stack adds enough latency that users repeat themselves, become frustrated, or abandon the call.

Existing voice observability products are good at exposing raw telemetry. They may show STT latency, LLM latency, TTS latency, interruptions, talk-over, and call replay.

The Voker opportunity explored in this prototype is different:

> **Do these technical voice issues actually matter to resolution? If they do, how much?**

That turns raw voice telemetry into product analytics.

---

## Problem Statement

A team operating a production voice agent may know:

- p90 end-to-end latency is 2.8 seconds;
- average interruptions are 3.1 per call;
- STT finalization is occasionally above 1.2 seconds;
- some calls contain long dead-air periods.

But these values alone do not answer:

- Which issue is actually harming resolution?
- Which intents are most affected?
- Are user corrections increasing when STT finalization becomes slower?
- Do interrupted conversations fail more frequently?
- Which failed calls provide evidence of the pattern?

Voker Voice Impact connects the technical voice signals to business and product outcomes.

---

## Project Goal

Build a short, high-impact product prototype that demonstrates how Voker could extend Agent Analytics to voice agents.

The prototype should allow a user to move from:

```text
"This intent has poor resolution"
```

to:

```text
"Calls with more than 3 interruptions resolve 44 percentage points less often,
and 37 failed sessions show the same pattern."
```

The project should feel like a real Voker product feature rather than a generic voice monitoring dashboard.

---

## Core Product Thesis

Traditional voice observability answers:

> **What happened technically during the call?**

Voker already answers:

> **Did the user accomplish what they wanted?**

Voker Voice Impact combines both and answers:

> **Which technical voice behaviors are associated with the outcome?**

The complete conceptual flow is:

```text
Voice Agent
    |
    +--> Voice Telemetry
    |      - STT finalization
    |      - end-to-end latency
    |      - interruptions
    |      - dead air
    |      - talk-over
    |
    +--> Voker Analytics
           - intent
           - resolution
           - correction
           - escalation
           - session outcome

              |
              v
       Voice Impact Engine
              |
              v
    Correlations + Evidence
              |
              v
       Product Insight
```

---

# Demo Overview

## Demo Story

The demo uses a synthetic **Appointment Scheduling Voice Agent**.

The agent supports intents such as:

- book appointment;
- reschedule appointment;
- cancel appointment;
- check appointment details;
- ask opening hours.

The prototype is populated with realistic synthetic call data where most calls succeed, but some intents experience voice-specific friction.

The primary problematic intent is:

> **Reschedule Appointment**

Example synthetic metrics:

```text
Total calls:            1,124
Resolution rate:        54%
User correction rate:   31%
P90 latency:             2.6s
Average interruptions:   3.1
```

The system then compares successful and failed calls and discovers:

```text
Calls with 0–1 interruption:
Resolution: 86%

Calls with 3+ interruptions:
Resolution: 42%

Impact:
-44 percentage points
```

A second signal might show:

```text
STT finalization < 500 ms
Resolution: 88%

STT finalization > 1.2 s
Resolution: 51%
```

The product then surfaces a clear insight:

> **High interruption rate is the strongest voice issue associated with failed reschedule requests.**

The user can drill into affected calls and inspect real evidence.

---

# Demo Flow

## Step 1 — Voice Impact Overview

The first screen gives an executive overview.

It shows:

- total calls;
- resolution rate;
- correction rate;
- escalation rate;
- p90 end-to-end latency;
- top intents by resolution rate;
- top voice issues by impact;
- resolution comparison between normal and problematic calls.

Example insight banner:

> **3 voice issues are significantly impacting resolution.**

The purpose of this screen is to immediately communicate that the system is not merely collecting telemetry — it is connecting telemetry to outcomes.

---

## Step 2 — Intent Detail

The user clicks **Reschedule Appointment**.

The intent-level screen shows:

- call volume;
- resolution rate;
- user correction rate;
- p90 latency;
- average interruptions;
- successful vs. failed-call comparisons;
- scatter plot or grouped visualization showing interruption rate vs. resolution;
- top contributing voice issues;
- example calls.

The key insight should be visually prominent:

> **Calls with more than 3 interruptions are 44 percentage points less likely to resolve.**

This is the main product wow factor.

---

## Step 3 — Conversation Playback / Evidence

The user opens one failed call.

Example conversation:

```text
User:
"I need to move my appointment to Tuesday..."

Agent interrupts.

Agent:
"Sure, I'll move it to Thursday."

User:
"No, Tuesday."
```

The call detail page shows:

- audio playback;
- transcript;
- timeline;
- interruption events;
- dead-air events;
- STT finalization timing;
- user corrections;
- session outcome.

A root-cause panel summarizes the evidence:

```text
Likely contributing factors

- Agent interrupted before the user completed the utterance
- STT finalization was 1.8s
- User corrected the agent twice
- Same pattern appears in 37 failed sessions
```

The purpose of this screen is to prove that the aggregate insight is backed by actual calls.

---

## Optional Step 4 — STT Provider Benchmark

This is an optional extension, not required for the first MVP.

For failed calls that appear to have transcription-related problems, the system can replay the same audio through multiple STT providers.

Example:

```text
Provider       WER     Entity Accuracy    Finalization p90
Deepgram       13.2%       82%                840 ms
AssemblyAI      8.9%       94%                620 ms
Google          7.8%       96%               1050 ms
```

The system can recommend the best tradeoff for this specific traffic.

This screen should only be added if the core Voice Impact flow is already polished.

---

# Wow Factor

The wow factor is **not** that the system can display latency, interruptions, or dead air.

Existing voice observability products already do that.

The wow factor is that the prototype converts raw telemetry into product-impact insights.

Instead of saying:

```text
P90 latency = 2.8s
Interruptions = 3.4 per call
```

it says:

```text
Calls with >3 interruptions
Resolution: 42%

Calls with <1 interruption
Resolution: 86%

Impact: -44 percentage points
```

That changes the conversation from:

> **"Our voice latency looks high."**

into:

> **"This voice issue is associated with a measurable drop in user success."**

---

# Feature List

## MVP Features

### 1. Voice Impact Dashboard

Purpose: provide an overview of voice quality and its relationship to agent outcomes.

Includes:

- total voice sessions;
- resolution rate;
- user correction rate;
- escalation rate;
- p90 end-to-end latency;
- top intents by resolution;
- top voice issues by impact;
- normal vs. problematic-call resolution comparison.

---

### 2. Intent-Level Voice Analysis

Purpose: explain why a specific intent is performing poorly.

Includes:

- intent call volume;
- intent resolution rate;
- intent correction rate;
- average/p90 voice metrics;
- successful vs. failed call comparison;
- voice-factor impact table;
- correlation visualization;
- key insight generation.

---

### 3. Interruption Impact Analysis

Purpose: determine whether frequent interruptions are associated with lower resolution.

Metrics:

- interruptions per call;
- resolution for low-interruption sessions;
- resolution for high-interruption sessions;
- affected session count;
- impact in percentage points.

---

### 4. STT Finalization Impact

Purpose: measure how slow speech finalization affects the conversation.

Metrics:

- STT finalization latency;
- p50 and p90 finalization;
- user correction rate;
- intent resolution rate;
- comparison between fast and slow finalization cohorts.

---

### 5. Dead-Air Analysis

Purpose: identify whether long silence periods are associated with failure or abandonment.

Metrics:

- longest dead-air period;
- total dead-air duration;
- resolution rate by dead-air cohort;
- call abandonment association.

---

### 6. Talk-Over Detection

Purpose: detect moments where both sides speak at the same time.

Includes:

- talk-over event count;
- talk-over duration;
- comparison against resolution;
- example affected calls.

---

### 7. Example Calls / Evidence

Purpose: allow users to validate aggregate insights against actual conversations.

Includes:

- resolved / failed badge;
- call duration;
- interruption count;
- STT finalization latency;
- correction count;
- short transcript summary;
- link to call playback.

---

### 8. Conversation Playback

Purpose: provide evidence for the detected pattern.

Includes:

- audio player;
- transcript;
- user/agent speaker distinction;
- interruption markers;
- dead-air markers;
- timeline;
- voice metrics;
- session outcome;
- root-cause summary.

---

### 9. Root-Cause Summary

Purpose: transform raw call metrics into a concise explanation.

Example:

```text
Likely contributing factors:

1. Agent interrupted user before utterance completion.
2. STT finalization was significantly above baseline.
3. User corrected the agent twice.
4. Similar pattern detected in 37 failed calls.
```

The wording should remain evidence-based and use phrases such as:

- "associated with";
- "likely contributing factor";
- "strongest observed signal";

rather than claiming unproven causation.

---

# Optional / Phase 2 Features

## STT Provider Benchmark

Replay selected failed-call audio against alternative STT providers and compare:

- WER where reference transcripts exist;
- critical entity accuracy;
- finalization latency;
- p50 / p90 latency;
- recovered intent accuracy.

---

## Critical Entity Accuracy

Track important words separately from overall transcription accuracy.

Examples:

- dates;
- appointment times;
- names;
- phone numbers;
- addresses;
- order IDs;
- currency amounts.

This is useful because a transcript can have low overall WER while still mishearing the single word that determines the business action.

---

## Voice Friction Score

A composite metric based on:

- interruptions;
- dead air;
- talk-over;
- finalization latency;
- repeated user corrections.

This score could later be correlated with resolution, escalation, or abandonment.

It is not required for MVP because the initial demo should prioritize transparent, understandable metrics over a black-box score.

---

## MCP Integration

Expose voice analytics through MCP so an engineer can query the system from Cursor, Claude Code, or another compatible tool.

Example questions:

```text
Why is reschedule appointment resolution low?

Which voice issue affects resolution the most?

Show failed sessions with high interruption rate.

Which agent version has the highest p90 latency?
```

This is valuable as a technical extension but should not replace the visual product demo.

---

# Data Model — High Level

Each call should contain enough data to connect telemetry with outcome.

Example:

```ts
interface VoiceSession {
  id: string;
  agentId: string;
  agentVersion: string;
  intent: string;
  outcome: 'resolved' | 'failed' | 'escalated' | 'abandoned';

  durationMs: number;

  latency: {
    endToEndMs: number;
    sttFinalizationMs: number;
    llmTtftMs?: number;
    ttsFirstAudioMs?: number;
  };

  voice: {
    interruptionCount: number;
    talkOverCount: number;
    deadAirMs: number;
    correctionCount: number;
  };

  transcript: TranscriptTurn[];
  events: VoiceEvent[];
}
```

---

# Recommended MVP Scope

For the first founder demo, implement only:

1. Voice Impact Overview
2. Intent Detail
3. Interruption analysis
4. STT finalization analysis
5. Dead-air analysis
6. Example calls
7. Conversation playback
8. Evidence-based insight panel

Do not initially build:

- telephony infrastructure;
- SIP;
- custom STT/TTS engines;
- real-time production ingestion at scale;
- churn prediction;
- emotion recognition;
- dozens of voice metrics;
- complex statistical causal inference;
- full STT benchmarking unless time remains.

The prototype should optimize for clarity and product value rather than platform completeness.

---

# Demo Data Strategy

Use synthetic but realistic data.

Example:

```text
Total calls: 1,500

Track order             350
Book appointment        320
Reschedule appointment  280
Cancel appointment      220
Other                    330
```

Most sessions should succeed.

Example overall distribution:

```text
Resolved     76%
Failed       14%
Escalated     6%
Abandoned     4%
```

The problematic intent should have enough examples to make the relationship visually obvious without making the data look fake.

---

# Design Direction

The UI should visually feel compatible with the Voker product while remaining clearly a prototype.

Primary colors:

```text
Primary:       #004D43
Primary Light: #DDEAED
```

The UI should use:

- light backgrounds;
- dark teal navigation;
- white cards;
- subtle borders;
- green for successful/resolved states;
- red for failed/high-impact states;
- simple charts;
- concise insight cards;
- minimal visual clutter.

The full design package is maintained separately in the project design ZIP.

---

# Success Criteria

The prototype is successful if a founder can understand the value within approximately 30 seconds.

After watching the full demo, the viewer should understand:

1. Voker already knows which intents succeed or fail.
2. Voice agents introduce technical conversation-quality signals.
3. The prototype connects those signals to Voker outcomes.
4. It identifies the voice issues most associated with poor resolution.
5. The aggregate insight can be verified through real call examples.
6. The concept feels like a plausible extension of Voker's existing analytics product.

---

# One-Sentence Product Pitch

> **Voker Voice Impact connects voice-agent telemetry such as interruptions, dead air, and speech finalization latency with Voker's intent and resolution analytics, showing teams which voice-quality problems are actually associated with failed user outcomes.**

---

# Short Demo Pitch

> Voice observability tools can tell you that your agent had three interruptions or 2.8 seconds of latency. Voker already tells you whether the user succeeded. Voice Impact connects the two — so instead of seeing raw metrics, you can see that calls with more than three interruptions resolve 44 percentage points less often, drill into the affected intent, and inspect the exact conversations behind the pattern.
