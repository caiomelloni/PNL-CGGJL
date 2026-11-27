"""API de recuperação e classificação da Frente D."""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock

from .busca import Embeddings, Indice, Vizinho
from .dados import (
    DIVISOES, GRAFOS, GRAFOS_P2, caminhos_de_nos, corpus_padrao, ler_casos,
    ler_divisoes, ler_textos, preparar_consulta,
)

SISTEMAS = ("grafo", "llm", "rag_texto", "rag_grafo", "rag_grafo_p2")
PROMPT = Path(__file__).with_name("prompt.md").read_text(encoding="utf-8")


@dataclass(frozen=True)
class Sugestao:
    rotulo: str
    mesh: str
    score: float
    casos_fonte: tuple[str, ...]


@dataclass(frozen=True)
class Analise:
    sugestoes: list[Sugestao]
    vizinhos: list[Vizinho]
    base: str


def cliente_llm() -> Callable:
    try:
        from project3.src.llm import chamar
    except ModuleNotFoundError as erro:
        if erro.name != "project3.src.llm":
            raise
        raise RuntimeError("O cliente chamar() da Frente B precisa estar disponível em project3.src.llm.") from erro
    except ImportError as erro:
        if erro.name != "project3.src.llm":
            raise
        try:
            from project3.src.llm.cliente import chamar
        except ImportError as causa:
            raise RuntimeError("O pacote da Frente B precisa expor a função chamar().") from causa
    return chamar


def normalizador_mesh() -> Callable:
    try:
        from project3.src.normalizacao.normalizacao import normalizar
    except ModuleNotFoundError as erro:
        if erro.name not in {"project3.src.normalizacao", "project3.src.normalizacao.normalizacao"}:
            raise
        raise RuntimeError("A função normalizar() da Frente C precisa estar disponível.") from erro
    return normalizar


def votar(vizinhos: list[Vizinho], k: int) -> list[Sugestao]:
    votos = defaultdict(float)
    fontes = defaultdict(list)
    rotulos = {}
    for vizinho in vizinhos:
        for diag in vizinho.caso.diagnosticos:
            chave = ("mesh", diag.mesh) if diag.mesh else ("rotulo", diag.rotulo.casefold())
            if vizinho.caso.case_id not in fontes[chave]:
                votos[chave] += vizinho.score
                fontes[chave].append(vizinho.caso.case_id)
                rotulos.setdefault(chave, diag)
    total = sum(votos.values())
    return [
        Sugestao(rotulos[chave].rotulo, rotulos[chave].mesh, votos[chave] / total, tuple(fontes[chave]))
        for chave in sorted(votos, key=lambda chave: (-votos[chave], chave))[:k]
    ]


def interpretar_resposta(resposta: str, disponiveis: set[str]) -> list[tuple[str, float, tuple[str, ...]]]:
    try:
        dados = json.loads(resposta)
    except (TypeError, json.JSONDecodeError) as erro:
        raise ValueError("O LLM retornou uma resposta que não é JSON válido.") from erro
    if isinstance(dados, dict):
        dados = dados.get("sugestoes")
    if not isinstance(dados, list):
        raise ValueError("A resposta precisa incluir a lista 'sugestoes'.")

    resultado = []
    for item in dados:
        if not isinstance(item, dict):
            raise ValueError("Cada sugestão do LLM precisa ser um objeto.")
        rotulo, score = item.get("rotulo"), item.get("score")
        citacoes = item.get("casos_fonte", [])
        if (
            not isinstance(rotulo, str) or not rotulo.strip()
            or not isinstance(score, (float, int)) or isinstance(score, bool)
            or not 0 <= score <= 1 or not math.isfinite(score)
            or not isinstance(citacoes, list) or any(not isinstance(cid, str) for cid in citacoes)
        ):
            raise ValueError("Sugestão do LLM com rótulo, pontuação ou fontes inválidas.")
        fontes = tuple(dict.fromkeys(cid for cid in citacoes if cid in disponiveis))
        if fontes or not disponiveis:
            resultado.append((rotulo.strip(), float(score), fontes))
    return sorted(resultado, key=lambda item: item[1], reverse=True)


