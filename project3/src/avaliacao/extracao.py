"""Avaliação comparativa da extração: P1 × P2 × professor × aluno (Frente A, Etapa 6)."""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from project2.src.avaliacao.avaliar import (
    avaliar_grafo,
    avaliar_mencoes,
    avaliar_relacoes,
    avaliar_tipos,
)
from project2.src.comum import REPO, casos_gold
from project3.src.dados.divisoes import SAIDA_PADRAO as DIVISOES_PADRAO, carregar_divisoes

COLUNAS_EXTRACAO = (
    "conjunto",
    "sistema",
    "criterio",
    "n_casos",
    "mencoes_precisao",
    "mencoes_revocacao",
    "mencoes_f1",
    "mencoes_n_pred",
    "mencoes_n_gold",
    "tipos_cobertura",
    "tipos_acuracia",
    "tipos_macro_f1",
    "polaridade_acuracia",
    "polaridade_f1_absent",
    "relacoes_precisao",
    "relacoes_revocacao",
    "relacoes_f1",
    "relacoes_macro_f1",
    "grafo_nos",
    "grafo_arestas",
    "grafo_grau_medio",
    "grafo_pct_mesh",
    "alucinacoes",
    "segundos_por_caso",
    "custo_usd_por_caso",
)

GOLD_MENCOES_PADRAO = REPO / "project2/data/gold/mencoes.csv"
GOLD_RELACOES_PADRAO = REPO / "project2/data/gold/relacoes.csv"
MACCROBAT_MENCOES_PADRAO = REPO / "project3/data/interim/maccrobat/mencoes.csv"
SAIDA_PADRAO = REPO / "project3/data/resultados/extracao.csv"


@dataclass(frozen=True)
class SistemaConfig:
    """Configuração de caminhos de um sistema avaliado."""

    nome: str
    mencoes: Path
    relacoes: Path | None = None
    grafo_dir: Path | None = None
    alucinacoes: Path | None = None
    metricas_execucao: Path | None = None
    custo_padrao: float | None = 0.0


def sistemas_padrao(raiz: Path = REPO) -> list[SistemaConfig]:
    """Retorna os quatro sistemas previstos no contrato da Etapa 6."""
    return [
        SistemaConfig(
            nome="regras_p1",
            mencoes=raiz / "project2/data/regras/mencoes.csv",
            relacoes=raiz / "project2/data/regras/relacoes.csv",
            grafo_dir=raiz / "project1/data/processed",
            custo_padrao=0.0,
        ),
        SistemaConfig(
            nome="p2",
            mencoes=raiz / "project2/data/mencoes_tipadas.csv",
            relacoes=raiz / "project2/data/relacoes.csv",
            grafo_dir=raiz / "project2/data/grafo",
            custo_padrao=0.0,
        ),
        SistemaConfig(
            nome="professor",
            mencoes=raiz / "project3/data/interim/professor/mencoes_tipadas.csv",
            relacoes=raiz / "project3/data/interim/professor/relacoes.csv",
            grafo_dir=raiz / "project3/data/processed/grafo/professor",
            alucinacoes=raiz / "project3/data/interim/professor/alucinacoes.csv",
            # Por caso (case_id, segundos, custo_usd). O uso_llm.csv não tem case_id: somaria todas as
            # chamadas do log, de todas as execuções, e inflaria o custo por caso.
            metricas_execucao=raiz / "project3/data/interim/professor/execucao.csv",
            custo_padrao=None,
        ),
        SistemaConfig(
            nome="aluno",
            mencoes=raiz / "project3/data/interim/aluno/mencoes_tipadas.csv",
            relacoes=raiz / "project3/data/interim/aluno/relacoes.csv",
            grafo_dir=raiz / "project3/data/processed/grafo/aluno",
            alucinacoes=raiz / "project3/data/interim/aluno/alucinacoes.csv",
            metricas_execucao=raiz / "project3/data/interim/aluno/resumo.json",
            custo_padrao=0.0,
        ),
    ]


def _ler_mencoes(caminho: Path) -> list[dict[str, Any]]:
    with caminho.open(encoding="utf-8", newline="") as handle:
        linhas = list(csv.DictReader(handle))
    for linha in linhas:
        linha["start"] = int(linha["start"])
        linha["end"] = int(linha["end"])
    return linhas


