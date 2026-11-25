"""Acurácia de código no gold do P2: léxico do P2 × SapBERT (Etapa 5, Frente C).

Só avaliação final: nada aqui ajusta limiar nem filtro (eles foram fixados antes, sem o gold).

    python -m project3.src.normalizacao.comparar
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from project2.src.comum import CASOS_PADRAO
from project3.src.normalizacao.normalizacao import REPO, _lexico_p2, normalizar, textos_dos_casos

GOLD = REPO / "project2" / "data" / "gold" / "mencoes.csv"
SAIDA = REPO / "project3" / "data" / "resultados" / "normalizacao.csv"
COLUNAS = ["sistema", "grupo", "mencoes", "com_codigo_previsto", "acertos", "acuracia", "precisao", "cobertura"]


def ler_gold(caminho: Path = GOLD) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def prever(mencoes: list[dict[str, str]]) -> dict[str, list[str]]:
    """Código previsto por cada sistema, na ordem das menções."""
    casos = textos_dos_casos({m["case_id"] for m in mencoes}, CASOS_PADRAO)
    textos, tipos = [m["texto"] for m in mencoes], [m["tipo"] for m in mencoes]
    textos_caso = [casos.get(m["case_id"], "") for m in mencoes]
    return {
        "lexico_p2": _lexico_p2(textos, textos_caso),
        "sapbert": [c for c, _ in normalizar(textos, tipos, metodo="sapbert")],
        "sapbert_filtro_tipo": [c for c, _ in normalizar(textos, tipos, metodo="sapbert", filtrar_tipo=True)],
        "lexico_p2+sapbert": [c for c, _ in normalizar(textos, tipos, metodo="lexico+sapbert",
                                                       textos_caso=textos_caso)],
    }


def medir(gold: list[str], previsto: list[str]) -> dict[str, float]:
    """acuracia = acertos/menções; precisao = acertos/códigos previstos; cobertura = previstos/menções."""
    n, dados = len(gold), sum(1 for p in previsto if p)
    acertos = sum(1 for g, p in zip(gold, previsto) if g and g == p)
    return {"mencoes": n, "com_codigo_previsto": dados, "acertos": acertos,
            "acuracia": round(acertos / n, 4) if n else 0.0,
            "precisao": round(acertos / dados, 4) if dados else 0.0,
            "cobertura": round(dados / n, 4) if n else 0.0}


def comparar(mencoes: list[dict[str, str]], previsoes: dict[str, list[str]]) -> list[dict]:
    """Uma linha por (sistema, grupo). Grupos: menções com código no gold (todas, só MeSH `D…`,
    só anatômicas `ANAT…`) e `sem_codigo`, onde qualquer código previsto é um erro."""
    grupos = {
        "com_codigo": lambda g: bool(g),
        "com_codigo_mesh": lambda g: g.startswith("D"),
        "com_codigo_anat": lambda g: g.startswith("ANAT"),
        "sem_codigo": lambda g: not g,
    }
    linhas = []
    for sistema, previsto in previsoes.items():
        for grupo, pertence in grupos.items():
            idx = [i for i, m in enumerate(mencoes) if pertence(m["mesh"])]
            linhas.append({"sistema": sistema, "grupo": grupo,
                           **medir([mencoes[i]["mesh"] for i in idx], [previsto[i] for i in idx])})
    return linhas


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    args = parser.parse_args(argv)
    mencoes = ler_gold()
    linhas = comparar(mencoes, prever(mencoes))
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    with args.saida.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerows(linhas)
    for l in linhas:
        print(f"{l['sistema']:20} {l['grupo']:16} n={l['mencoes']:3} acertos={l['acertos']:3} "
              f"acurácia={l['acuracia']:.3f} precisão={l['precisao']:.3f} cobertura={l['cobertura']:.3f}")


if __name__ == "__main__":
    main()
