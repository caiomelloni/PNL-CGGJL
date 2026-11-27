"""Etapa 2 (Frente B): o LLM "professor" extrai menções tipadas dos casos.

    python -m project3.src.professor.professor custo [--n 50]
    python -m project3.src.professor.professor rodar [--n-treino N] [--n-validacao N] [--variante direta|proposicoes]
    python -m project3.src.professor.professor comparar [--gold CSV_DE_VALIDACAO]   # direta × proposições
    python -m project3.src.professor.professor exemplos [--gold CSV_DE_VALIDACAO]   # zero-shot × few-shot

Cada caso é cortado em trechos de frases inteiras. Para cada trecho o LLM devolve JSON com
`texto, tipo, polaridade`; a ancoragem acha cada texto no trecho e descarta o que não existe
(alucinação). A variante `proposicoes` pede antes ao LLM que quebre o trecho em proposições simples
e as entrega junto com o trecho; as menções continuam sendo extraídas do texto original.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from project2.src.avaliacao import avaliar as avaliacao
from project2.src.comum import CASOS_PADRAO, dividir_frases, iter_casos
from project2.src.montagem.montagem import montar_caso
from project3.src.llm import RecusaLLM, chamar, ler_json
from project3.src.llm.cliente import modelo_padrao
from project3.src.professor.ancoragem import ancorar
from project3.src.professor.divisoes import garantir_fora_do_teste, ler_divisoes

REPO = Path(__file__).resolve().parents[3]
PROMPTS = Path(__file__).resolve().parent / "prompts"
SAIDA = REPO / "project3/data/interim/professor"
RESULTADOS = REPO / "project3/data/resultados"
MACCROBAT = REPO / "project3/data/interim/maccrobat"
COLUNAS = ["case_id", "id", "start", "end", "texto", "tipo", "mesh", "polaridade", "confianca", "fonte"]
COLUNAS_ALUCINACOES = ["case_id", "texto", "tipo", "motivo"]
MAX_TRECHO = 1200  # caracteres por chamada: ~3 trechos por caso da amostra


# ================================================================ arquivos CSV ==
def corpora_padrao() -> list[Path]:
    """A amostra do P1 e, se já convertido pela Frente A, o MACCROBAT (que traz validação anotada)."""
    return [CASOS_PADRAO] + ([MACCROBAT / "casos.csv"] if (MACCROBAT / "casos.csv").is_file() else [])


def iter_corpora(corpora: list[Path]):
    """(case_id, texto) de vários arquivos de casos, na ordem dada."""
    for corpus in corpora:
        yield from iter_casos(corpus)


def ler_csv(caminho: Path) -> list[dict]:
    with open(caminho, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def gravar_csv(caminho: Path, colunas: list[str], linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as handle:
        escritor = csv.DictWriter(handle, fieldnames=colunas, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(linhas)


def medir(pred: list[dict], gold: list[dict]) -> dict:
    """F1 de fronteira (exato e sobreposição) e acerto de tipo/polaridade, com a avaliação do P2."""
    spans = lambda linhas: [(l["case_id"], int(l["start"]), int(l["end"])) for l in linhas]  # noqa: E731
    fronteira = avaliacao.avaliar_mencoes(spans(pred), spans(gold))
    tipos = avaliacao.avaliar_tipos(pred, gold, exato=False)
    return {"f1_exato": round(fronteira["exato"]["f1"], 4),
            "f1_sobreposicao": round(fronteira["sobreposicao"]["f1"], 4),
            "acuracia_tipo": round(tipos["acuracia"], 4), "macro_f1_tipo": round(tipos["macro_f1"], 4),
            "f1_absent": round(tipos["f1_absent"], 4)}


# ==================================================================== prompts ==
def trechos(texto: str, maximo: int | None = None) -> list[tuple[int, int]]:
    """Frases consecutivas agrupadas até `maximo` caracteres; uma frase nunca é cortada."""
    maximo = maximo or MAX_TRECHO
    blocos, atual = [], None
    for frase in dividir_frases(texto):
        if atual and frase.end - atual[0] <= maximo:
            atual[1] = frase.end
        else:
            if atual:
                blocos.append(tuple(atual))
            atual = [frase.start, frase.end]
    if atual:
        blocos.append(tuple(atual))
    return blocos


def pergunta(trecho: str, proposicoes: list[str] | None = None) -> str:
    texto = f"Passage:\n<<<\n{trecho}\n>>>"
    if proposicoes:
        lista = "\n".join(f"- {p}" for p in proposicoes)
        texto += ("\n\nThe same passage as simple propositions (to help you read it; copy mentions "
                  f"only from the passage above):\n{lista}")
    return texto


def escolher_exemplos(mencoes: Path, casos: Path, particoes: dict[str, str], k: int = 3) -> list[tuple[str, list]]:
    """k trechos de casos de `treino`, cada um com ≥ 4 menções de ≥ 3 tipos (os mais variados)."""
    por_caso = defaultdict(list)
    for l in ler_csv(mencoes):
        if particoes.get(l["case_id"]) == "treino":
            por_caso[l["case_id"]].append(l)
    candidatos = []
    for case_id, texto in iter_casos(casos):
        if case_id not in por_caso:
            continue
        for inicio, fim in trechos(texto):
            dentro = sorted((m for m in por_caso[case_id] if inicio <= int(m["start"]) and int(m["end"]) <= fim),
                            key=lambda m: (int(m["start"]), int(m["end"])))
            n_tipos = len({m["tipo"] for m in dentro})
            if len(dentro) >= 4 and n_tipos >= 3:
                itens = [{"texto": m["texto"], "tipo": m["tipo"], "polaridade": (m.get("polaridade") or "present")}
                         for m in dentro]
                candidatos.append((-n_tipos, case_id, inicio, texto[inicio:fim], itens))
    escolhidos, casos_usados = [], set()
    for _, case_id, _, trecho, itens in sorted(candidatos):
        if case_id not in casos_usados and len(escolhidos) < k:
            escolhidos.append((trecho, itens))
            casos_usados.add(case_id)
    garantir_fora_do_teste(casos_usados, particoes)
    return escolhidos


def montar_sistema(exemplos: list[tuple[str, list]]) -> str:
    modelo = (PROMPTS / "extracao.md").read_text(encoding="utf-8")
    blocos = [f"{pergunta(trecho)}\nAnswer:\n{json.dumps({'mencoes': itens}, ensure_ascii=False)}"
              for trecho, itens in exemplos]
    texto = "## Examples\n\n" + "\n\n".join(blocos) if blocos else ""
    return modelo.replace("{exemplos}", texto).strip()


def sistema_padrao(particoes: dict[str, str], exemplos: str | None) -> str:
    """Zero-shot por padrão; `--exemplos maccrobat` ou `--exemplos <csv de menções da amostra>` liga o few-shot.

    Nenhuma fonte de exemplos é o padrão: o silver do P2 vem das regras do P1 (poucas menções,
    fronteiras ruins) e o MACCROBAT segue outra convenção ("abdominal pain" vira sítio + sintoma,
    sem Finding), que contradiz o guia do P2. Usar exemplos é um experimento, não um padrão.
    """
    if not exemplos or exemplos == "nenhum":
        return montar_sistema([])
    if exemplos == "maccrobat":
        mencoes, casos = MACCROBAT / "mencoes.csv", MACCROBAT / "casos.csv"
    else:
        mencoes, casos = Path(exemplos), CASOS_PADRAO
    escolhidos = escolher_exemplos(mencoes, casos, particoes)
    if escolhidos and all(m["polaridade"] == "present" for _, itens in escolhidos for m in itens):
        print("aviso: nenhum exemplo tem polaridade absent; a fonte pode não anotar negação", file=sys.stderr)
    return montar_sistema(escolhidos)


# ================================================================== extração ==
def extrair_caso(case_id: str, texto: str, sistema: str, variante: str = "direta",
                 modelo: str | None = None, provedor=None) -> tuple[list[dict], list[dict], dict]:
    """Menções no contrato, alucinações e estatísticas (chamadas, tokens, tempo, custo)."""
    mencoes, alucinacoes = [], []
    stats = defaultdict(float)
    modelo_usado = modelo
    for inicio, fim in trechos(texto):
        try:
            proposicoes = None
            if variante == "proposicoes":
                r = chamar(texto[inicio:fim], sistema=(PROMPTS / "proposicoes.md").read_text(encoding="utf-8"),
                           modelo=modelo, json=True, provedor=provedor)
                _somar(stats, r)
                proposicoes = [str(p) for p in ler_json(r.texto).get("proposicoes", [])]
            r = chamar(pergunta(texto[inicio:fim], proposicoes), sistema=sistema, modelo=modelo,
                       json=True, provedor=provedor)
            _somar(stats, r)
            modelo_usado = r.modelo
            dados = ler_json(r.texto)
            if "mencoes" not in dados:
                raise ValueError("resposta sem a chave mencoes")
            itens = dados["mencoes"]
        except (RecusaLLM, ValueError, AttributeError) as erro:  # JSON inválido também cai aqui
            stats["respostas_invalidas"] += 1
            print(f"aviso: {case_id} [{inicio}:{fim}] sem resposta válida: {erro}", file=sys.stderr)
            continue
        achadas, perdidas = ancorar(texto, inicio, fim, itens if isinstance(itens, list) else [])
        mencoes += achadas
        alucinacoes += [{"case_id": case_id, **a} for a in perdidas]
    linhas = []
    for n, m in enumerate(sorted(mencoes, key=lambda m: (m["start"], m["end"], m["tipo"])), 1):
        linhas.append({"case_id": case_id, "id": f"m{n}", "start": m["start"], "end": m["end"],
                       "texto": m["texto"], "tipo": m["tipo"], "mesh": "", "polaridade": m["polaridade"],
                       "confianca": "", "fonte": f"llm:{modelo_usado}"})
    stats.update(mencoes=len(linhas), alucinacoes=sum(a["motivo"] == "nao_encontrado" for a in alucinacoes))
    return linhas, alucinacoes, dict(stats)


def _somar(stats: dict, r) -> None:
    stats["chamadas"] += 1
    stats["chamadas_novas"] += not r.do_cache
    stats["tokens_entrada"] += r.tokens_entrada
    stats["tokens_saida"] += r.tokens_saida
    stats["segundos"] += r.segundos
    stats["custo_usd"] += r.custo_usd


def validar_contrato(case_id: str, texto: str, linhas: list[dict]) -> None:
    """Passa as menções pela montagem do P2, que falha se o contrato não for cumprido."""
    montar_caso(case_id, texto, linhas, [])


# ================================================================== comandos ==
def ordem_fixa(case_ids) -> list[str]:
    """Ordem pseudoaleatória mas fixa: os primeiros N casos são sempre os mesmos."""
    return sorted(case_ids, key=lambda c: hashlib.sha256(c.encode()).hexdigest())


def selecionar(particoes: dict[str, str], alvo: list[str], n_treino: int,
               disponiveis: set[str] | None = None, limites: dict[str, int] | None = None) -> list[str]:
    """Casos das partições `alvo` (cada uma até `limites[p]`) e mais `n_treino` casos de treino.

    Só entra caso presente nos corpora carregados (`disponiveis`): o divisoes.csv cobre o MultiCaRe
    inteiro, mas o professor só roda nos textos que recebeu.
    """
    limites = limites or {}
    ordem = [c for c in ordem_fixa(particoes) if disponiveis is None or c in disponiveis]
    escolhidos = []
    for particao in alvo:
        escolhidos += [c for c in ordem if particoes[c] == particao][:limites.get(particao)]
    treino = [c for c in ordem if particoes[c] == "treino"][:n_treino]
    return list(dict.fromkeys(escolhidos + treino))


def rodar(case_ids: list[str], corpora: list[Path], particoes: dict[str, str], sistema: str,
          variante: str = "direta", saida: Path = SAIDA, modelo: str | None = None) -> list[dict]:
    alvo = set(case_ids)
    textos = {c: t for c, t in iter_corpora(corpora) if c in alvo}
    todas, perdidas, execucao = [], [], []
    for k, case_id in enumerate(case_ids, 1):
        linhas, alucinacoes, stats = extrair_caso(case_id, textos[case_id], sistema, variante, modelo)
        validar_contrato(case_id, textos[case_id], linhas)
        todas += linhas
        perdidas += alucinacoes
        execucao.append({"case_id": case_id, "particao": particoes[case_id], "variante": variante, **stats})
        if k % 10 == 0 or k == len(case_ids):
            gasto = sum(e.get("custo_usd", 0) for e in execucao)
            print(f"{k}/{len(case_ids)} casos, US$ {gasto:.2f}", file=sys.stderr)
    gravar_csv(saida / "mencoes_tipadas.csv", COLUNAS, todas)
    gravar_csv(saida / "alucinacoes.csv", COLUNAS_ALUCINACOES, perdidas)
    gravar_csv(saida / "execucao.csv", ["case_id", "particao", "variante", "chamadas", "chamadas_novas",
                                        "respostas_invalidas", "mencoes", "alucinacoes", "tokens_entrada",
                                        "tokens_saida", "segundos", "custo_usd"], execucao)
    return execucao


def resumir(execucao: list[dict]) -> dict:
    n = len(execucao) or 1
    soma = lambda campo: sum(float(e.get(campo, 0)) for e in execucao)  # noqa: E731
    mencoes = soma("mencoes")
    return {"casos": len(execucao), "chamadas": int(soma("chamadas")), "mencoes_por_caso": round(mencoes / n, 1),
            "taxa_alucinacao": round(soma("alucinacoes") / ((mencoes + soma("alucinacoes")) or 1), 4),
            "tokens_entrada_por_caso": round(soma("tokens_entrada") / n),
            "tokens_saida_por_caso": round(soma("tokens_saida") / n),
            "segundos_por_caso": round(soma("segundos") / n, 2),
            "custo_usd_por_caso": round(soma("custo_usd") / n, 5)}


def comparar_configs(configs: list[tuple[str, str, str]], eixo: str, casos: list[str], corpora: list[Path],
                     particoes: dict[str, str], gold_csv: Path | None, modelo: str | None, tabela: Path) -> list[dict]:
    """Roda cada configuração (nome, sistema, variante) nos casos de validação e grava uma linha por uma.

    Com `gold_csv`, mede F1 só nos casos de validação que têm gabarito: o teste e o gabarito do P2
    nunca servem para escolher configuração. Sem gabarito, a concordância com a primeira
    configuração ainda mostra o quanto as outras mudam.
    """
    gold = []
    if gold_csv:
        gold = [l for l in ler_csv(gold_csv) if particoes.get(l["case_id"]) == "validacao" and l["case_id"] in set(casos)]
    com_gold = {g["case_id"] for g in gold}
    linhas, referencia = [], None
    for nome, sistema, variante in configs:
        pasta = SAIDA / "comparacao" / nome
        linha = {eixo: nome, **resumir(rodar(casos, corpora, particoes, sistema, variante, pasta, modelo))}
        pred = ler_csv(pasta / "mencoes_tipadas.csv")
        if gold:
            linha.update({"casos_com_gold": len(com_gold),
                          **medir([m for m in pred if m["case_id"] in com_gold], gold)})
        if referencia is None:
            referencia = pred
        else:
            concordancia = medir(pred, referencia)
            linha.update({"concordancia_f1_exato": concordancia["f1_exato"],
                          "concordancia_tipo": concordancia["acuracia_tipo"]})
        linhas.append(linha)
    gravar_csv(tabela, list(linhas[-1]), linhas)
    return linhas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, nargs="+", default=None,
                        help="arquivos de casos (padrão: amostra do P1 + MACCROBAT, se convertido)")
    parser.add_argument("--modelo", help="padrão: P3_LLM_MODELO ou o do provedor")
    parser.add_argument("--exemplos", help='few-shot: "maccrobat" ou CSV de menções da amostra (padrão: nenhum)')
    sub = parser.add_subparsers(dest="comando", required=True)
    p_custo = sub.add_parser("custo", help="mede o custo nos primeiros casos de treino")
    p_custo.add_argument("--n", type=int, default=50)
    p_rodar = sub.add_parser("rodar", help="extrai teste, validação e N casos de treino")
    p_rodar.add_argument("--n-treino", type=int, default=0)
    p_rodar.add_argument("--n-validacao", type=int, help="limita os casos de validação (padrão: todos)")
    p_rodar.add_argument("--n-teste", type=int, help="limita os casos de teste (padrão: todos)")
    p_rodar.add_argument("--particoes", nargs="+", default=["teste", "validacao"])
    p_rodar.add_argument("--variante", choices=["direta", "proposicoes"], default="direta")
    p_comparar = sub.add_parser("comparar", help="direta × proposições na validação")
    p_comparar.add_argument("--gold", type=Path, help="menções anotadas de casos de validação")
    p_comparar.add_argument("--n", type=int, help="limita o número de casos de validação")
    p_exemplos = sub.add_parser("exemplos", help="zero-shot × few-shot do MACCROBAT na validação")
    p_exemplos.add_argument("--gold", type=Path, help="menções anotadas de casos de validação")
    p_exemplos.add_argument("--n", type=int, help="limita o número de casos de validação")
    args = parser.parse_args()

    corpora = args.corpus or corpora_padrao()
    particoes = ler_divisoes(corpus=corpora[0])
    disponiveis = {c for c, _ in iter_corpora(corpora)}
    sistema = sistema_padrao(particoes, args.exemplos)

    if args.comando == "custo":
        casos = selecionar(particoes, [], args.n, disponiveis)
        execucao = rodar(casos, corpora, particoes, sistema, saida=SAIDA / "custo", modelo=args.modelo)
        linha = {"modelo": args.modelo or modelo_padrao(), **resumir(execucao)}
        linha["custo_usd_1000_casos"] = round(linha["custo_usd_por_caso"] * 1000, 2)
        gravar_csv(RESULTADOS / "custo_professor.csv", list(linha), [linha])
        print(json.dumps(linha, ensure_ascii=False, indent=2))
    elif args.comando == "rodar":
        saida = SAIDA if args.variante == "direta" else SAIDA / "proposicoes"
        casos = selecionar(particoes, args.particoes, args.n_treino, disponiveis,
                           {"validacao": args.n_validacao, "teste": args.n_teste})
        print(json.dumps(resumir(rodar(casos, corpora, particoes, sistema, args.variante, saida,
                                       args.modelo)), ensure_ascii=False, indent=2))
    else:
        # comparar: direta × proposições; exemplos: zero-shot × few-shot do MACCROBAT (direta).
        casos = selecionar(particoes, ["validacao"], 0, disponiveis)[:args.n]
        if args.comando == "comparar":
            configs = [("direta", sistema, "direta"), ("proposicoes", sistema, "proposicoes")]
            eixo, tabela = "variante", "quebra_frases.csv"
        else:
            configs = [("zero_shot", montar_sistema([]), "direta"),
                       ("few_shot_maccrobat", sistema_padrao(particoes, "maccrobat"), "direta")]
            eixo, tabela = "exemplos", "few_shot.csv"
        print(json.dumps(comparar_configs(configs, eixo, casos, corpora, particoes, args.gold, args.modelo,
                                          RESULTADOS / tabela), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
