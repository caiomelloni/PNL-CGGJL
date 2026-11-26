"""Download e conversão do corpus MACCROBAT (formato brat) para o contrato do P2/P3."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen

from project2.src.comum import REPO

FIGSHARE_ARTICLE_ID = "9764942"
FIGSHARE_DOI = "10.6084/m9.figshare.9764942.v2"
FIGSHARE_LICENCA = "CC BY 4.0"
FIGSHARE_LICENCA_URL = "https://creativecommons.org/licenses/by/4.0/"
ARQUIVO_ZIP = "MACCROBAT2020.zip"
URL_DOWNLOAD = "https://ndownloader.figshare.com/files/21489405"
MD5_ESPERADO = "9d090f3e0719e77e7a33c38750548bb8"

TIPOS_VALIDOS = frozenset({
    "History",
    "Symptom",
    "Finding",
    "Exam",
    "ExamResult",
    "Diagnosis",
    "Treatment",
    "Medication",
    "AnatomicalSite",
    "Outcome",
})

COLUNAS_CASOS = ("article_id", "case_id", "case_text")
COLUNAS_MENCOES = (
    "case_id",
    "id",
    "start",
    "end",
    "texto",
    "tipo",
    "mesh",
    "polaridade",
    "confianca",
    "fonte",
)

MAPA_PADRAO = Path(__file__).resolve().parent / "mapa_maccrobat.csv"
EXTERNO_PADRAO = REPO / "project3/data/external/maccrobat"
SAIDA_PADRAO = REPO / "project3/data/interim/maccrobat"


def _md5(caminho: Path) -> str:
    digest = hashlib.md5()
    with caminho.open("rb") as handle:
        for bloco in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def baixar(destino: Path = EXTERNO_PADRAO) -> dict:
    """Baixa MACCROBAT2020.zip do Figshare, valida MD5, extrai e grava proveniência."""
    destino.mkdir(parents=True, exist_ok=True)
    zip_path = destino / ARQUIVO_ZIP
    if not zip_path.is_file() or _md5(zip_path) != MD5_ESPERADO:
        req = Request(URL_DOWNLOAD, headers={"User-Agent": "PNL-CGGJL-project3/1.0"})
        with urlopen(req, timeout=120) as resposta:
            zip_path.write_bytes(resposta.read())
        obtido = _md5(zip_path)
        if obtido != MD5_ESPERADO:
            raise ValueError(f"Checksum MD5 inválido para {zip_path}: {obtido} != {MD5_ESPERADO}")

    pasta_extraida = destino / "MACCROBAT2020"
    if not pasta_extraida.exists() or not any(pasta_extraida.rglob("*.ann")):
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(pasta_extraida)

    proveniencia = {
        "dataset": "MACCROBAT2020",
        "figshare_article_id": FIGSHARE_ARTICLE_ID,
        "doi": FIGSHARE_DOI,
        "licenca": FIGSHARE_LICENCA,
        "licenca_url": FIGSHARE_LICENCA_URL,
        "arquivo": ARQUIVO_ZIP,
        "md5": MD5_ESPERADO,
        "documentos_txt": len(list(pasta_extraida.rglob("*.txt"))),
        "documentos_ann": len(list(pasta_extraida.rglob("*.ann"))),
    }
    (destino / "proveniencia.json").write_text(
        json.dumps(proveniencia, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return proveniencia


def carregar_mapa(caminho_mapa: Path = MAPA_PADRAO) -> dict[str, str]:
    """Lê mapa_maccrobat.csv e retorna {tipo_maccrobat: tipo_p3} (vazio se descartado)."""
    mapa: dict[str, str] = {}
    with caminho_mapa.open(encoding="utf-8", newline="") as handle:
        for linha in csv.DictReader(handle):
            origem = linha["tipo_maccrobat"].strip()
            destino = linha["tipo_p3"].strip()
            if destino and destino not in TIPOS_VALIDOS:
                raise ValueError(f"Tipo de destino inválido no mapa: {destino!r} (para {origem!r})")
            mapa[origem] = destino
    return mapa


# Valores de POLARITY do MACCROBAT tratados como negação; os demais (POS, UNCERTAIN, MAYBE_POS) são present.
POLARIDADES_NEGADAS = frozenset({"NEG", "MAYBE_NEG"})


def ler_polaridades(linhas: list[str]) -> dict[str, str]:
    """{id do trecho T: "absent"} para os trechos negados de um .ann.

    No brat do MACCROBAT a negação fica num atributo do evento, não do trecho:
    `A1 POLARITY E10 NEG` -> `E10 Disease_disorder:T22` -> `T22 ... problems`.
    """
    gatilho: dict[str, str] = {}
    negados: set[str] = set()
    for linha in linhas:
        partes = linha.split("\t")
        if linha.startswith("E") and len(partes) >= 2 and ":" in partes[1]:
            gatilho[partes[0]] = partes[1].split()[0].split(":", 1)[1]
        elif linha.startswith("A") and len(partes) >= 2:
            campos = partes[1].split()
            if len(campos) == 3 and campos[0] == "POLARITY" and campos[2] in POLARIDADES_NEGADAS:
                negados.add(campos[1])
    # O atributo pode apontar para um evento (E) ou direto para o trecho (T).
    return {gatilho.get(alvo, alvo): "absent" for alvo in negados}


def converter(
    entrada: Path = EXTERNO_PADRAO / "MACCROBAT2020",
    saida: Path = SAIDA_PADRAO,
    caminho_mapa: Path = MAPA_PADRAO,
) -> dict:
    """Converte arquivos brat (.txt/.ann) para casos.csv e mencoes.csv no contrato do P2/P3."""
    mapa = carregar_mapa(caminho_mapa)
    arquivos_ann = sorted(entrada.rglob("*.ann"))
    if not arquivos_ann:
        raise FileNotFoundError(f"Nenhum arquivo .ann encontrado em {entrada}")

    saida.mkdir(parents=True, exist_ok=True)
    casos_csv = saida / "casos.csv"
    mencoes_csv = saida / "mencoes.csv"

    por_tipo: Counter[str] = Counter()
    por_polaridade: Counter[str] = Counter()
    tipos_nao_mapeados: Counter[str] = Counter()
    descartadas_mapa = 0
    descartadas_descontinuas = 0
    total_casos = 0
    total_mencoes = 0

    with (
        casos_csv.open("w", encoding="utf-8", newline="") as f_casos,
        mencoes_csv.open("w", encoding="utf-8", newline="") as f_mencoes,
    ):
        w_casos = csv.DictWriter(f_casos, fieldnames=COLUNAS_CASOS)
        w_mencoes = csv.DictWriter(f_mencoes, fieldnames=COLUNAS_MENCOES)
        w_casos.writeheader()
        w_mencoes.writeheader()

        for caminho_ann in arquivos_ann:
            caminho_txt = caminho_ann.with_suffix(".txt")
            if not caminho_txt.is_file():
                raise FileNotFoundError(f"Texto correspondente ausente: {caminho_txt}")

            doc_id = caminho_ann.stem
            case_text = caminho_txt.read_text(encoding="utf-8")
            w_casos.writerow({
                "article_id": doc_id,
                "case_id": doc_id,
                "case_text": case_text,
            })
            total_casos += 1

            linhas_ann = caminho_ann.read_text(encoding="utf-8").splitlines()
            polaridades = ler_polaridades(linhas_ann)
            mencoes_doc: list[tuple[int, int, str, str, str]] = []
            for linha in linhas_ann:
                if not linha.startswith("T"):
                    continue
                partes = linha.split("\t")
                if len(partes) < 3:
                    continue
                tipo_orig, spans = partes[1].split(" ", 1)
                texto_ann = partes[2]

                if tipo_orig not in mapa:
                    tipos_nao_mapeados[tipo_orig] += 1
                    continue
                tipo_p3 = mapa[tipo_orig]
                if not tipo_p3:
                    descartadas_mapa += 1
                    continue

                if ";" in spans:
                    descartadas_descontinuas += 1
                    continue

                start, end = (int(v) for v in spans.split())
                texto_real = case_text[start:end]
                if texto_real != texto_ann:
                    raise ValueError(
                        f"Offset incompatível em {doc_id} ({start}:{end}): "
                        f"esperado {texto_ann!r}, obtido {texto_real!r}"
                    )
                mencoes_doc.append((start, end, texto_real, tipo_p3, polaridades.get(partes[0], "present")))

            mencoes_doc.sort(key=lambda item: (item[0], item[1], item[3]))
            for indice, (start, end, texto_real, tipo_p3, polaridade) in enumerate(mencoes_doc, start=1):
                w_mencoes.writerow({
                    "case_id": doc_id,
                    "id": f"M{indice}",
                    "start": start,
                    "end": end,
                    "texto": texto_real,
                    "tipo": tipo_p3,
                    "mesh": "",
                    "polaridade": polaridade,
                    "confianca": "1.0",
                    "fonte": "maccrobat",
                })
                por_tipo[tipo_p3] += 1
                por_polaridade[polaridade] += 1
                total_mencoes += 1

    if tipos_nao_mapeados:
        raise ValueError(f"Tipos MACCROBAT ausentes em {caminho_mapa}: {dict(tipos_nao_mapeados)}")

    resumo = {
        "casos": total_casos,
        "mencoes_convertidas": total_mencoes,
        "descartadas_sem_equivalente": descartadas_mapa,
        "descartadas_descontinuas": descartadas_descontinuas,
        "por_tipo": dict(por_tipo.most_common()),
        "por_polaridade": dict(por_polaridade.most_common()),
        "observacao_finding": "MACCROBAT não separa Finding de Sign_symptom; Finding permanece com 0 ocorrências.",
    }
    (saida / "resumo.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return resumo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    p_baixar = sub.add_parser("baixar", help="Baixa e extrai o MACCROBAT2020 do Figshare.")
    p_baixar.add_argument("--destino", type=Path, default=EXTERNO_PADRAO)

    p_conv = sub.add_parser("converter", help="Converte brat (.txt/.ann) para o contrato do P2/P3.")
    p_conv.add_argument("--entrada", type=Path, default=EXTERNO_PADRAO / "MACCROBAT2020")
    p_conv.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    p_conv.add_argument("--mapa", type=Path, default=MAPA_PADRAO)

    p_tudo = sub.add_parser("tudo", help="Executa download e conversão em sequência.")
    p_tudo.add_argument("--destino", type=Path, default=EXTERNO_PADRAO)
    p_tudo.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    p_tudo.add_argument("--mapa", type=Path, default=MAPA_PADRAO)

    args = parser.parse_args()
    if args.comando == "baixar":
        print(json.dumps(baixar(args.destino), ensure_ascii=False, indent=2))
    elif args.comando == "converter":
        print(json.dumps(converter(args.entrada, args.saida, args.mapa), ensure_ascii=False, indent=2))
    elif args.comando == "tudo":
        prov = baixar(args.destino)
        res = converter(args.destino / "MACCROBAT2020", args.saida, args.mapa)
        print(json.dumps({"proveniencia": prov, "conversao": res}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
