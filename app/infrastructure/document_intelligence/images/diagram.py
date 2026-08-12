"""draw.io (XML) → Mermaid conversion (P2-504).

Produces a Mermaid ``flowchart`` skeleton from drawio ``mxGraphModel`` cells:
labeled non-edge cells become nodes, edge cells become connections (with their
label as an edge annotation). Unparseable or empty input yields ``""`` so
callers can fall back to the raw text.
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree

_VALID_NODE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _node_id(cell_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", cell_id)
    if not cleaned or not cleaned[0].isalpha():
        cleaned = "n_" + cleaned
    return cleaned


def _is_edge(cell: ElementTree.Element) -> bool:
    if cell.get("edge") in ("1", "true"):
        return True
    style = cell.get("style", "")
    return "edgeStyle" in style or "rounded=0" in style


def _label(cell: ElementTree.Element) -> str:
    value = cell.get("value", "") or ""
    value = value.strip()
    if not value:
        return ""
    # Strip embedded HTML so labels stay plain text in Mermaid.
    return re.sub(r"<[^>]+>", "", value).strip().replace('"', "'")


def drawio_to_mermaid(xml_content: str) -> str:
    """Convert a drawio XML string into a Mermaid flowchart skeleton.

    Returns an empty string when the input is not parseable as drawio
    ``mxGraphModel`` or yields no labeled content.
    """
    try:
        root = ElementTree.fromstring(xml_content)
    except ElementTree.ParseError:
        return ""

    cells = list(root.iter("mxCell"))
    if not cells:
        return ""

    node_labels: dict[str, str] = {}
    edges: list[tuple[str, str, str]] = []
    for cell in cells:
        cell_id = cell.get("id", "")
        if not cell_id:
            continue
        source = cell.get("source")
        target = cell.get("target")
        if _is_edge(cell) and source and target:
            edges.append((_node_id(source), _node_id(target), _label(cell)))
            continue
        label = _label(cell)
        if label:
            node_labels[_node_id(cell_id)] = label

    if not node_labels:
        return ""

    lines = ["flowchart LR"]
    for node_id, label in node_labels.items():
        if _VALID_NODE_ID.match(node_id) and node_id == label.replace(" ", "_"):
            lines.append(f"    {node_id}")
        else:
            lines.append(f'    {node_id}["{label}"]')
    for src, dst, label in edges:
        if label:
            lines.append(f'    {src} -->|"{label}"| {dst}')
        else:
            lines.append(f"    {src} --> {dst}")
    return "\n".join(lines)


class DiagramParser:
    """Parse a diagram file into its Mermaid representation."""

    supported_suffixes = (".drawio",)

    def parse(self, path: Path) -> str:
        """Return the Mermaid skeleton for ``path``, or ``""`` when unsupported."""
        if path.suffix.lower() not in self.supported_suffixes:
            return ""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return drawio_to_mermaid(content)


def get_default_diagram_parser() -> DiagramParser:
    """Return the configured diagram parser."""
    return DiagramParser()
