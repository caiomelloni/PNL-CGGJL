"""Construção incremental das tabelas de nós e arestas."""

import re
from collections import defaultdict
from typing import Any

from case_normalizer import CaseNormalizer
from models import Edge, NODE_PREFIXES, Node


_CASE_ID_PATTERN = re.compile(r"PMC\d+_\d{2}")


class GraphBuilder:
    """Constrói o grafo de um único caso clínico."""

    def __init__(self, case_id: str, case_text: str) -> None:
        if _CASE_ID_PATTERN.fullmatch(case_id) is None:
            raise ValueError(f"invalid case_id: {case_id!r}")

        self.case_id = case_id
        self.case_text = case_text
        self.normalizer = CaseNormalizer(case_text)

        self.nodes: list[Node] = []
        self.edges: list[Edge] = []

        self._node_counters: dict[str, int] = defaultdict(int)
        self._edge_counter = 0
        self._node_ids: set[str] = set()

    def _next_node_id(self, node_type: str) -> str:
        """Gera o próximo ID para um tipo de nó."""
        if node_type not in NODE_PREFIXES:
            raise ValueError(f"invalid node type: {node_type!r}")

        self._node_counters[node_type] += 1
        prefix = NODE_PREFIXES[node_type]

        return f"{prefix}{self._node_counters[node_type]}"

    def _normalize_node_label(
        self,
        node_type: str,
        raw_label: str,
    ) -> str:
        """Normaliza o rótulo respeitando casos especiais."""
        if not isinstance(raw_label, str):
            raise TypeError("raw_label must be a string")

        # O Patient usa o identificador original do caso. Aplicar case
        # folding aqui transformaria PMC em pmc.
        if node_type == "Patient":
            return raw_label.strip()

        return self.normalizer.normalize_entity_label(raw_label)

    def add_node(
        self,
        node_type: str,
        raw_label: str,
        attributes: dict[str, Any] | None = None,
    ) -> Node:
        """Normaliza e adiciona um nó ao grafo."""
        node_id = self._next_node_id(node_type)
        label = self._normalize_node_label(
            node_type,
            raw_label,
        )

        node = Node(
            case_id=self.case_id,
            node_id=node_id,
            type=node_type,
            label=label,
            attributes=dict(attributes or {}),
        )

        self.nodes.append(node)
        self._node_ids.add(node.node_id)

        return node

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        attributes: dict[str, Any] | None = None,
    ) -> Edge:
        """Adiciona uma aresta entre dois nós existentes."""
        if source_id not in self._node_ids:
            raise ValueError(
                f"source node does not exist: {source_id!r}"
            )

        if target_id not in self._node_ids:
            raise ValueError(
                f"target node does not exist: {target_id!r}"
            )

        self._edge_counter += 1

        edge = Edge(
            case_id=self.case_id,
            edge_id=f"e{self._edge_counter}",
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            attributes=dict(attributes or {}),
        )

        self.edges.append(edge)
        return edge

    def node_rows(self) -> list[dict[str, str]]:
        """Retorna as linhas da tabela de nós."""
        return [node.to_row() for node in self.nodes]

    def edge_rows(self) -> list[dict[str, str]]:
        """Retorna as linhas da tabela de arestas."""
        return [edge.to_row() for edge in self.edges]