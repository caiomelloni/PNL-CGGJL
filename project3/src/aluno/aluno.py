"""Etapa 3 (Frente B): o "aluno", um CRF treinado com as menções do professor (destilação).

    python -m project3.src.aluno.aluno [--modelo crf|bert] treinar [--fracao 1.0]
    python -m project3.src.aluno.aluno [--modelo crf|bert] prever [--particoes teste validacao | --todos]
    python -m project3.src.aluno.aluno [--modelo crf|bert] curva

Dois modelos com a mesma rotulagem: o CRF e as pistas por palavra do P2 (`project2/src/entidades`)
e um BERT biomédico (`bert.py`). Em relação ao P2:
1. Aprendem com os rótulos do LLM, e não com as regras do P1.
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


from project2.src.entidades.entidades import achatar, frases_do_caso, pistas_da_palavra
from project3.src.professor.divisoes import garantir_fora_do_teste, ler_divisoes
from project3.src.professor.professor import (COLUNAS, RESULTADOS, corpora_padrao, gravar_csv, iter_corpora,
                                              ler_csv, medir, ordem_fixa, validar_contrato)

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


def linhas_do_caso(case_id: str, texto: str, achadas: list[dict], versao: str) -> list[dict]:
    """Spans previstos -> linhas no contrato de menções tipadas."""
    return [{"case_id": case_id, "id": f"a{n}", "start": s["start"], "end": s["end"],
             "texto": texto[s["start"]:s["end"]], "tipo": s["tipo"], "mesh": "", "polaridade": s["polaridade"],
             "confianca": s["confianca"], "fonte": f"aluno:{versao}"}
            for n, s in enumerate(sorted(achadas, key=lambda s: (s["start"], s["end"])), 1)]


def prever_caso(crf, case_id: str, texto: str) -> list[dict]:
    frases = frases_do_caso(texto)
    X = [[pistas_da_palavra(f, i) for i in range(len(f))] for f in frases]
    achadas = []
    for frase, rotulos, marginais in zip(frases, crf.predict(X), crf.predict_marginals(X)):
        # Confiança: média, nas palavras da menção, da probabilidade do rótulo escolhido.
        probs = [m[r] for m, r in zip(marginais, rotulos)]
        achadas += spans(frase, rotulos, probs)
    return linhas_do_caso(case_id, texto, achadas, VERSAO)


def descrever(crf) -> dict:
    return {"versao": VERSAO, "c1": C1, "c2": C2, "rotulos": len(crf.classes_)}


def salvar(crf, pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    with open(pasta / "crf.pkl", "wb") as handle:
        pickle.dump(crf, handle)


def carregar(pasta: Path):
    caminho = pasta / "crf.pkl"
    if not caminho.is_file():
        raise FileNotFoundError(f"{caminho} não existe: rode `treinar` antes")
    with open(caminho, "rb") as handle:
        return pickle.load(handle)


def modelo_aluno(nome: str):
    """O módulo com treinar/prever_caso/descrever/salvar/carregar do modelo pedido."""
    if nome == "bert":
        from project3.src.aluno import bert  # torch e transformers só para quem usa o BERT
        return bert
    return sys.modules[__name__]


# ================================================================== comandos ==
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, nargs="+", default=None,
                        help="arquivos de casos (padrão: amostra do P1 + MACCROBAT, se convertido)")
    parser.add_argument("--professor", type=Path, default=PROFESSOR, help="menções do LLM")
    parser.add_argument("--modelo", choices=["crf", "bert"], default="bert",
                        help="bert (padrão, melhor na validação) ou crf (sem torch)")
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

    corpora = args.corpus or corpora_padrao()
    particoes = ler_divisoes(corpus=corpora[0])
    backend, pasta = modelo_aluno(args.modelo), MODELOS / args.modelo

    if args.comando == "prever":
        modelo = backend.carregar(pasta)
        linhas, n, inicio = [], 0, time.perf_counter()
        for case_id, texto in iter_corpora(corpora):
            if args.todos or particoes.get(case_id) in args.particoes:
                achadas = backend.prever_caso(modelo, case_id, texto)
                validar_contrato(case_id, texto, achadas)
                linhas += achadas
                n += 1
        gravar_csv(args.saida, COLUNAS, linhas)
        # Telemetria lida pela avaliação da Frente A (segundos_por_caso, custo_usd_por_caso).
        segundos = time.perf_counter() - inicio
        resumo = {"modelo": args.modelo, "casos": n, "mencoes": len(linhas), "segundos": round(segundos, 2),
                  "segundos_por_caso": round(segundos / (n or 1), 4), "custo_usd_por_caso": 0.0}
        (args.saida.parent / "resumo.json").write_text(json.dumps(resumo, indent=2) + "\n", encoding="utf-8")
        print(f"{args.saida}: {n} casos, {len(linhas)} menções")
        return

    mencoes = mencoes_por_caso(args.professor)
    textos = dict(iter_corpora(corpora))
    if args.comando == "treinar":
        ids = casos_de_treino(particoes, mencoes, args.fracao)
        inicio = time.perf_counter()
        modelo = backend.treinar([(c, textos[c]) for c in ids], mencoes)
        info = {**backend.descrever(modelo), "casos_treino": len(ids), "fracao": args.fracao,
                "segundos_treino": round(time.perf_counter() - inicio, 1)}
        backend.salvar(modelo, pasta)
        (pasta / "metadados.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return

    validacao = [c for c in ordem_fixa(mencoes) if particoes.get(c) == "validacao"]
    if not validacao:
        sys.exit("Sem menções do professor na validação: rode `professor rodar --particoes validacao` antes")
    gold = [m for c in validacao for m in mencoes[c]]
    linhas = []
    for fracao in FRACOES:
        ids = casos_de_treino(particoes, mencoes, fracao)
        modelo = backend.treinar([(c, textos[c]) for c in ids], mencoes)
        pred = [m for c in validacao for m in backend.prever_caso(modelo, c, textos[c])]
        linhas.append({"modelo": args.modelo, "fracao": fracao, "casos_treino": len(ids), "casos_validacao": len(validacao),
                       **medir(pred, gold)})
        print(linhas[-1])
    # Uma tabela para os dois modelos: troca só as linhas do modelo que acabou de rodar.
    caminho = RESULTADOS / "curva_aluno.csv"
    outras = [l for l in ler_csv(caminho) if l.get("modelo", "crf") != args.modelo] if caminho.is_file() else []
    gravar_csv(caminho, list(linhas[0]), outras + linhas)


if __name__ == "__main__":
    main()
