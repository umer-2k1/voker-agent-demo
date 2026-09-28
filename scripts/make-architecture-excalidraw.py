"""Generate an Excalidraw architecture diagram for the Voker observability system.

Run:  python scripts/make-architecture-excalidraw.py
Out:  docs/diagrams/voker-architecture.excalidraw
"""

from __future__ import annotations

import json
import random
from pathlib import Path

random.seed(17)
ELEM: list[dict] = []

FONT = 2  # Helvetica
INK = "#1e1e1e"


def _seed() -> int:
    return random.randint(1, 2**31 - 1)


def _base(element_id: str, kind: str, **extra) -> dict:
    element = {
        "id": element_id,
        "type": kind,
        "angle": 0,
        "strokeColor": INK,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": {"type": 3},
        "seed": _seed(),
        "version": 1,
        "versionNonce": _seed(),
        "isDeleted": False,
        "boundElements": [],
        "updated": 1_700_000_000_000,
        "link": None,
        "locked": False,
    }
    element.update(extra)
    return element


def zone(zone_id: str, x: int, y: int, w: int, h: int, label: str, color: str) -> None:
    """A dashed grouping frame with a title label."""
    ELEM.append(
        _base(
            zone_id,
            "rectangle",
            x=x,
            y=y,
            width=w,
            height=h,
            strokeColor=color,
            backgroundColor=color,
            fillStyle="solid",
            opacity=28,
            strokeStyle="dashed",
            strokeWidth=1,
            roundness={"type": 3},
        )
    )
    ELEM.append(
        _base(
            f"{zone_id}-label",
            "text",
            x=x + 18,
            y=y + 12,
            width=len(label) * 10.5,
            height=26,
            strokeColor=INK,
            fontSize=20,
            fontFamily=FONT,
            text=label,
            originalText=label,
            textAlign="left",
            verticalAlign="top",
            containerId=None,
            lineHeight=1.25,
            baseline=16,
        )
    )


def box(
    box_id: str,
    x: int,
    y: int,
    w: int,
    h: int,
    text: str,
    fill: str,
    font_size: int = 15,
) -> str:
    """A rounded component box with centered bound text."""
    text_id = f"{box_id}-text"
    ELEM.append(
        _base(
            box_id,
            "rectangle",
            x=x,
            y=y,
            width=w,
            height=h,
            backgroundColor=fill,
            fillStyle="solid",
            roundness={"type": 3},
            boundElements=[{"type": "text", "id": text_id}],
        )
    )
    lines = text.split("\n")
    ELEM.append(
        _base(
            text_id,
            "text",
            x=x + 10,
            y=y + h / 2 - (len(lines) * font_size * 1.25) / 2,
            width=w - 20,
            height=len(lines) * font_size * 1.3,
            fontSize=font_size,
            fontFamily=FONT,
            text=text,
            originalText=text,
            textAlign="center",
            verticalAlign="middle",
            containerId=box_id,
            lineHeight=1.25,
            baseline=font_size * 0.8,
        )
    )
    return box_id


