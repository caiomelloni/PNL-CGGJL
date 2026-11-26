"""Exporta as predições para a avaliação da Frente C."""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from tempfile import NamedTemporaryFile

from project2.src.comum import casos_gold

from .dados import DIVISOES, GRAFOS, GRAFOS_P2, PREDICOES, artigo_do_caso, ler_divisoes
from .motor import SISTEMAS, Motor, Sugestao, cliente_llm, normalizador_mesh

COLUNAS = ("sistema", "case_id", "rank", "mesh", "rotulo", "score", "casos_fonte")


def linhas_predicoes(sistema: str, case_id: str, sugestoes: list[Sugestao]) -> Iterator[dict]:
    for rank, sugestao in enumerate(sugestoes, 1):
        yield dict(
            sistema=sistema, case_id=case_id, rank=rank, mesh=sugestao.mesh, rotulo=sugestao.rotulo,
            score=f"{sugestao.score:.8f}", casos_fonte=";".join(sugestao.casos_fonte),
        )


def predizer(
    motor: Motor, casos: set[str], sistemas: Iterable[str], limite_vizinhos: int = 5,
) -> Iterator[dict]:
    sistemas = tuple(sistemas)
    for case_id in sorted(casos):
        caso = motor.casos[case_id]
        for sistema in sistemas:
            analise = motor.analisar(
                list(caso.consulta), sistema=sistema, excluir_artigos={caso.article_id},
                limite_vizinhos=limite_vizinhos,
            )
            yield from linhas_predicoes(sistema, case_id, analise.sugestoes)


def exportar(saida: Path, predicoes: Iterable[dict]) -> Counter:
    """Substitui a saída somente depois que o lote termina com sucesso."""
    saida.parent.mkdir(parents=True, exist_ok=True)
    arquivo = NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=saida.parent, prefix=f".{saida.name}.", delete=False,
    )
    caminho = Path(arquivo.name)
    contagem = Counter()
    try:
        with arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS)
            escritor.writeheader()
            for linha in predicoes:
                escritor.writerow(linha)
                contagem[linha["sistema"]] += 1
        caminho.replace(saida)
    finally:
        caminho.unlink(missing_ok=True)
    return contagem


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grafos", type=Path, default=GRAFOS)
    parser.add_argument("--grafos-p2", type=Path, default=GRAFOS_P2)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--divisoes", type=Path, default=DIVISOES)
    parser.add_argument("--saida", type=Path, default=PREDICOES)
    parser.add_argument("--sistemas", choices=SISTEMAS, nargs="+", default=SISTEMAS)
    parser.add_argument("--modelo-embeddings", default=os.getenv("P3_DIAGNOSTICO_EMBEDDINGS"))
    parser.add_argument("--vizinhos", type=int, choices=range(1, 21), default=5, metavar="1..20")
    parser.add_argument("--aceitar-amostra", action="store_true", help="Permite fallback P2, gold do P2 e teste parcial.")
    args = parser.parse_args(argv)

    try:
        divisoes = ler_divisoes(args.divisoes)
        if not divisoes and not args.aceitar_amostra:
            raise ValueError("Faltam as divisões MultiCaRe da Frente A. Use --aceitar-amostra para o gold do P2.")
        teste = {linha["case_id"]: linha["article_id"] for linha in divisoes if linha["particao"] == "teste"}
        if not divisoes:
            teste = {case_id: artigo_do_caso(case_id) for case_id in casos_gold()}
        if not teste:
            raise ValueError("Nenhum caso MultiCaRe na partição de teste.")

        sistemas = tuple(dict.fromkeys(args.sistemas))
        motor = Motor(
            grafos=args.grafos, grafos_p2=args.grafos_p2, corpus=args.corpus, divisoes=args.divisoes,
            modelo_embeddings=args.modelo_embeddings, excluir_da_base=set(teste.values()),
        )
        if motor.usando_p2 and not args.aceitar_amostra:
            raise ValueError("Faltam os grafos do P3. Use --aceitar-amostra para rodar sobre os grafos do P2.")
        disponiveis = teste.keys() & motor.casos.keys()
        faltantes = teste.keys() - disponiveis
        if not disponiveis or (faltantes and not args.aceitar_amostra):
            raise ValueError(f"Faltam grafos para {len(faltantes)} de {len(teste)} casos de teste.")
        if any(s != "grafo" for s in sistemas):
            motor.chamar = cliente_llm()
            motor.normalizar = normalizador_mesh()

        if not divisoes or motor.usando_p2 or faltantes:
            print(f"Amostra de desenvolvimento: {len(disponiveis)}/{len(teste)} casos, base {'P2' if motor.usando_p2 else 'P3'}.", file=sys.stderr)
        if not args.modelo_embeddings:
            print("Busca textual com TF-IDF. Use --modelo-embeddings para vetores semânticos.", file=sys.stderr)

        contagem = exportar(args.saida, predizer(motor, disponiveis, sistemas, args.vizinhos))
    except (OSError, ValueError, RuntimeError, ImportError) as erro:
        parser.exit(1, f"{erro}\n")
    print(f"{len(disponiveis)} casos em {args.saida}")
    for sistema in sistemas:
        print(f"  {sistema}: {contagem[sistema]} sugestões")


if __name__ == "__main__":
    main()
