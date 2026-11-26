"""Geração determinística das partições treino/validação/teste (divisoes.csv)."""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from project2.src.comum import REPO

COLUNAS = ("fonte", "case_id", "article_id", "particao")
FONTES_VALIDAS = frozenset({"multicare", "maccrobat"})
PARTICOES_VALIDAS = frozenset({"treino", "validacao", "teste"})
SEMENTE_PADRAO = 42

CASES_MULTICARE_PADRAO = REPO / "project2/data/corpus/csv/full/cases.csv"
METADATA_MULTICARE_PADRAO = REPO / "project2/data/corpus/csv/full/metadata.csv"
CASOS_MACCROBAT_PADRAO = REPO / "project3/data/interim/maccrobat/casos.csv"
GOLD_PADRAO = REPO / "project2/data/gold/casos.txt"
SAIDA_PADRAO = REPO / "project3/data/divisoes.csv"


def carregar_gold(caminho_gold: Path = GOLD_PADRAO) -> set[str]:
    """Lê os case_ids do gabarito do P2."""
    return {
        linha.strip()
        for linha in caminho_gold.read_text(encoding="utf-8").splitlines()
        if linha.strip() and not linha.strip().startswith("#")
    }


def _atribuir_particoes(
    artigos: list[str],
    fixos: dict[str, str],
    proporcoes: tuple[float, float, float],
    semente: int,
) -> dict[str, str]:
    """Atribui treino/validacao/teste por artigo respeitando artigos fixos."""
    p_treino, p_val, p_teste = proporcoes
    if abs((p_treino + p_val + p_teste) - 1.0) > 1e-6:
        raise ValueError(f"Proporções devem somar 1.0: {proporcoes}")

    total = len(artigos)
    alvo_teste = round(total * p_teste)
    alvo_val = round(total * p_val)

    particao_por_artigo = dict(fixos)
    contagem_fixos = Counter(particao_por_artigo.values())

    faltam_teste = max(0, alvo_teste - contagem_fixos["teste"])
    faltam_val = max(0, alvo_val - contagem_fixos["validacao"])

    restantes = sorted(a for a in artigos if a not in particao_por_artigo)
    rng = random.Random(semente)
    rng.shuffle(restantes)

    for artigo in restantes[:faltam_teste]:
        particao_por_artigo[artigo] = "teste"
    for artigo in restantes[faltam_teste : faltam_teste + faltam_val]:
        particao_por_artigo[artigo] = "validacao"
    for artigo in restantes[faltam_teste + faltam_val :]:
        particao_por_artigo[artigo] = "treino"

    return particao_por_artigo


