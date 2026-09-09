"""CLI: converte um caso clínico em tabelas de nós e arestas."""

from __future__ import annotations

import argparse

from exporters import export_graph
from pipeline import process_case_from_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Converte um caso clínico (case_id) em tabelas de nós e arestas, "
        "ligando entidades a conceitos do MeSH quando possível."
    )
    parser.add_argument("--cases", required=True, help="Caminho para sample/cases.csv")
    parser.add_argument("--case-id", required=True, help="Identificador PMC..._NN")
    parser.add_argument("--output", default="output/dicionarios", help="Diretório de saída")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    graph = process_case_from_csv(args.cases, args.case_id)
    nodes_path, edges_path = export_graph(graph, args.output)
    print(f"nodes: {nodes_path}")
    print(f"edges: {edges_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
