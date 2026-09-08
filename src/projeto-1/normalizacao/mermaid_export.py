"""Renderização do grafo em Markdown com diagrama Mermaid."""

from html import escape

from graph import GraphBuilder


_NODE_STYLES = {
    "Patient": ("#fef3c7", "#d97706"),
    "History": ("#e0e7ff", "#4338ca"),
    "Symptom": ("#fee2e2", "#b91c1c"),
    "Finding": ("#fce7f3", "#be185d"),
    "Exam": ("#dbeafe", "#1d4ed8"),
    "ExamResult": ("#cffafe", "#0e7490"),
    "Diagnosis": ("#dcfce7", "#15803d"),
    "Treatment": ("#fef9c3", "#a16207"),
    "Medication": ("#ffedd5", "#c2410c"),
    "AnatomicalSite": ("#ede9fe", "#6d28d9"),
    "Outcome": ("#f3e8ff", "#7e22ce"),
    "Concept": ("#f3f4f6", "#4b5563"),
}


def _node_text(node_type: str, label: str, attributes: str) -> str:
    parts = [f"<b>{escape(node_type)}</b>", escape(label)]
    if attributes:
        parts.append(f"<small>{escape(attributes)}</small>")
    return "<br/>".join(parts)


def render_mermaid_markdown(graph: GraphBuilder) -> str:
    """Produz Markdown contendo o resumo e o fluxograma Mermaid."""
    lines = [
        f"# Grafo do caso {graph.case_id}",
        "",
        f"- Nós: {len(graph.nodes)}",
        f"- Arestas: {len(graph.edges)}",
        "",
        "```mermaid",
        "flowchart LR",
    ]

    for node_type, (fill, stroke) in _NODE_STYLES.items():
        lines.append(
            f"  classDef {node_type} fill:{fill},stroke:{stroke},color:#111827"
        )

    lines.append("")
    for node in graph.nodes:
        attributes = node.to_row()["attributes"]
        label = _node_text(node.type, node.label, attributes)
        lines.append(f'  {node.node_id}["{label}"]:::{node.type}')

    lines.append("")
    for edge in graph.edges:
        relation = escape(edge.relation)
        lines.append(
            f"  {edge.source_id} -->|{relation}| {edge.target_id}"
        )

    lines.extend(["```", ""])
    return "\n".join(lines)
