"""Etapa 3 (Frente B): o "aluno", um CRF treinado com as menções do professor (destilação).

    python -m project3.src.aluno.aluno treinar [--fracao 1.0]
    python -m project3.src.aluno.aluno prever [--particoes teste validacao | --todos] [--corpus CSV]
    python -m project3.src.aluno.aluno curva

Mesmo CRF e mesmas pistas por palavra do P2 (`project2/src/entidades`). Duas diferenças:
1. Aprende com os rótulos do LLM, e não com as regras do P1.
2. O rótulo de cada palavra carrega tipo e polaridade (`B-Symptom-absent`), então o aluno sozinho
   gera o contrato completo de menções tipadas, sem as etapas 3 e 4 do P2.
"""
from __future__ import annotations

import argparse
import csv
import json
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

import sklearn_crfsuite

from project2.src.comum import CASOS_PADRAO, iter_casos
from project2.src.entidades.entidades import achatar, frases_do_caso, pistas_da_palavra
from project3.src.professor.divisoes import garantir_fora_do_teste, ler_divisoes
from project3.src.professor.professor import (COLUNAS, RESULTADOS, gravar_csv, ler_csv, medir,
                                              ordem_fixa, validar_contrato)

REPO = Path(__file__).resolve().parents[3]
PROFESSOR = REPO / "project3/data/interim/professor/mencoes_tipadas.csv"
MODELOS = REPO / "project3/models/aluno"
SAIDA = REPO / "project3/data/interim/aluno/mencoes_tipadas.csv"
VERSAO = "crf-v1"
# Fixos (os do meio da grade do P2): ajustá-los na validação inflaria a curva medida nela mesma.
C1, C2 = 0.1, 0.05
FRACOES = (0.10, 0.25, 0.50, 1.00)


# ============================================================ rótulos tipados ==
def rotular(frase: list[dict], mencoes: list[dict]) -> list[str]:
    """B/I/O por palavra, com tipo e polaridade: B-Finding-present, I-Finding-present, O.

    O BIO é plano: entre menções sobrepostas fica a mais longa (mesma regra do P2).
    """
    por_span = {(int(m["start"]), int(m["end"])): f'{m["tipo"]}-{m["polaridade"] or "present"}' for m in mencoes}
    rotulos = ["O"] * len(frase)
    for inicio, fim in achatar(list(por_span)):
        dentro = [k for k, t in enumerate(frase) if t["start"] < fim and inicio < t["end"]]
        for posicao, k in enumerate(dentro):
            rotulos[k] = ("B-" if posicao == 0 else "I-") + por_span[(inicio, fim)]
    return rotulos


def spans(frase: list[dict], rotulos: list[str], probs: list[float] | None = None) -> list[dict]:
    """Inverso de `rotular`. Um I- que não continua a menção aberta (outro tipo) abre uma nova."""
    saida, aberto = [], None
    for k, (tok, rotulo) in enumerate(zip(frase, rotulos)):
        classe = rotulo[2:]
        if rotulo == "O" or rotulo.startswith("B-") or (aberto and aberto["classe"] != classe):
            if aberto:
                saida.append(aberto)
            aberto = None
        if rotulo != "O":
            if aberto is None:
                aberto = {"start": tok["start"], "end": tok["end"], "classe": classe, "probs": []}
            aberto["end"] = tok["end"]
            aberto["probs"].append(probs[k] if probs else 1.0)
    if aberto:
        saida.append(aberto)
    for s in saida:
        s["tipo"], s["polaridade"] = s.pop("classe").rsplit("-", 1)
        p = s.pop("probs")
        s["confianca"] = round(sum(p) / len(p), 4)
    return saida


def exemplos(casos: list[tuple[str, str]], mencoes: dict[str, list[dict]]):
    X, y = [], []
    for case_id, texto in casos:
        for frase in frases_do_caso(texto):
            X.append([pistas_da_palavra(frase, i) for i in range(len(frase))])
            y.append(rotular(frase, mencoes.get(case_id, [])))
    return X, y


# ========================================================= treino e predição ==
def mencoes_por_caso(caminho: Path) -> dict[str, list[dict]]:
    por_caso = defaultdict(list)
    for linha in ler_csv(caminho):
        por_caso[linha["case_id"]].append(linha)
    return por_caso


def casos_de_treino(particoes: dict[str, str], mencoes: dict, fracao: float = 1.0) -> list[str]:
    """Casos de `treino` com rótulo do professor. Frações menores são prefixos da mesma ordem fixa,
    então o conjunto de 10% está contido no de 25%, que está contido no de 50%."""
    todos = [c for c in ordem_fixa(mencoes) if particoes.get(c) == "treino"]
    escolhidos = todos[:max(1, round(len(todos) * fracao))] if todos else []
    garantir_fora_do_teste(escolhidos, particoes)
    return escolhidos


