"""Top-k e MRR do diagnóstico diferencial por sistema (Etapa 8, Frente C).

Lê as predições da frente D e compara com os diagnósticos dos grafos dos casos de teste.

    python -m project3.src.avaliacao_diagnostico.avaliar

Resposta certa de um caso: os códigos MeSH dos nós `Diagnosis` presentes (polarity != absent) do
grafo dele. Casos de teste: partição `teste` do MultiCaRe em `divisoes.csv`; enquanto ela não
existe, os 8 casos do gold do P2. Caso sem predição de um sistema conta como erro desse sistema.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from project2.src.avaliacao.avaliar import _parse_attrs
from project2.src.comum import casos_gold
from project3.src.avaliacao_diagnostico.arvore import ARVORE, Arvore

REPO = Path(__file__).resolve().parents[3]
DIVISOES = REPO / "project3" / "data" / "divisoes.csv"
PREDICOES = REPO / "project3" / "data" / "processed" / "diagnostico" / "predicoes.csv"
GRAFOS = REPO / "project3" / "data" / "processed" / "grafo" / "aluno"
GRAFOS_P2 = REPO / "project2" / "data" / "grafo"
SAIDA = REPO / "project3" / "data" / "resultados" / "diagnostico.csv"
KS = (1, 3, 5)
COLUNAS_PREDICOES = ["sistema", "case_id", "rank", "mesh", "rotulo", "score", "casos_fonte"]


@dataclass(frozen=True)
class Sugestao:
    rank: int
    mesh: str
    rotulo: str
    casos_fonte: tuple[str, ...]


def ler_csv(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def casos_de_teste(divisoes: Path = DIVISOES) -> set[str]:
    if not divisoes.is_file():
        return casos_gold()
    return {l["case_id"] for l in ler_csv(divisoes) if l["fonte"] == "multicare" and l["particao"] == "teste"}


def diagnosticos_do_grafo(nodes: list[dict[str, str]]) -> set[str]:
    """Códigos MeSH dos nós Diagnosis que não foram negados."""
    codigos = set()
    for n in nodes:
        attrs = _parse_attrs(n.get("attributes", ""))
        if n["type"] == "Diagnosis" and attrs.get("polarity") != "absent" and attrs.get("mesh"):
            codigos.add(attrs["mesh"])
    return codigos


def respostas(casos: set[str], pasta: Path) -> dict[str, set[str]]:
    """case_id -> códigos certos, só dos casos que têm grafo e algum diagnóstico com código."""
    saida = {}
    for cid in sorted(casos):
        arquivo = pasta / f"{cid}-nodes.csv"
        if arquivo.is_file() and (codigos := diagnosticos_do_grafo(ler_csv(arquivo))):
            saida[cid] = codigos
    return saida


def ler_predicoes(caminho: Path = PREDICOES) -> dict[str, dict[str, list[Sugestao]]]:
    """sistema -> case_id -> sugestões em ordem de rank."""
    linhas = ler_csv(caminho)
    if linhas and (faltam := set(COLUNAS_PREDICOES) - set(linhas[0])):
        raise ValueError(f"{caminho} sem as colunas {sorted(faltam)}")
    saida: dict[str, dict[str, list[Sugestao]]] = defaultdict(lambda: defaultdict(list))
    for l in linhas:
        fontes = tuple(c for c in l["casos_fonte"].split(";") if c)
        saida[l["sistema"]][l["case_id"]].append(Sugestao(int(l["rank"]), l["mesh"], l["rotulo"], fontes))
    for por_caso in saida.values():
        for lista in por_caso.values():
            lista.sort(key=lambda s: s.rank)
    return saida


def primeiro_acerto(sugestoes: list[Sugestao], certos: set[str], casa) -> int | None:
    """Rank da primeira sugestão (até o rank 5) que casa com algum código certo."""
    for s in sugestoes:
        if s.rank <= max(KS) and s.mesh and any(casa(s.mesh, c) for c in certos):
            return s.rank
    return None


def metricas(posicoes: list[int | None], sufixo: str = "") -> dict[str, float]:
    n = len(posicoes)
    saida = {f"top{k}{sufixo}": round(sum(1 for p in posicoes if p and p <= k) / n, 4) if n else 0.0 for k in KS}
    saida[f"mrr{sufixo}"] = round(sum(1 / p for p in posicoes if p) / n, 4) if n else 0.0
    return saida


def avaliar(predicoes: dict[str, dict[str, list[Sugestao]]], certos: dict[str, set[str]],
            arvore: Arvore | None = None) -> list[dict]:
    """Uma linha por sistema. As métricas `_hier` (pai ou filho direto no MeSH) ficam em colunas à parte."""
    linhas = []
    for sistema in sorted(predicoes):
        por_caso = predicoes[sistema]
        exatas = [primeiro_acerto(por_caso.get(c, []), certos[c], str.__eq__) for c in sorted(certos)]
        linha = {"sistema": sistema, "casos": len(certos),
                 "casos_sem_predicao": sum(1 for c in certos if not por_caso.get(c)), **metricas(exatas)}
        if arvore is not None:
            hier = [primeiro_acerto(por_caso.get(c, []), certos[c], arvore.parentes) for c in sorted(certos)]
            linha.update(metricas(hier, "_hier"))
        linhas.append(linha)
    return linhas


def escrever(linhas: list[dict], saida: Path = SAIDA) -> None:
    saida.parent.mkdir(parents=True, exist_ok=True)
    colunas = list(dict.fromkeys(k for l in linhas for k in l))
    with saida.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=colunas)
        escritor.writeheader()
        escritor.writerows(linhas)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--predicoes", type=Path, default=PREDICOES)
    parser.add_argument("--grafos", type=Path, default=GRAFOS if GRAFOS.is_dir() else GRAFOS_P2)
    parser.add_argument("--divisoes", type=Path, default=DIVISOES)
    parser.add_argument("--arvore", type=Path, default=ARVORE)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    args = parser.parse_args(argv)
    certos = respostas(casos_de_teste(args.divisoes), args.grafos)
    arvore = Arvore.ler(args.arvore) if args.arvore.is_file() else None
    if arvore is None:
        print(f"aviso: {args.arvore} não existe; sem métricas hierárquicas")
    linhas = avaliar(ler_predicoes(args.predicoes), certos, arvore)
    escrever(linhas, args.saida)
    print(f"{len(certos)} casos de teste com diagnóstico codificado (grafos em {args.grafos})")
    for l in linhas:
        print("  ".join(f"{k}={v}" for k, v in l.items()))


if __name__ == "__main__":
    main()
