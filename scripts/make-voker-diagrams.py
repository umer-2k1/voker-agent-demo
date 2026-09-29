"""Generate the editable Voker product-story Excalidraw diagrams.

Run: python3 scripts/make-voker-diagrams.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path


OUT = Path("docs/diagrams")
FONT = 2
INK = "#172033"
MUTED = "#526071"
NOW = 1_790_000_000_000


class Scene:
    def __init__(self, name: str) -> None:
        self.name = name
        self.elements: list[dict] = []
        self.n = 0

    def add(self, kind: str, **extra) -> dict:
        self.n += 1
        element = {
            "id": f"{self.name}-{self.n}",
            "type": kind,
            "angle": 0,
            "strokeColor": INK,
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 2,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "groupIds": [],
            "frameId": None,
            "seed": random.randint(1, 2**31 - 1),
            "version": 1,
            "versionNonce": random.randint(1, 2**31 - 1),
            "isDeleted": False,
            "boundElements": [],
            "updated": NOW,
            "link": None,
            "locked": False,
        }
        element.update(extra)
        self.elements.append(element)
        return element

    def text(
        self,
        x: int,
        y: int,
        value: str,
        size: int = 16,
        color: str = INK,
        *,
        align: str = "left",
        width: int | None = None,
    ) -> None:
        lines = value.split("\n")
        h = round(len(lines) * size * 1.25)
        self.add(
            "text",
            x=x,
            y=y,
            width=width or max(len(line) for line in lines) * size * 0.6,
            height=h,
            strokeColor=color,
            strokeWidth=1,
            fontSize=size,
            fontFamily=FONT,
            text=value,
            originalText=value,
            textAlign=align,
            verticalAlign="top",
            containerId=None,
            autoResize=width is None,
            lineHeight=1.25,
            baseline=round(size * 0.8),
        )

    def card(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        title: str,
        body: str,
        fill: str,
        *,
        title_color: str = INK,
        body_color: str = MUTED,
    ) -> tuple[float, float]:
        self.add(
            "rectangle",
            x=x,
            y=y,
            width=w,
            height=h,
            backgroundColor=fill,
            roundness={"type": 3},
        )
        self.text(x + 24, y + 20, title, 19, title_color, width=w - 48)
        self.text(x + 24, y + 54, body, 14, body_color, width=w - 48)
        return (x + w / 2, y + h / 2)

    def frame(self, x: int, y: int, w: int, h: int, label: str, color: str) -> None:
        self.add(
            "rectangle",
            x=x,
            y=y,
            width=w,
            height=h,
            strokeColor=color,
            backgroundColor=color,
            opacity=18,
            strokeWidth=1,
            strokeStyle="dashed",
            roundness={"type": 3},
        )
        self.text(x + 24, y + 18, label, 15, color)

    def arrow(
        self,
        points: list[tuple[int, int]],
        color: str = INK,
        *,
        dashed: bool = False,
    ) -> None:
        x0, y0 = points[0]
        relative = [[x - x0, y - y0] for x, y in points]
        self.add(
            "arrow",
            x=x0,
            y=y0,
            width=max(x for x, _ in relative) - min(x for x, _ in relative),
            height=max(y for _, y in relative) - min(y for _, y in relative),
            strokeColor=color,
            strokeWidth=2,
            strokeStyle="dashed" if dashed else "solid",
            points=relative,
            lastCommittedPoint=None,
            startBinding=None,
            endBinding=None,
            startArrowhead=None,
            endArrowhead="triangle",
            elbowed=False,
        )

    def write(self, filename: str) -> None:
        scene = {
            "type": "excalidraw",
            "version": 2,
            "source": "voker-agent-demo/scripts/make-voker-diagrams.py",
            "elements": self.elements,
            "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
            "files": {},
        }
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / filename).write_text(json.dumps(scene, indent=2) + "\n")


def master() -> None:
    s = Scene("master")
    s.text(80, 48, "Voker AI — Voice Agent Analytics", 34)
    s.text(82, 98, "End-to-end observability that turns every voice conversation into evidence for faster agent improvement.", 17, MUTED)
    s.card(
        80, 146, 1880, 96,
        "The Voker advantage",
        "One trace connects customer intent, conversation outcome, agent behavior, and the underlying technical evidence.",
        "#e0f2fe", title_color="#075985", body_color="#0c4a6e",
    )

    s.frame(80, 286, 1880, 288, "1 · What Voker captures", "#0f766e")
    source_cards = [
        (112, "Transcripts & turns", "Who said what —\nand when", "#dcfce7"),
        (420, "Tool calls & results", "Tool execution\nand responses", "#ede9fe"),
        (728, "LLM calls", "Model inputs, outputs,\nand failures", "#ede9fe"),
        (1036, "Latency", "STT · LLM · TTS\nand response gaps", "#fef3c7"),
        (1344, "Voice behavior", "Interruptions\nand handoffs", "#fee2e2"),
        (1652, "Failures & usage", "Errors · timeouts\ntokens · cost", "#fee2e2"),
    ]
    for x, title, body, fill in source_cards:
        s.card(x, 346, 280, 110, title, body, fill)
    s.text(112, 500, "SDK / platform support: LiveKit · Vapi · Retell · ElevenLabs · Deepgram · custom voice stacks", 16, "#0f766e")

    s.frame(80, 620, 1880, 340, "2 · Voker system analysis", "#7c3aed")
    analysis_cards = [
        (112, "Trace + metrics", "Sessions, spans,\ntranscripts, latency, cost"),
        (552, "Deterministic analysis", "Errors · timeouts · slow stages\ntalk-over · dead air · handoffs"),
        (992, "Semantic analysis", "Intent · resolution · corrections\noutcome · confidence"),
        (1432, "Evidence-backed findings", "Severity, certainty,\nand exact trace evidence"),
    ]
    for x, title, body in analysis_cards:
        s.card(x, 698, 400, 120, title, body, "#f3e8ff", title_color="#5b21b6")
    for x in (512, 952, 1392):
        s.arrow([(x, 758), (x + 40, 758)], "#7c3aed")
    s.card(112, 852, 1816, 92, "Core analytics output", "Intent identification · resolution & outcomes · correction patterns · voice quality · agent and version performance", "#ede9fe", title_color="#5b21b6")

    s.frame(80, 1006, 1880, 196, "3 · Voker architecture", "#0f766e")
    architecture_cards = [
        (112, "Voice Agent", "live call"),
        (374, "SDK / adapters", "platform events"),
        (636, "Event Ingestion", "durable capture"),
        (898, "PostgreSQL", "canonical data"),
        (1160, "Trace + Metrics", "sessions · spans"),
        (1422, "Semantic Analysis", "findings + evidence"),
        (1684, "Analytics Dashboard", "insights + trends"),
    ]
    for x, title, body in architecture_cards:
        s.card(x, 1070, 224, 84, title, body, "#e0f2fe", title_color="#0f766e")
    for x in (336, 598, 860, 1122, 1384, 1646):
        s.arrow([(x, 1112), (x + 38, 1112)], "#0f766e")

    s.frame(80, 1250, 1120, 300, "4 · Make teams faster", "#2563eb")
    s.card(112, 1314, 496, 158, "Agent Analytics Dashboard", "Resolution, error, latency,\nvoice-quality, and cost trends.", "#dbeafe", title_color="#1d4ed8")
    s.card(672, 1314, 496, 158, "MCP for development", "Read-only sessions, traces, transcripts,\nfindings, errors, and comparisons in Codex, Claude, or Cursor.", "#e0e7ff", title_color="#3730a3")
    s.arrow([(608, 1393), (672, 1393)], "#2563eb")

    s.frame(1248, 1250, 712, 300, "Market context", "#d97706")
    s.card(1280, 1314, 300, 158, "Adjacent", "Lemma\nuselemma.ai", "#fff7ed", title_color="#9a3412")
    s.card(1628, 1314, 300, 158, "Adjacent", "Coval\ncoval.ai", "#fff7ed", title_color="#9a3412")
    s.text(1280, 1490, "Opportunity: voice-agent observability is moving quickly.\nVoker can expand voice capabilities and ship faster.", 15, "#9a3412")
    s.write("voker-master.excalidraw")


def architecture() -> None:
    s = Scene("architecture")
    s.text(80, 50, "Voker Voice — Architecture", 34)
    s.text(82, 100, "From live voice interaction to evidence-backed agent analytics.", 17, MUTED)

    s.frame(80, 156, 1880, 230, "Live voice agent", "#0f766e")
    nodes = [
        (112, "Caller", "speech", "#dcfce7"),
        (432, "Voice agent", "orchestration", "#dcfce7"),
        (752, "STT", "transcript", "#e0f2fe"),
        (1072, "LLM + tools", "reasoning · actions", "#ede9fe"),
        (1392, "TTS", "audio response", "#fef3c7"),
        (1712, "Caller", "response", "#dcfce7"),
    ]
    centres = []
    for x, title, body, fill in nodes:
        centres.append(s.card(x, 226, 200, 94, title, body, fill))
    for (_, cy), (nx, ny) in zip(centres[:-1], centres[1:]):
        s.arrow([(centres[centres.index((_, cy))][0] + 100, cy), (nx - 100, ny)], "#0f766e")

    s.frame(80, 444, 1880, 218, "Voker capture and durable storage", "#2563eb")
    sdk = s.card(112, 510, 360, 96, "SDK / adapters", "LiveKit · Vapi · Retell · ElevenLabs\nDeepgram · custom voice stacks", "#dbeafe", title_color="#1d4ed8")
    ingest = s.card(632, 510, 360, 96, "Event ingestion", "Turns · calls · spans · latency\ninterruptions · errors · usage", "#e0f2fe", title_color="#0369a1")
    store = s.card(1152, 510, 360, 96, "PostgreSQL", "Canonical sessions, traces,\ntranscripts, costs, and outcomes", "#fef3c7", title_color="#92400e")
    s.card(1672, 510, 256, 96, "Data controls", "Redaction\n& project scope", "#f1f5f9")
    for source_x in (532, 852, 1172, 1492):
        s.arrow([(source_x, 320), (source_x, 482), (292, 482), (292, 510)], "#94a3b8", dashed=True)
    s.arrow([(472, 558), (632, 558)], "#2563eb")
    s.arrow([(992, 558), (1152, 558)], "#2563eb")

    s.frame(80, 720, 1880, 324, "Voker analysis and delivery", "#7c3aed")
    det = s.card(112, 806, 350, 112, "Deterministic analysis", "Errors · timeouts · slow stages\ndead air · talk-over · handoffs", "#f3e8ff", title_color="#5b21b6")
    sem = s.card(542, 806, 350, 112, "Semantic analysis", "Intent · resolution · corrections\nconfidence · evidence-backed findings", "#f3e8ff", title_color="#5b21b6")
    dashboard = s.card(972, 806, 350, 112, "Analytics dashboard", "Outcomes, cohorts, cost, latency\nand agent/version comparison", "#e0e7ff", title_color="#3730a3")
    mcp = s.card(1402, 806, 526, 112, "Read-only MCP", "Codex · Claude · Cursor inspect sessions, traces, transcripts, findings, and errors.", "#ecfeff", title_color="#155e75")
    s.arrow([(1332, 606), (1332, 758), (287, 758), (287, 806)], "#7c3aed")
    s.arrow([(1332, 606), (1332, 758), (717, 758), (717, 806)], "#7c3aed")
    s.arrow([(462, 862), (542, 862)], "#7c3aed")
    s.arrow([(892, 862), (972, 862)], "#7c3aed")
    s.arrow([(1322, 862), (1402, 862)], "#7c3aed")
    s.write("voker-architecture.excalidraw")


def analytics() -> None:
    s = Scene("analytics")
    s.text(80, 50, "Voker Core Analytics", 34)
    s.text(82, 100, "Understand demand, prove resolution, and find the exact reason performance breaks.", 17, MUTED)
    s.frame(80, 156, 540, 706, "Voice telemetry", "#0f766e")
    telemetry = [
        (112, 224, "Conversation", "Transcript and\nconversation turns", "#dcfce7"),
        (112, 352, "Execution", "Tool calls, results,\nand LLM calls", "#ede9fe"),
        (112, 480, "Speed & cost", "STT / LLM / TTS latency\ntokens and cost", "#fef3c7"),
        (112, 608, "Voice behavior", "Interruptions, talk-over,\ndead air, handoffs, errors", "#fee2e2"),
    ]
    for x, y, title, body, fill in telemetry:
        s.card(x, y, 476, 96, title, body, fill)

    s.frame(696, 156, 620, 706, "Voker analysis", "#7c3aed")
    core = [
        (728, 224, "Identify intent", "What the customer wanted"),
        (728, 370, "Classify outcome", "Resolved, escalated, abandoned, failed"),
        (728, 516, "Find correction patterns", "Where conversations or execution failed"),
        (728, 662, "Link the evidence", "Trace, transcript, events, and severity"),
    ]
    for x, y, title, body in core:
        s.card(x, y, 556, 106, title, body, "#f3e8ff", title_color="#5b21b6")
    for y in (272, 400, 528, 656):
        s.arrow([(588, y), (728, y)], "#7c3aed")

    s.frame(1392, 156, 568, 706, "Operational decisions", "#2563eb")
    decisions = [
        (1424, 224, "Improve releases", "Compare resolution, errors,\nand latency across agent versions"),
        (1424, 398, "Protect experience", "Prioritize quality failures:\ntalk-over, dead air, escalation"),
        (1424, 572, "Operate efficiently", "Track cost, reliability, and\nperformance by agent or cohort"),
    ]
    for x, y, title, body in decisions:
        s.card(x, y, 504, 126, title, body, "#dbeafe", title_color="#1d4ed8")
    s.arrow([(1284, 277), (1424, 277)], "#2563eb")
    s.arrow([(1284, 451), (1424, 451)], "#2563eb")
    s.arrow([(1284, 625), (1424, 625)], "#2563eb")
    s.card(80, 920, 1880, 108, "Voker takeaway", "Voker shows what customers want, whether the agent resolved it, and the evidence behind every improvement decision.", "#e0f2fe", title_color="#075985", body_color="#0c4a6e")
    s.write("voker-core-analytics.excalidraw")


if __name__ == "__main__":
    random.seed(93)
    master()
    architecture()
    analytics()
