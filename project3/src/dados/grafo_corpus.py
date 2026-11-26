"""Geração de grafos do corpus em lotes com retomada (Frente A, Etapa 4)."""
from __future__ import annotations

import argparse
import csv
import json
import pickle
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable

from project1.src.tokenizacao.models import serialize_attributes
from project2.src.comum import REPO, iter_registros
from project2.src.montagem.montagem import EDGE_COLUMNS, NODE_COLUMNS, TIPOS, montar_caso
from project2.src.relacoes.relacoes import (
    COLUNAS_RELACOES,
    DEFAULT_MODELO,
    prever_mencoes,
)

MENCOES_PADRAO = REPO / "project3/data/interim/aluno/mencoes_tipadas.csv"
CORPUS_PADRAO = REPO / "project2/data/corpus/csv/full/cases.csv"
SAIDA_PADRAO = REPO / "project3/data/processed/grafo/aluno"
POLARIDADES_VALIDAS = frozenset({"present", "absent", "uncertain"})


def _caso_pronto(saida: Path, case_id: str) -> bool:
    return (saida / f"{case_id}-nodes.csv").is_file() and (saida / f"{case_id}-edges.csv").is_file()


def _escrever_csv_atomico(caminho: Path, colunas: list[str], linhas: list[dict]) -> None:
    parcial = caminho.with_suffix(caminho.suffix + ".part")
    with parcial.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=colunas)
        writer.writeheader()
        writer.writerows(linhas)
    parcial.replace(caminho)


def _carregar_modelo_relacoes(caminho_modelo: Path):
    if not caminho_modelo.is_file():
        raise FileNotFoundError(
            f"Classificador de relações não encontrado em {caminho_modelo}. "
            "Rode `python -m project2.src.relacoes.relacoes treinar` antes."
        )
    with caminho_modelo.open("rb") as handle:
        return pickle.load(handle)


def _carregar_mencoes_por_caso(
    caminho_mencoes: Path,
    ignorar_sem_tipo: bool = True,
) -> tuple[dict[str, list[dict]], int]:
    por_caso: dict[str, list[dict]] = defaultdict(list)
    omitidas = 0
    with caminho_mencoes.open(encoding="utf-8", newline="") as handle:
        for linha in csv.DictReader(handle):
            tipo = (linha.get("tipo") or "").strip()
            if tipo not in TIPOS:
                if ignorar_sem_tipo:
                    omitidas += 1
                    continue
                raise ValueError(f"Tipo inválido/ausente em {linha.get('case_id')}/{linha.get('id')}: {tipo!r}")
            polaridade = (linha.get("polaridade") or "").strip()
            if polaridade not in POLARIDADES_VALIDAS:
                linha = {**linha, "polaridade": "present"}
            por_caso[linha["case_id"].strip()].append(linha)
    return por_caso, omitidas