def _ler_csv(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _contar_alucinacoes(caminho: Path | None, casos_alvo: set[str]) -> int:
    if caminho is None or not caminho.is_file():
        return 0
    total = 0
    for linha in _ler_csv(caminho):
        # Só `nao_encontrado` é alucinação; tipo_invalido, texto_vazio etc. são outros descartes.
        if linha.get("case_id", "").strip() in casos_alvo and linha.get("motivo", "nao_encontrado") == "nao_encontrado":
            total += 1
    return total


def _ler_telemetria(
    caminho: Path | None,
    casos_alvo: set[str],
    custo_padrao: float | None,
) -> tuple[str, str]:
    """Extrai (segundos_por_caso, custo_usd_por_caso) de JSON de resumo ou CSV de uso."""
    segundos = ""
    custo = f"{custo_padrao:.6f}" if custo_padrao is not None else ""

    if caminho is None or not caminho.is_file():
        return segundos, custo

    if caminho.suffix.lower() == ".json":
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        if "segundos_por_caso" in dados and dados["segundos_por_caso"] is not None:
            segundos = f"{float(dados['segundos_por_caso']):.4f}"
        elif dados.get("segundos") is not None and dados.get("casos"):
            segundos = f"{float(dados['segundos']) / float(dados['casos']):.4f}"
        if "custo_usd_por_caso" in dados and dados["custo_usd_por_caso"] is not None:
            custo = f"{float(dados['custo_usd_por_caso']):.6f}"
        return segundos, custo

    # CSV de telemetria (ex.: uso_llm.csv com colunas opcionais case_id, segundos, custo_usd)
    linhas = _ler_csv(caminho)
    filtradas = [l for l in linhas if not l.get("case_id") or l["case_id"].strip() in casos_alvo]
    if not filtradas:
        return segundos, custo

    n_ref = len({l["case_id"].strip() for l in filtradas if l.get("case_id")}) or len(casos_alvo)
    if n_ref <= 0:
        return segundos, custo

    vals_seg = [float(l["segundos"]) for l in filtradas if l.get("segundos") not in (None, "")]
    if vals_seg:
        segundos = f"{sum(vals_seg) / n_ref:.4f}"

    vals_custo = [float(l["custo_usd"]) for l in filtradas if l.get("custo_usd") not in (None, "")]
    if vals_custo:
        custo = f"{sum(vals_custo) / n_ref:.6f}"

    return segundos, custo


def _fmt(valor: float | int | None, casas: int = 4) -> str:
    if valor is None or valor == "":
        return ""
    if isinstance(valor, int):
        return str(valor)
    return f"{float(valor):.{casas}f}"


def _avaliar_par(
    conjunto: str,
    sistema: SistemaConfig,
    gold_mencoes: list[dict[str, Any]],
    casos_alvo: set[str],
    gold_relacoes: list[dict[str, str]] | None,
    avaliar_polaridade: bool,
) -> list[dict[str, Any]]:
    if not sistema.mencoes.is_file():
        return []

    pred_todas = _ler_mencoes(sistema.mencoes)
    pred = [m for m in pred_todas if m["case_id"] in casos_alvo]
    if not pred:
        return []

    gold = [m for m in gold_mencoes if m["case_id"] in casos_alvo]
    pred_spans = [(m["case_id"], int(m["start"]), int(m["end"])) for m in pred]
    gold_spans = [(m["case_id"], int(m["start"]), int(m["end"])) for m in gold]

    res_mencoes = avaliar_mencoes(pred_spans, gold_spans)

    pred_rel: list[dict[str, str]] | None = None
    if gold_relacoes is not None and sistema.relacoes is not None and sistema.relacoes.is_file():
        pred_rel = [r for r in _ler_csv(sistema.relacoes) if r["case_id"] in casos_alvo]

    res_grafo: dict[str, Any] | None = None
    if sistema.grafo_dir is not None and sistema.grafo_dir.is_dir():
        metricas_g = avaliar_grafo(sistema.grafo_dir, casos=casos_alvo)
        if metricas_g["n_casos"] > 0:
            res_grafo = metricas_g

    aluc = _contar_alucinacoes(sistema.alucinacoes, casos_alvo)
    seg_caso, custo_caso = _ler_telemetria(sistema.metricas_execucao, casos_alvo, sistema.custo_padrao)

    linhas: list[dict[str, Any]] = []
    for criterio, exato in (("exato", True), ("sobreposicao", False)):
        rm = res_mencoes[criterio]
        rt = avaliar_tipos(pred, gold, exato=exato)

        rr: dict[str, Any] | None = None
        if pred_rel is not None and gold_relacoes is not None:
            gold_rel_filtrado = [r for r in gold_relacoes if r["case_id"] in casos_alvo]
            rr = avaliar_relacoes(pred_rel, gold_rel_filtrado, pred, gold, exato=exato)

        linhas.append({
            "conjunto": conjunto,
            "sistema": sistema.nome,
            "criterio": criterio,
            "n_casos": len(casos_alvo),
            "mencoes_precisao": _fmt(rm["precisao"]),
            "mencoes_revocacao": _fmt(rm["revocacao"]),
            "mencoes_f1": _fmt(rm["f1"]),
            "mencoes_n_pred": rm["n_pred"],
            "mencoes_n_gold": rm["n_gold"],
            "tipos_cobertura": _fmt(rt["cobertura"]),
            "tipos_acuracia": _fmt(rt["acuracia"]),
            "tipos_macro_f1": _fmt(rt["macro_f1"]),
            "polaridade_acuracia": _fmt(rt["acuracia_polaridade"]) if avaliar_polaridade else "",
            "polaridade_f1_absent": _fmt(rt["f1_absent"]) if avaliar_polaridade else "",
            "relacoes_precisao": _fmt(rr["precisao"]) if rr else "",
            "relacoes_revocacao": _fmt(rr["revocacao"]) if rr else "",
            "relacoes_f1": _fmt(rr["f1"]) if rr else "",
            "relacoes_macro_f1": _fmt(rr["macro_f1"]) if rr else "",
            "grafo_nos": res_grafo["n_nos"] if res_grafo else "",
            "grafo_arestas": res_grafo["n_arestas"] if res_grafo else "",
            "grafo_grau_medio": _fmt(res_grafo["grau_medio"]) if res_grafo else "",
            "grafo_pct_mesh": _fmt(res_grafo["pct_nos_com_mesh"]) if res_grafo else "",
            "alucinacoes": aluc,
            "segundos_por_caso": seg_caso,
            "custo_usd_por_caso": custo_caso,
        })
    return linhas


def avaliar_extracao(
    sistemas: list[SistemaConfig] | None = None,
    gold_mencoes: Path = GOLD_MENCOES_PADRAO,
    gold_relacoes: Path = GOLD_RELACOES_PADRAO,
    maccrobat_mencoes: Path = MACCROBAT_MENCOES_PADRAO,
    caminho_divisoes: Path = DIVISOES_PADRAO,
    saida: Path = SAIDA_PADRAO,
) -> list[dict[str, Any]]:
    """Avalia todos os sistemas disponíveis no gold do P2 e no teste do MACCROBAT."""
    sistemas = sistemas if sistemas is not None else sistemas_padrao()
    linhas: list[dict[str, Any]] = []

    if gold_mencoes.is_file():
        gold_m = _ler_mencoes(gold_mencoes)
        gold_r = _ler_csv(gold_relacoes) if gold_relacoes.is_file() else None
        casos_g = {m["case_id"] for m in gold_m}
        for sis in sistemas:
            linhas.extend(
                _avaliar_par(
                    conjunto="gold_p2",
                    sistema=sis,
                    gold_mencoes=gold_m,
                    casos_alvo=casos_g,
                    gold_relacoes=gold_r,
                    avaliar_polaridade=True,
                )
            )

    if maccrobat_mencoes.is_file() and caminho_divisoes.is_file():
        macc_teste_ids = {
            r["case_id"]
            for r in carregar_divisoes(caminho_divisoes)
            if r["fonte"] == "maccrobat" and r["particao"] == "teste"
        }
        if macc_teste_ids:
            macc_m = _ler_mencoes(maccrobat_mencoes)
            for sis in sistemas:
                linhas.extend(
                    _avaliar_par(
                        conjunto="maccrobat_teste",
                        sistema=sis,
                        gold_mencoes=macc_m,
                        casos_alvo=macc_teste_ids,
                        gold_relacoes=None,
                        avaliar_polaridade=True,
                    )
                )

    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUNAS_EXTRACAO)
        writer.writeheader()
        writer.writerows(linhas)
    return linhas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    p_av = sub.add_parser("avaliar", help="Gera project3/data/resultados/extracao.csv.")
    p_av.add_argument("--gold-mencoes", type=Path, default=GOLD_MENCOES_PADRAO)
    p_av.add_argument("--gold-relacoes", type=Path, default=GOLD_RELACOES_PADRAO)
    p_av.add_argument("--maccrobat-mencoes", type=Path, default=MACCROBAT_MENCOES_PADRAO)
    p_av.add_argument("--divisoes", type=Path, default=DIVISOES_PADRAO)
    p_av.add_argument("--saida", type=Path, default=SAIDA_PADRAO)

    args = parser.parse_args()
    if args.comando == "avaliar":
        linhas = avaliar_extracao(
            gold_mencoes=args.gold_mencoes,
            gold_relacoes=args.gold_relacoes,
            maccrobat_mencoes=args.maccrobat_mencoes,
            caminho_divisoes=args.divisoes,
            saida=args.saida,
        )
        print(json.dumps({
            "saida": str(args.saida),
            "linhas": len(linhas),
            "sistemas_avaliados": sorted({(l["conjunto"], l["sistema"]) for l in linhas}),
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
