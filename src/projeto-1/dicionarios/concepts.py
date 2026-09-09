"""Ligação de entidades extraídas a conceitos do gazetteer (Concept + SAME_AS).

É aqui que o resultado do matching (matching.py) efetivamente vira parte do
grafo — ver README.md, processo 6.
"""

from __future__ import annotations

from core.graph import GraphBuilder
from core.models import Node
from extractors.common import ExtractedEntity
from matching import link_label_to_concept


def link_entities_to_concepts(
    entities: list[ExtractedEntity],
    gazetteers: list[dict[str, list[tuple[str, str]]]],
    graph: GraphBuilder,
    concept_nodes: dict[str, Node],
    vocabulary: str = "MeSH",
) -> None:
    """Tenta ligar cada entidade a um Concept, tentando os gazetteers na
    ordem dada (ex.: 'diseases' primeiro, 'mental_disorders' como reserva
    para Diagnosis). concept_nodes é compartilhado entre chamadas no mesmo
    caso, para reaproveitar o mesmo nó Concept quando duas entidades
    diferentes casam com o mesmo código (ex. Symptom e History mencionando
    o mesmo conceito) — em vez de criar um Concept duplicado.
    """
    for entity in entities:
        match = None
        for gazetteer in gazetteers:
            match = link_label_to_concept(entity.node.label, gazetteer)
            if match is not None:
                break

        if match is None:
            continue

        if match.code not in concept_nodes:
            concept_nodes[match.code] = graph.add_node(
                "Concept",
                match.preferred_term,
                {
                    "vocabulary": vocabulary,
                    "code": match.code,
                    "preferred_term": match.preferred_term,
                },
            )

        graph.add_edge(
            entity.node,
            concept_nodes[match.code],
            "SAME_AS",
            {"strategy": match.strategy, "score": match.score},
        )