def arrow(
    arrow_id: str,
    points: list[tuple[float, float]],
    *,
    label: str | None = None,
    dashed: bool = False,
    color: str = INK,
) -> None:
    """An arrow through absolute waypoints; optional centered label."""
    (x0, y0) = points[0]
    relative = [[px - x0, py - y0] for px, py in points]
    bound = []
    element = _base(
        arrow_id,
        "arrow",
        x=x0,
        y=y0,
        width=abs(relative[-1][0]),
        height=abs(relative[-1][1]),
        strokeColor=color,
        strokeStyle="dashed" if dashed else "solid",
        roundness={"type": 2},
        points=relative,
        lastCommittedPoint=None,
        startBinding=None,
        endBinding=None,
        startArrowhead=None,
        endArrowhead="arrow",
        elbowed=False,
    )
    if label:
        text_id = f"{arrow_id}-label"
        mid = points[len(points) // 2]
        bound.append({"type": "text", "id": text_id})
        ELEM.append(
            _base(
                text_id,
                "text",
                x=mid[0] - len(label) * 4,
                y=mid[1] - 24,
                width=len(label) * 8,
                height=20,
                fontSize=13,
                fontFamily=FONT,
                text=label,
                originalText=label,
                textAlign="center",
                verticalAlign="middle",
                containerId=arrow_id,
                lineHeight=1.25,
                baseline=12,
                strokeColor="#495057",
            )
        )
    element["boundElements"] = bound
    ELEM.append(element)


# ---------------------------------------------------------------------------
# 1 · Live voice call (instrumented)
# ---------------------------------------------------------------------------
zone("z-call", 60, 70, 1660, 210, "1 · Live voice call (instrumented)", "#e7f5f1")

box("n-user", 110, 150, 150, 84, "User\n(caller)", "#dbeafe")
box("n-agent", 340, 150, 210, 84, "Voice Agent\n(LiveKit session)", "#e7f5f1")
box("n-stt", 630, 150, 160, 84, "STT\n(Deepgram)", "#e7f5f1")
box("n-llm", 870, 150, 190, 84, "LLM\n(DeepSeek)", "#e7f5f1")
box("n-tools", 1140, 150, 190, 84, "Tools\n(function calls)", "#e7f5f1")
box("n-tts", 1410, 150, 150, 84, "TTS\n(audio)", "#e7f5f1")

arrow("a-user-agent", [(260, 192), (340, 192)])
arrow("a-agent-stt", [(550, 192), (630, 192)], label="speech")
arrow("a-stt-llm", [(790, 192), (870, 192)], label="transcript")
arrow("a-llm-tools", [(1060, 192), (1140, 192)], label="tool calls")
arrow("a-tools-tts", [(1330, 192), (1410, 192)])
arrow(
    "a-tts-user",
    [(1485, 150), (1485, 118), (185, 118), (185, 150)],
    label="audio response",
    color="#0f766e",
)

# ---------------------------------------------------------------------------
# 2 · Voker platform
# ---------------------------------------------------------------------------
zone("z-platform", 60, 320, 1660, 620, "2 · Voker platform", "#eef2ff")

box(
    "n-sdk",
    710,
    370,
    360,
    74,
    "Voker SDK · observe()\ncanonical events (turns, spans, tool calls)",
    "#e0e7ff",
)
arrow("a-agent-sdk", [(445, 234), (445, 320), (890, 320), (890, 370)], label="emits", dashed=True)

box(
    "n-ingest",
    180,
    500,
    360,
    84,
    "Event ingestion\nPOST /v1/events/batch\n(durable inbox)",
    "#e0f2fe",
)
arrow("a-sdk-ingest", [(770, 444), (770, 470), (360, 470), (360, 500)], label="export")

box(
    "n-db",
    720,
    480,
    480,
    104,
    "PostgreSQL\nsessions · events · turns · spans · findings · analysis runs",
    "#fef3c7",
)
arrow("a-ingest-db", [(540, 542), (720, 542)], label="project + commit")

box(
    "n-det",
    180,
    660,
    330,
    84,
    "Deterministic analysis\nrules v2 (errors, latency, dead air)",
    "#dcfce7",
)
box(
    "n-sem",
    560,
    660,
    360,
    84,
    "Async LLM evaluation\nsemantic-v3 · worker · evidence-validated",
    "#dcfce7",
)
arrow("a-db-det", [(800, 584), (800, 622), (345, 622), (345, 660)], label="reads")
arrow("a-db-sem", [(900, 584), (900, 660)], label="queues")

box(
    "n-find",
    1010,
    660,
    360,
    84,
    "Findings + evidence\nimmutable analysis runs\n(certainty · severity · next step)",
    "#f3e8ff",
)
arrow("a-det-find", [(510, 702), (1010, 702)], label="findings")
arrow("a-sem-find", [(920, 702), (1010, 702)])

box(
    "n-api",
    180,
    810,
    230,
    74,
    "API (FastAPI)\nauth · analytics",
    "#e2e8f0",
)
box(
    "n-dash",
    470,
    810,
    400,
    74,
    "Dashboard (React)\ncharts · traces · tool calls · findings",
    "#e2e8f0",
)
box(
    "n-mcp",
    1010,
    810,
    330,
    74,
    "MCP clients\n(Codex · Claude · Cursor) — read-only",
    "#e2e8f0",
)
arrow("a-db-api", [(760, 584), (760, 622), (295, 622), (295, 810)], label="queries")
arrow("a-api-dash", [(410, 847), (470, 847)])
arrow("a-db-mcp", [(1120, 584), (1120, 810)], label="read-only", dashed=True)

scene = {
    "type": "excalidraw",
    "version": 2,
    "source": "voker-agent-demo/scripts/make-architecture-excalidraw.py",
    "elements": ELEM,
    "appState": {
        "gridSize": None,
        "viewBackgroundColor": "#ffffff",
    },
    "files": {},
}

out = Path("docs/diagrams/voker-architecture.excalidraw")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(scene, indent=2))
print(f"wrote {out} ({len(ELEM)} elements)")
