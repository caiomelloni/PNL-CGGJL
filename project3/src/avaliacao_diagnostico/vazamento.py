"""Verificações de vazamento da avaliação do diagnóstico (regra 6 de docs/vazamento-de-dados.md).

Cada função devolve a lista de problemas encontrados (vazia = sem vazamento). Os testes em
tests/test_vazamento.py falham se alguma lista vier com itens.
"""
from __future__ import annotations

import re
from pathlib import Path

from project2.src.avaliacao.avaliar import _parse_attrs

# Tipos que podem entrar numa consulta (lista do que pode entrar, não do que deve sair).
TIPOS_PERMITIDOS = frozenset({"Symptom", "Finding", "ExamResult"})


def article_id(case_id: str, por_caso: dict[str, str] | None = None) -> str:
    """PMCID do caso: pelo `divisoes.csv` quando houver, senão o prefixo antes do último `_`."""
    if por_caso and case_id in por_caso:
        return por_caso[case_id]
    return case_id.rsplit("_", 1)[0] if "_" in case_id else case_id


def _contem(texto: str, trecho: str) -> bool:
    trecho = trecho.strip().lower()
    return bool(trecho) and re.search(rf"(?<!\w){re.escape(trecho)}(?!\w)", texto.lower()) is not None


def diagnosticos_do_caso(nodes: list[dict]) -> tuple[set[str], set[str]]:
    """(códigos MeSH, rótulos) de todos os nós Diagnosis do caso, inclusive os negados."""
    codigos, rotulos = set(), set()
    for n in nodes:
        if n.get("type") == "Diagnosis":
            attrs = _parse_attrs(n.get("attributes", ""))
            if attrs.get("mesh"):
                codigos.add(attrs["mesh"])
            rotulos.add(n.get("label", ""))
    return codigos, {r for r in rotulos if r.strip()}


def problemas_da_consulta(consulta: list[dict], nodes: list[dict]) -> list[str]:
    """Tipo fora da lista permitida, ou código/rótulo de um diagnóstico do caso dentro da consulta."""
    codigos, rotulos = diagnosticos_do_caso(nodes)
    problemas = []
    for item in consulta:
        attrs = item.get("attributes", "")
        attrs = _parse_attrs(attrs) if isinstance(attrs, str) else dict(attrs or {})
        rotulo, codigo = item.get("label", ""), item.get("mesh") or attrs.get("mesh", "")
        if item.get("type") not in TIPOS_PERMITIDOS:
            problemas.append(f"tipo {item.get('type')!r} não pode entrar na consulta ({rotulo!r})")
        if codigo and codigo in codigos:
            problemas.append(f"código do diagnóstico {codigo} na consulta ({rotulo!r})")
        for diag in rotulos:
            if _contem(rotulo, diag):
                problemas.append(f"rótulo do diagnóstico {diag!r} na consulta ({rotulo!r})")
    return problemas


def problemas_das_fontes(predicoes: dict, artigos: dict[str, str] | None = None) -> list[str]:
    """Sugestões que citam um caso do mesmo artigo do caso testado (regra 2)."""
    problemas = []
    for sistema, por_caso in predicoes.items():
        for case_id, sugestoes in por_caso.items():
            artigo = article_id(case_id, artigos)
            for s in sugestoes:
                for fonte in s.casos_fonte:
                    if article_id(fonte, artigos) == artigo:
                        problemas.append(f"{sistema}/{case_id} rank {s.rank} cita {fonte} (artigo {artigo})")
    return problemas


def ler_artigos(divisoes: Path) -> dict[str, str]:
    """case_id -> article_id do `divisoes.csv` (vazio se ele ainda não existe)."""
    import csv

    if not divisoes.is_file():
        return {}
    with divisoes.open(encoding="utf-8", newline="") as f:
        return {l["case_id"]: l["article_id"] for l in csv.DictReader(f)}