def gerar_divisoes(
    cases_multicare: Path = CASES_MULTICARE_PADRAO,
    metadata_multicare: Path | None = METADATA_MULTICARE_PADRAO,
    casos_maccrobat: Path = CASOS_MACCROBAT_PADRAO,
    caminho_gold: Path = GOLD_PADRAO,
    saida: Path = SAIDA_PADRAO,
    semente: int = SEMENTE_PADRAO,
    prop_multicare: tuple[float, float, float] = (0.80, 0.10, 0.10),
    prop_maccrobat: tuple[float, float, float] = (0.70, 0.15, 0.15),
) -> dict:
    """Gera project3/data/divisoes.csv agrupado por article_id, com gold sempre em teste."""
    gold_ids = carregar_gold(caminho_gold)

    mc_casos_por_artigo: dict[str, list[str]] = defaultdict(list)
    mc_artigo_por_caso: dict[str, str] = {}
    with cases_multicare.open(encoding="utf-8", newline="") as handle:
        for linha in csv.DictReader(handle):
            cid = linha["case_id"].strip()
            aid = linha["article_id"].strip()
            mc_casos_por_artigo[aid].append(cid)
            mc_artigo_por_caso[cid] = aid

    gold_faltando = sorted(g for g in gold_ids if g not in mc_artigo_por_caso)
    if gold_faltando:
        raise ValueError(f"Casos gold ausentes no corpus MultiCaRe: {gold_faltando}")

    fixos_mc = {mc_artigo_por_caso[cid]: "teste" for cid in gold_ids}
    part_mc = _atribuir_particoes(
        sorted(mc_casos_por_artigo),
        fixos_mc,
        prop_multicare,
        semente,
    )

    pmid_para_artigo_mc: dict[str, str] = {}
    if metadata_multicare is not None and metadata_multicare.is_file():
        with metadata_multicare.open(encoding="utf-8", newline="") as handle:
            for linha in csv.DictReader(handle):
                pmid = (linha.get("pmid") or "").strip()
                aid = linha["article_id"].strip()
                if pmid and aid in part_mc:
                    pmid_para_artigo_mc[pmid] = aid

    macc_casos_por_artigo: dict[str, list[str]] = defaultdict(list)
    with casos_maccrobat.open(encoding="utf-8", newline="") as handle:
        for linha in csv.DictReader(handle):
            cid = linha["case_id"].strip()
            aid = linha["article_id"].strip()
            macc_casos_por_artigo[aid].append(cid)

    # Artigos do MACCROBAT que também existem no MultiCaRe (mesmo PMID) herdam a mesma partição.
    fixos_macc: dict[str, str] = {}
    for aid_macc in sorted(macc_casos_por_artigo):
        aid_mc = pmid_para_artigo_mc.get(aid_macc)
        if aid_mc is not None:
            fixos_macc[aid_macc] = part_mc[aid_mc]

    part_macc = _atribuir_particoes(
        sorted(macc_casos_por_artigo),
        fixos_macc,
        prop_maccrobat,
        semente + 1,
    )

    linhas: list[dict[str, str]] = []
    for aid in sorted(mc_casos_por_artigo):
        part = part_mc[aid]
        for cid in sorted(mc_casos_por_artigo[aid]):
            linhas.append({
                "fonte": "multicare",
                "case_id": cid,
                "article_id": aid,
                "particao": part,
            })

    for aid in sorted(macc_casos_por_artigo):
        part = part_macc[aid]
        for cid in sorted(macc_casos_por_artigo[aid]):
            linhas.append({
                "fonte": "maccrobat",
                "case_id": cid,
                "article_id": aid,
                "particao": part,
            })

    linhas.sort(key=lambda r: (r["fonte"], r["article_id"], r["case_id"]))

    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUNAS)
        writer.writeheader()
        writer.writerows(linhas)

    resumo = {
        "saida": str(saida),
        "semente": semente,
        "gold_em_teste": len(gold_ids),
        "sobreposicao_pmid_multicare_maccrobat": len(fixos_macc),
        "multicare": {
            "artigos": dict(Counter(part_mc.values())),
            "casos": dict(Counter(r["particao"] for r in linhas if r["fonte"] == "multicare")),
        },
        "maccrobat": {
            "artigos": dict(Counter(part_macc.values())),
            "casos": dict(Counter(r["particao"] for r in linhas if r["fonte"] == "maccrobat")),
        },
    }
    return resumo


def carregar_divisoes(caminho: Path = SAIDA_PADRAO) -> list[dict[str, str]]:
    """Lê divisoes.csv e retorna a lista de registros."""
    with caminho.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    p_gerar = sub.add_parser("gerar", help="Gera divisoes.csv a partir de MultiCaRe e MACCROBAT.")
    p_gerar.add_argument("--cases-multicare", type=Path, default=CASES_MULTICARE_PADRAO)
    p_gerar.add_argument("--metadata-multicare", type=Path, default=METADATA_MULTICARE_PADRAO)
    p_gerar.add_argument("--casos-maccrobat", type=Path, default=CASOS_MACCROBAT_PADRAO)
    p_gerar.add_argument("--gold", type=Path, default=GOLD_PADRAO)
    p_gerar.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    p_gerar.add_argument("--semente", type=int, default=SEMENTE_PADRAO)

    args = parser.parse_args()
    if args.comando == "gerar":
        resumo = gerar_divisoes(
            cases_multicare=args.cases_multicare,
            metadata_multicare=args.metadata_multicare,
            casos_maccrobat=args.casos_maccrobat,
            caminho_gold=args.gold,
            saida=args.saida,
            semente=args.semente,
        )
        print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
