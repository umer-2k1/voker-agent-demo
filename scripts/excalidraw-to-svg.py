"""Render a simple SVG preview from an .excalidraw scene (rectangles, bound text, arrows).

Usage: python scripts/excalidraw-to-svg.py <in.excalidraw> <out.svg>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def esc(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def render(scene: dict) -> str:
    elements = scene["elements"]
    by_id = {e["id"]: e for e in elements}
    parts: list[str] = []
    xs: list[float] = []
    ys: list[float] = []

    def track(x: float, y: float) -> None:
        xs.append(x)
        ys.append(y)

    for e in elements:
        x, y, w, h = e["x"], e["y"], e["width"], e["height"]
        track(x, y)
        track(x + w, y + h)
        if e["type"] == "rectangle":
            dash = ' stroke-dasharray="7 7"' if e.get("strokeStyle") == "dashed" else ""
            fill = e.get("backgroundColor", "transparent")
            opacity = e.get("opacity", 100) / 100
            fill_attr = (
                "none"
                if fill in ("transparent", None)
                else f"{fill}"
            )
            fill_op = "" if fill_attr == "none" else f' fill-opacity="{opacity}"'
            parts.append(
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" '
                f'fill="{fill_attr}"{fill_op} stroke="{e["strokeColor"]}" '
                f'stroke-width="{e.get("strokeWidth", 2)}"{dash} />'
            )
        elif e["type"] == "arrow":
            pts = [(x + px, y + py) for px, py in e["points"]]
            dash = ' stroke-dasharray="6 6"' if e.get("strokeStyle") == "dashed" else ""
            poly = " ".join(f"{px},{py}" for px, py in pts)
            parts.append(
                f'<polyline points="{poly}" fill="none" stroke="{e["strokeColor"]}" '
                f'stroke-width="2"{dash} marker-end="url(#arrow)" />'
            )

    # Text on top.
    for e in elements:
        if e["type"] != "text":
            continue
        fs = e.get("fontSize", 16)
        color = e.get("strokeColor", "#1e1e1e")
        lines = e["text"].split("\n")
        container = by_id.get(e.get("containerId")) if e.get("containerId") else None
        if container is not None:
            cx = container["x"] + container["width"] / 2
            cy = container["y"] + container["height"] / 2
            anchor = "middle"
        else:
            cx = e["x"]
            cy = e["y"] + fs * 0.8
            anchor = "start"
        lh = fs * 1.25
        start = cy - (len(lines) - 1) * lh / 2
        family = "Sora, Inter, Helvetica, Arial, sans-serif" if fs >= 18 else "Inter, Helvetica, Arial, sans-serif"
        for index, line in enumerate(lines):
            ty = start + index * lh
            weight = "600" if fs >= 18 else "500"
            parts.append(
                f'<text x="{cx}" y="{ty}" font-family="{family}" font-size="{fs}" '
                f'font-weight="{weight}" fill="{color}" text-anchor="{anchor}" '
                f'dominant-baseline="middle">{esc(line)}</text>'
            )
            track(cx - len(line) * fs * 0.3, ty - fs)
            track(cx + len(line) * fs * 0.3, ty + fs)

    pad = 40
    minx, miny = min(xs) - pad, min(ys) - pad
    maxx, maxy = max(xs) + pad, max(ys) + pad
    width, height = maxx - minx, maxy - miny
    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx} {miny} {width} {height}" '
        f'width="{width}" height="{height}">'
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#1e1e1e" /></marker></defs>'
        '<rect x="{minx}" y="{miny}" width="{width}" height="{height}" fill="#ffffff" />'
    ).format(minx=minx, miny=miny, width=width, height=height)
    return header + "".join(parts) + "</svg>"


def main() -> None:
    source, target = sys.argv[1], sys.argv[2]
    scene = json.loads(Path(source).read_text())
    Path(target).write_text(render(scene))
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
