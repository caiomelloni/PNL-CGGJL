from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from time import perf_counter

if __package__:
    from .combinado import ROOT, ResultadoCaso, carregar_recursos, processar_caso, validar_grafo
else:
    from combinado import ROOT, ResultadoCaso, carregar_recursos, processar_caso, validar_grafo
from normalizacao.case_reader import case_from_row


LOGGER = logging.getLogger(__name__)
COLUNAS_RESUMO = [
    "case_id", "status", "nos", "arestas", "evidencias_desalinhadas",
    "arestas_fora_do_dominio", "tempo_s", "erro",
]
COLUNAS_ENTRADA = {"article_id", "age", "case_id", "case_text", "gender"}


def exportar_caso(resultado: ResultadoCaso, case_id: str, saida: Path) -> None:
    """Serializa ambos os arquivos antes de publicar cada CSV por substituição."""
    temporarios = []
    try:
        for sufixo, tabela in (("nodes", resultado.nos), ("edges", resultado.arestas)):
            destino = saida / f"{case_id}-{sufixo}.csv"
            with tempfile.NamedTemporaryFile(dir=saida, suffix=".tmp", delete=False) as handle:
                temporario = Path(handle.name)
            temporarios.append((temporario, destino))
            tabela.to_csv(temporario, index=False, encoding="utf-8")
        for temporario, destino in temporarios:
            os.replace(temporario, destino)
    finally:
        for temporario, _ in temporarios:
            temporario.unlink(missing_ok=True)


def gravar_resumo(linhas: list[dict], saida: Path) -> None:
    """Mantém o último resumo completo se a gravação seguinte falhar."""
    caminho = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=saida, suffix=".tmp", delete=False
        ) as handle:
            caminho = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=COLUNAS_RESUMO)
            writer.writeheader()
            writer.writerows(linhas)
        os.replace(caminho, saida / "_resumo.csv")
    finally:
        if caminho is not None:
            caminho.unlink(missing_ok=True)


def executar_lote(
    cases_csv: str | Path = ROOT / "sample" / "cases.csv",
    output: str | Path = ROOT / "data" / "processed",
    case_ids: list[str] | None = None,
) -> list[dict]:
    """Processa casos na ordem do CSV; falhas de uma linha não abortam as demais.

    Arquivo/cabeçalho inválido, recursos indisponíveis e falha ao gravar o resumo
    são erros globais. O resumo representa apenas esta execução; CSVs de casos
    fora da seleção e saídas antigas de casos que falharam permanecem no disco.
    """
    with Path(cases_csv).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        faltantes = COLUNAS_ENTRADA - set(reader.fieldnames or ())
        if faltantes:
            raise ValueError(f"CSV sem colunas obrigatórias: {', '.join(sorted(faltantes))}")
        linhas = list(reader)

    ids = [(linha.get("case_id") or "").strip() for linha in linhas]
    ocorrencias = Counter(ids)
    selecao = None if case_ids is None else set(case_ids)
    selecionadas = [(cid, linha) for cid, linha in zip(ids, linhas)
                    if selecao is None or cid in selecao]
    ausentes = sorted((selecao or set()) - set(ids))
    recursos = carregar_recursos() if selecionadas else None
    saida = Path(output)
    saida.mkdir(parents=True, exist_ok=True)
    resumo = []
    gravar_resumo(resumo, saida)

    for cid, linha in selecionadas:
        inicio = perf_counter()
        registro = dict.fromkeys(COLUNAS_RESUMO, "")
        registro.update(case_id=cid, status="erro")
        try:
            # Além de rejeitar IDs inválidos, impede caminhos arbitrários na saída.
            if not re.fullmatch(r"PMC\d+_\d{2}", cid):
                raise ValueError(f"case_id inválido: {cid!r}")
            if ocorrencias[cid] != 1:
                raise ValueError(f"case_id duplicado no CSV: {cid}")
            if None in linha or any(linha.get(coluna) is None for coluna in COLUNAS_ENTRADA):
                raise ValueError("Linha com quantidade incorreta de campos")
            caso = case_from_row(linha)
            resultado = processar_caso(caso, recursos)
            validacao = validar_grafo(caso, resultado)
            registro.update(
                nos=len(resultado.nos), arestas=len(resultado.arestas),
                evidencias_desalinhadas=len(validacao.evidencias_desalinhadas),
                arestas_fora_do_dominio=len(validacao.arestas_fora_do_dominio),
            )
            exportar_caso(resultado, cid, saida)
            registro["status"] = (
                "com_inconsistencias" if validacao.evidencias_desalinhadas
                or validacao.arestas_fora_do_dominio else "ok"
            )
        except Exception as error:
            registro["erro"] = f"{type(error).__name__}: {error}"
            LOGGER.exception("Falha no caso %s", cid)
        registro["tempo_s"] = f"{perf_counter() - inicio:.6f}"
        resumo.append(registro)
        gravar_resumo(resumo, saida)
        LOGGER.info("%s: %s (%ss)", cid, registro["status"], registro["tempo_s"])

    for cid in ausentes:
        registro = dict.fromkeys(COLUNAS_RESUMO, "")
        registro.update(case_id=cid, status="erro", tempo_s="0.000000",
                        erro="LookupError: case_id não encontrado no CSV")
        resumo.append(registro)
    gravar_resumo(resumo, saida)
    return resumo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Executa o grafo combinado em lote.")
    parser.add_argument("--cases", type=Path, default=ROOT / "sample" / "cases.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed")
    parser.add_argument("--case-ids", nargs="+", help="IDs separados por espaço; padrão: todos")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        resumo = executar_lote(args.cases, args.output, args.case_ids)
    except Exception as error:
        LOGGER.error("Lote não concluído: %s: %s", type(error).__name__, error)
        return 2
    LOGGER.info("Resumo: %s; arquivo: %s", dict(Counter(r["status"] for r in resumo)),
                args.output / "_resumo.csv")
    return int(any(r["status"] != "ok" for r in resumo))


if __name__ == "__main__":
    raise SystemExit(main())
