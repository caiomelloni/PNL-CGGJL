"""Consultas e leitura dos grafos no contrato do Projeto 2."""
from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from project1.tools.graph_csv import parse_attributes
from project2.src.comum import CASOS_PADRAO, REPO, iter_registros

TIPOS_PERMITIDOS = frozenset({"Symptom", "Finding", "ExamResult"})
GRAFOS = REPO / "project3/data/processed/grafo/aluno"
GRAFOS_P2 = REPO / "project2/data/grafo"
DIVISOES = REPO / "project3/data/divisoes.csv"
CORPUS = REPO / "project2/data/corpus/csv/full/cases.csv"
PREDICOES = REPO / "project3/data/processed/diagnostico/predicoes.csv"
IDENTIFICADOR_ARTIGO = re.compile(r"\bPMC\d+(?:_\d+)?\b", re.IGNORECASE)


def atributos(no: Mapping) -> Mapping:
    valor = no.get("attributes")
    return valor if isinstance(valor, Mapping) else parse_attributes(valor or "")


def preparar_consulta(consulta: Iterable[Mapping]) -> list[dict]:
    """Projeta os campos permitidos, inclusive para entradas da interface."""
    resultado = []
    vistos = set()
    for no in consulta:
        if not isinstance(no, Mapping):
            raise ValueError("Cada achado precisa ser um objeto")
        tipo = no.get("type", "")
        rotulo = str(no.get("label") or "").strip()
        if tipo not in TIPOS_PERMITIDOS or not rotulo or IDENTIFICADOR_ARTIGO.search(rotulo):
            continue
        attrs = atributos(no)
        mesh = str(no.get("mesh") or attrs.get("mesh") or "").strip()
        polaridade = no.get("polarity") or attrs.get("polarity") or "present"
        if polaridade not in {"present", "absent"}:
            raise ValueError(f"Polaridade inválida em {rotulo!r}: {polaridade!r}")
        chave = tipo, rotulo.casefold(), mesh, polaridade
        if chave not in vistos:
            resultado.append(dict(type=tipo, label=rotulo, mesh=mesh, polarity=polaridade))
            vistos.add(chave)
    return resultado


def montar_consulta(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Usa sintomas, achados e resultados. Descarta diagnósticos que vazaram para esses tipos."""
    # As arestas fazem parte da entrada do grafo, mas não entram na consulta.
    diagnosticos = [no for no in nodes if no.get("type") == "Diagnosis"]
    codigos = {str(atributos(no).get("mesh") or "") for no in diagnosticos} - {""}
    termos = {str(no.get("label") or "").strip() for no in diagnosticos} - {""}
    bloqueio = re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(t) for t in sorted(termos | codigos)) + r")(?!\w)",
        re.IGNORECASE,
    ) if termos or codigos else None
    return [
        item for item in preparar_consulta(nodes)
        if item["mesh"] not in codigos and (bloqueio is None or not bloqueio.search(item["label"]))
    ]


@dataclass(frozen=True)
class Diagnostico:
    rotulo: str
    mesh: str


@dataclass(frozen=True)
class Caso:
    case_id: str
    article_id: str
    consulta: tuple[dict, ...]
    diagnosticos: tuple[Diagnostico, ...]
    texto: str


def linhas(caminho: Path) -> list[dict]:
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def artigo_do_caso(case_id: str) -> str:
    return re.sub(r"_\d+$", "", case_id)


def ler_divisoes(caminho: Path) -> list[dict]:
    if not caminho.is_file():
        return []
    return [linha for linha in linhas(caminho) if linha["fonte"] == "multicare"]


def caminhos_de_nos(pasta: Path) -> dict[str, Path]:
    return {p.name.removesuffix("-nodes.csv"): p for p in sorted(pasta.glob("*-nodes.csv"))}


def ler_textos(corpus: Path, ids: set[str]) -> tuple[dict[str, str], dict[str, str]]:
    textos, artigos = {}, {}
    for linha in iter_registros(corpus):
        cid = linha["case_id"]
        if cid in ids:
            textos[cid] = linha["case_text"]
            if linha.get("article_id"):
                artigos[cid] = str(linha["article_id"])
            if len(textos) == len(ids):
                break
    return textos, artigos


def ler_casos(
    caminhos: Mapping[str, Path], textos: Mapping[str, str], artigos: Mapping[str, str],
) -> dict[str, Caso]:
    resultado = {}
    for cid, caminho in caminhos.items():
        nos = linhas(caminho)
        diagnosticos = []
        for no in nos:
            if no.get("type") == "Diagnosis" and no["label"].strip():
                attrs = atributos(no)
                if attrs.get("polarity", "present") == "present":
                    diagnosticos.append(Diagnostico(no["label"].strip(), attrs.get("mesh", "")))
        resultado[cid] = Caso(
            cid, artigos.get(cid, artigo_do_caso(cid)),
            tuple(montar_consulta(nos, [])), tuple(dict.fromkeys(diagnosticos)), textos.get(cid, ""),
        )
    return resultado


def corpus_padrao() -> Path:
    return CORPUS if CORPUS.is_file() else CASOS_PADRAO