class Motor:
    def __init__(
        self,
        *,
        grafos: Path = GRAFOS,
        grafos_p2: Path = GRAFOS_P2,
        corpus: Path | None = None,
        divisoes: Path = DIVISOES,
        modelo_embeddings: str | None = None,
        chamar: Callable | None = None,
        normalizar: Callable | None = None,
        excluir_da_base: set[str] | None = None,
    ):
        caminhos_p2 = caminhos_de_nos(grafos_p2)
        caminhos_p3 = caminhos_de_nos(grafos)
        self.usando_p2 = not caminhos_p3
        self.modelo_embeddings = modelo_embeddings
        self.chamar = chamar
        self.normalizar = normalizar
        self.excluir_da_base = frozenset(excluir_da_base or ())
        self._indices: dict[tuple[bool, bool], Indice] = {}
        self._trava = Lock()
        self._embeddings = None
        arquivos = caminhos_p2.keys() | caminhos_p3.keys()
        if not arquivos:
            raise FileNotFoundError(f"Nenhum grafo encontrado em {grafos} ou {grafos_p2}.")

        caminho_corpus = corpus if corpus is not None else corpus_padrao()
        textos, artigos = ler_textos(caminho_corpus, arquivos) if caminho_corpus.is_file() else ({}, {})
        artigos.update({linha["case_id"]: linha["article_id"] for linha in ler_divisoes(divisoes)})
        self.casos_p2 = ler_casos(caminhos_p2, textos, artigos)
        self.casos = ler_casos(caminhos_p3, textos, artigos) if caminhos_p3 else self.casos_p2

    def _indice(self, base_p2: bool, texto_integral: bool) -> Indice:
        chave = base_p2, texto_integral
        with self._trava:
            if chave not in self._indices:
                casos = self.casos_p2 if base_p2 else self.casos
                elegiveis = [
                    caso for caso in casos.values()
                    if caso.diagnosticos and caso.article_id not in self.excluir_da_base
                ]
                if not elegiveis:
                    raise RuntimeError("A base selecionada não tem casos de referência com diagnóstico.")
                if self.modelo_embeddings and self._embeddings is None:
                    self._embeddings = Embeddings(self.modelo_embeddings)
                self._indices[chave] = Indice(elegiveis, self._embeddings, texto_integral=texto_integral)
            return self._indices[chave]

    def analisar(
        self, consulta: list[dict], k: int = 5, sistema: str = "rag_grafo",
        excluir_artigos: set[str] | None = None, *, limite_vizinhos: int = 5,
    ) -> Analise:
        if sistema not in SISTEMAS:
            raise ValueError(f"Sistema desconhecido: {sistema}")
        if not 1 <= k <= 5 or not 1 <= limite_vizinhos <= 20:
            raise ValueError("k deve ser de 1 a 5 e limite_vizinhos de 1 a 20.")
        consulta = preparar_consulta(consulta)
        base_p2 = self.usando_p2 or sistema == "rag_grafo_p2"
        base = "consulta" if sistema == "llm" else ("P2" if base_p2 else "P3")
        if not consulta:
            return Analise([], [], base)
        vizinhos = []
        if sistema != "llm":
            por_texto = sistema == "rag_texto"
            vizinhos = self._indice(base_p2, por_texto).buscar(
                consulta, excluir_artigos or set(), limite_vizinhos,
            )
            if not vizinhos:
                return Analise([], [], base)
        if sistema == "grafo":
            return Analise(votar(vizinhos, k), vizinhos, base)
        return Analise(self._gerar(consulta, vizinhos, k), vizinhos, base)

    def _gerar(self, consulta: list[dict], vizinhos: list[Vizinho], k: int) -> list[Sugestao]:
        chamar = self.chamar or cliente_llm()
        normalizar = self.normalizar or normalizador_mesh()
        por_fonte = {f"fonte_{i}": viz.caso for i, viz in enumerate(vizinhos, 1)}
        dados = {
            "consulta": consulta,
            "maximo": k,
            "casos": [
                {
                    "referencia": ref,
                    "achados": caso.consulta,
                    "diagnosticos": [d.rotulo for d in caso.diagnosticos],
                }
                for ref, caso in por_fonte.items()
            ],
        }
        resposta = chamar(json.dumps(dados, ensure_ascii=False), sistema=PROMPT, json=True)
        itens = interpretar_resposta(resposta.texto, set(por_fonte))
        if not itens:
            return []
        codigos = normalizar([rotulo for rotulo, _, _ in itens], ["Diagnosis"] * len(itens))
        sugestoes, vistos = [], set()
        for (rotulo, score, fontes), (codigo, _) in zip(itens, codigos, strict=True):
            chave = codigo or rotulo.casefold()
            if chave in vistos:
                continue
            vistos.add(chave)
            sugestoes.append(Sugestao(rotulo, codigo or "", score, tuple(por_fonte[f].case_id for f in fontes)))
            if len(sugestoes) == k:
                break
        return sugestoes

    def sugerir(
        self, consulta: list[dict], k: int = 5, sistema: str = "rag_grafo",
        excluir_artigos: set[str] | None = None,
    ) -> list[Sugestao]:
        return self.analisar(consulta, k, sistema, excluir_artigos).sugestoes


@lru_cache(maxsize=1)
def motor_padrao() -> Motor:
    return Motor(modelo_embeddings=os.getenv("P3_DIAGNOSTICO_EMBEDDINGS"))


def sugerir(
    consulta: list[dict], k: int = 5, sistema: str = "rag_grafo",
    excluir_artigos: set[str] | None = None,
) -> list[Sugestao]:
    return motor_padrao().sugerir(consulta, k, sistema, excluir_artigos)
