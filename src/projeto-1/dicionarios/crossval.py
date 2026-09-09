"""Validação cruzada (processo 7): conceitos casados no caso vs. mesh_terms do artigo.

Não é gabarito: mesh_terms descreve o artigo (que pode ter mais de um
caso), curado por humano sobre o texto completo do artigo — não sobre o
case_text isolado. É só um sinal independente de que o casamento está
encontrando conceitos plausíveis, não uma métrica de precisão/revocação
no sentido estrito.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.graph import GraphBuilder
from metadata_reader import base_term, parse_bracket_list, read_metadata_row


@dataclass(frozen=True)
class CrossValidationResult:
    case_id: str
    article_id: str
    case_concept_terms: frozenset[str]
    article_mesh_terms: frozenset[str]
    overlap_terms: frozenset[str]

    @property
    def overlap_ratio_of_article_terms(self) -> float | None:
        if not self.article_mesh_terms:
            return None
        return len(self.overlap_terms) / len(self.article_mesh_terms)


def cross_validate_case(
    graph: GraphBuilder,
    article_id: str,
    metadata_csv: str | Path,
) -> CrossValidationResult:
    concept_terms = frozenset(
        node.attributes.get("preferred_term", node.label).lower()
        for node in graph.nodes
        if node.type == "Concept"
    )

    row = read_metadata_row(metadata_csv, article_id)
    mesh_terms = parse_bracket_list(row["mesh_terms"]) if row else []
    article_terms = frozenset(base_term(t).lower() for t in mesh_terms if base_term(t))

    overlap = concept_terms & article_terms

    return CrossValidationResult(
        case_id=graph.case_id,
        article_id=article_id,
        case_concept_terms=concept_terms,
        article_mesh_terms=article_terms,
        overlap_terms=overlap,
    )
