"""Partições treino/validação/teste lidas de `divisoes.csv` (Frente A), com substituto provisório."""
from __future__ import annotations

import csv
import hashlib
import warnings
from pathlib import Path

from project2.src.comum import CASOS_PADRAO, casos_gold, iter_casos

REPO = Path(__file__).resolve().parents[3]
DIVISOES = REPO / "project3/data/divisoes.csv"


def artigo(case_id: str) -> str:
    """PMC4782471_02 -> PMC4782471: casos do mesmo artigo ficam sempre na mesma partição."""
    return case_id.rsplit("_", 1)[0]


def ler_divisoes(caminho: Path = DIVISOES, corpus: Path = CASOS_PADRAO) -> dict[str, str]:
    """{case_id: particao}. Os casos do gabarito do P2 são sempre `teste`, senão falha."""
    gold = casos_gold()
    if Path(caminho).is_file():
        with open(caminho, encoding="utf-8", newline="") as handle:
            particoes = {l["case_id"]: l["particao"] for l in csv.DictReader(handle)}
    else:
        # Enquanto a Frente A não entrega o arquivo: gold é teste; o resto é dividido por artigo,
        # com um hash fixo (1 em cada 5 artigos vai para validação).
        warnings.warn(f"{caminho} não existe: usando divisão provisória (gold = teste)", stacklevel=2)
        particoes = {}
        for case_id, _ in iter_casos(corpus):
            sorteio = int(hashlib.md5(artigo(case_id).encode()).hexdigest(), 16) % 5
            particoes[case_id] = "validacao" if sorteio == 0 else "treino"
        particoes.update({c: "teste" for c in gold})
    fora = [c for c in gold if particoes.get(c) != "teste"]
    if fora:
        raise ValueError(f"Casos do gabarito fora de teste: {sorted(fora)}")
    return particoes


def garantir_fora_do_teste(case_ids, particoes: dict[str, str]) -> None:
    """Regra 3 de vazamento-de-dados.md: gabarito e teste nunca entram em treino nem em prompt."""
    proibidos = sorted(set(case_ids) & ({c for c, p in particoes.items() if p == "teste"} | casos_gold()))
    if proibidos:
        raise ValueError(f"Casos de teste usados em treino ou prompt: {proibidos[:5]}")