def gerar_grafos(
    mencoes: Path = MENCOES_PADRAO,
    corpus: Path = CORPUS_PADRAO,
    saida: Path = SAIDA_PADRAO,
    tamanho_lote: int = 500,
    modelo_relacoes: Path = DEFAULT_MODELO,
    relacoes_saida: Path | None = None,
    sobrescrever: bool = False,
    ignorar_sem_tipo: bool = True,
    preditor_relacoes: Callable[[list[dict], dict[str, str]], list[dict]] | None = None,
) -> dict:
    """Encadeia predição de relações + montagem do P2 em lotes, com retomada automática."""
    if tamanho_lote < 1:
        raise ValueError("tamanho_lote deve ser >= 1")

    inicio = time.perf_counter()
    saida.mkdir(parents=True, exist_ok=True)
    por_caso, omitidas = _carregar_mencoes_por_caso(mencoes, ignorar_sem_tipo=ignorar_sem_tipo)

    pendentes: set[str] = set()
    pulados = 0
    for cid in por_caso:
        if not sobrescrever and _caso_pronto(saida, cid):
            pulados += 1
        else:
            pendentes.add(cid)

    if preditor_relacoes is None and pendentes:
        pipeline = _carregar_modelo_relacoes(modelo_relacoes)
        preditor_relacoes = lambda mencs, textos: prever_mencoes(mencs, textos, pipeline=pipeline)

    rel_handle = None
    rel_writer = None
    if relacoes_saida is not None:
        relacoes_saida.parent.mkdir(parents=True, exist_ok=True)
        modo = "w" if sobrescrever or not relacoes_saida.is_file() else "a"
        rel_handle = relacoes_saida.open(modo, encoding="utf-8", newline="")
        rel_writer = csv.DictWriter(rel_handle, fieldnames=COLUNAS_RELACOES)
        if modo == "w":
            rel_writer.writeheader()

    processados = 0
    lotes = 0
    total_nos = 0
    total_arestas = 0
    lote_registros: list[dict] = []

    def _processar_lote(registros: list[dict]) -> None:
        nonlocal processados, lotes, total_nos, total_arestas
        if not registros:
            return
        textos = {r["case_id"]: r["case_text"] for r in registros}
        mencoes_lote = [m for r in registros for m in por_caso[r["case_id"]]]
        relacoes_lote = preditor_relacoes(mencoes_lote, textos) if preditor_relacoes else []

        rels_por_caso: dict[str, list[dict]] = defaultdict(list)
        for rel in relacoes_lote:
            rels_por_caso[rel["case_id"]].append(rel)
            if rel_writer is not None:
                rel_writer.writerow({c: rel.get(c, "") for c in COLUNAS_RELACOES})

        for reg in registros:
            cid = reg["case_id"]
            nodes, edges = montar_caso(cid, reg["case_text"], por_caso[cid], rels_por_caso[cid], reg)
            _escrever_csv_atomico(
                saida / f"{cid}-nodes.csv",
                NODE_COLUMNS,
                [{**n, "case_id": cid, "attributes": serialize_attributes(n["attributes"])} for n in nodes],
            )
            _escrever_csv_atomico(
                saida / f"{cid}-edges.csv",
                EDGE_COLUMNS,
                [{**e, "case_id": cid, "attributes": serialize_attributes(e["attributes"])} for e in edges],
            )
            processados += 1
            total_nos += len(nodes)
            total_arestas += len(edges)
        lotes += 1

    try:
        if pendentes:
            for reg in iter_registros(corpus):
                cid = reg["case_id"]
                if cid not in pendentes:
                    continue
                lote_registros.append(reg)
                pendentes.remove(cid)
                if len(lote_registros) >= tamanho_lote:
                    _processar_lote(lote_registros)
                    lote_registros = []
                if not pendentes:
                    break
            _processar_lote(lote_registros)
    finally:
        if rel_handle is not None:
            rel_handle.close()

    segundos = round(time.perf_counter() - inicio, 3)
    resumo = {
        "mencoes_entrada": str(mencoes),
        "corpus": str(corpus),
        "saida": str(saida),
        "tamanho_lote": tamanho_lote,
        "casos_no_csv": len(por_caso),
        "casos_processados": processados,
        "casos_pulados_retomada": pulados,
        "casos_nao_encontrados_no_corpus": len(pendentes),
        "lotes_executados": lotes,
        "nos_gerados": total_nos,
        "arestas_geradas": total_arestas,
        "mencoes_sem_tipo_omitidas": omitidas,
        "segundos": segundos,
    }
    (saida / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return resumo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    p_gerar = sub.add_parser("gerar", help="Gera grafos em lotes com retomada automática.")
    p_gerar.add_argument("--mencoes", type=Path, default=MENCOES_PADRAO)
    p_gerar.add_argument("--corpus", type=Path, default=CORPUS_PADRAO)
    p_gerar.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    p_gerar.add_argument("--tamanho-lote", type=int, default=500)
    p_gerar.add_argument("--modelo-relacoes", type=Path, default=DEFAULT_MODELO)
    p_gerar.add_argument("--relacoes-saida", type=Path, default=None)
    p_gerar.add_argument("--sobrescrever", action="store_true")

    args = parser.parse_args()
    if args.comando == "gerar":
        resumo = gerar_grafos(
            mencoes=args.mencoes,
            corpus=args.corpus,
            saida=args.saida,
            tamanho_lote=args.tamanho_lote,
            modelo_relacoes=args.modelo_relacoes,
            relacoes_saida=args.relacoes_saida,
            sobrescrever=args.sobrescrever,
        )
        print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