def treinar(casos: list[tuple[str, str]], mencoes: dict[str, list[dict]]) -> sklearn_crfsuite.CRF:
    X, y = exemplos(casos, mencoes)
    crf = sklearn_crfsuite.CRF(algorithm="lbfgs", c1=C1, c2=C2, max_iterations=200,
                               all_possible_transitions=True)
    crf.fit(X, y)
    return crf


def prever_caso(crf, case_id: str, texto: str) -> list[dict]:
    frases = frases_do_caso(texto)
    X = [[pistas_da_palavra(f, i) for i in range(len(f))] for f in frases]
    achadas = []
    for frase, rotulos, marginais in zip(frases, crf.predict(X), crf.predict_marginals(X)):
        # Confiança: média, nas palavras da menção, da probabilidade do rótulo escolhido.
        probs = [m[r] for m, r in zip(marginais, rotulos)]
        achadas += spans(frase, rotulos, probs)
    return [{"case_id": case_id, "id": f"a{n}", "start": s["start"], "end": s["end"],
             "texto": texto[s["start"]:s["end"]], "tipo": s["tipo"], "mesh": "", "polaridade": s["polaridade"],
             "confianca": s["confianca"], "fonte": f"aluno:{VERSAO}"}
            for n, s in enumerate(sorted(achadas, key=lambda s: (s["start"], s["end"])), 1)]


def salvar(crf, info: dict) -> None:
    MODELOS.mkdir(parents=True, exist_ok=True)
    with open(MODELOS / "crf.pkl", "wb") as handle:
        pickle.dump(crf, handle)
    (MODELOS / "metadados.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def carregar():
    caminho = MODELOS / "crf.pkl"
    if not caminho.is_file():
        raise FileNotFoundError(f"{caminho} não existe: rode `treinar` antes")
    with open(caminho, "rb") as handle:
        return pickle.load(handle)


# ================================================================== comandos ==
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=CASOS_PADRAO)
    parser.add_argument("--professor", type=Path, default=PROFESSOR, help="menções do LLM")
    sub = parser.add_subparsers(dest="comando", required=True)
    p_treinar = sub.add_parser("treinar", help="treina com as menções do professor em treino")
    p_treinar.add_argument("--fracao", type=float, default=1.0)
    p_prever = sub.add_parser("prever", help="gera aluno/mencoes_tipadas.csv")
    grupo = p_prever.add_mutually_exclusive_group()
    grupo.add_argument("--particoes", nargs="+", default=["teste", "validacao"])
    grupo.add_argument("--todos", action="store_true", help="todos os casos do corpus")
    p_prever.add_argument("--saida", type=Path, default=SAIDA)
    sub.add_parser("curva", help="F1 na validação com 10/25/50/100%% dos rótulos")
    args = parser.parse_args()

    particoes = ler_divisoes(corpus=args.corpus)

    if args.comando == "prever":
        crf = carregar()
        linhas, n = [], 0
        for case_id, texto in iter_casos(args.corpus):
            if args.todos or particoes.get(case_id) in args.particoes:
                achadas = prever_caso(crf, case_id, texto)
                validar_contrato(case_id, texto, achadas)
                linhas += achadas
                n += 1
        gravar_csv(args.saida, COLUNAS, linhas)
        print(f"{args.saida}: {n} casos, {len(linhas)} menções")
        return

    mencoes = mencoes_por_caso(args.professor)
    textos = dict(iter_casos(args.corpus))
    if args.comando == "treinar":
        ids = casos_de_treino(particoes, mencoes, args.fracao)
        inicio = time.perf_counter()
        crf = treinar([(c, textos[c]) for c in ids], mencoes)
        info = {"versao": VERSAO, "casos_treino": len(ids), "fracao": args.fracao, "c1": C1, "c2": C2,
                "rotulos": sorted(crf.classes_), "segundos_treino": round(time.perf_counter() - inicio, 1)}
        salvar(crf, info)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return

    validacao = [c for c in ordem_fixa(mencoes) if particoes.get(c) == "validacao"]
    if not validacao:
        sys.exit("Sem menções do professor na validação: rode `professor rodar --particoes validacao` antes")
    gold = [m for c in validacao for m in mencoes[c]]
    linhas = []
    for fracao in FRACOES:
        ids = casos_de_treino(particoes, mencoes, fracao)
        crf = treinar([(c, textos[c]) for c in ids], mencoes)
        pred = [m for c in validacao for m in prever_caso(crf, c, textos[c])]
        linhas.append({"fracao": fracao, "casos_treino": len(ids), "casos_validacao": len(validacao),
                       **medir(pred, gold)})
        print(linhas[-1])
    gravar_csv(RESULTADOS / "curva_aluno.csv", list(linhas[0]), linhas)


if __name__ == "__main__":
    main()
