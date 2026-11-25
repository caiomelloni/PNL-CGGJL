"""Normalização de menções clínicas para códigos MeSH por embeddings (Etapa 5, Frente C).

Cada termo dos gazetteers do projeto 1 (MeSH e sítios anatômicos) vira um vetor do SapBERT,
um BERT biomédico treinado para que sinônimos fiquem próximos. Uma menção recebe o código do
termo mais parecido (similaridade de cosseno).

    python -m project3.src.normalizacao.normalizacao indice
    python -m project3.src.normalizacao.normalizacao calibrar
    python -m project3.src.normalizacao.normalizacao csv --entrada <menções.csv> --saida <saída.csv>
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
GAZETTEERS = REPO / "project1" / "src" / "dicionarios" / "gazetteer"
ARQUIVOS_GAZETTEER = ("mesh_gazetteer.csv", "anatomical_site_gazetteer.csv")
INDICE = REPO / "project3" / "data" / "processed" / "indice_mesh"
MODELO = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
MAX_TOKENS = 25  # o SapBERT foi treinado com nomes curtos; o resto do texto é cortado
LOTE = 512
COLUNAS_TERMOS = ["term", "code", "preferred_term", "category"]
ARQUIVO_LIMIAR = Path(__file__).resolve().parent / "limiar.json"  # versionado; gerado por `calibrar`
CURVA = REPO / "project3" / "data" / "resultados" / "normalizacao_calibracao.csv"
LIMIAR_PADRAO = 0.8
# Padrão escolhido depois de ver o gold (data/resultados/normalizacao.csv): seleção declarada no README.
METODOS = ("lexico+sapbert", "sapbert")
METODO_PADRAO = "lexico+sapbert"
# Categorias do gazetteer que cada tipo pode receber com --filtrar-tipo (ver CATEGORIA_TIPO do P2).
# `drugs` entra em Exam porque os analitos (hemoglobin, troponin) estão na árvore D do MeSH.
CATEGORIAS_DO_TIPO = {
    "Medication": {"drugs"},
    "Diagnosis": {"diseases", "mental_disorders"},
    "Symptom": {"diseases", "mental_disorders"},
    "Finding": {"diseases", "mental_disorders"},
    "Exam": {"exams", "drugs"},
    "Treatment": {"treatments", "drugs"},
    "AnatomicalSite": {"anatomical_site"},
}


@dataclass(frozen=True)
class Vizinho:
    codigo: str
    termo: str
    preferido: str
    categoria: str
    score: float


def ler_termos(pasta: Path = GAZETTEERS) -> list[dict[str, str]]:
    """Linhas dos gazetteers sem repetir o par (termo em minúsculas, código)."""
    vistos, termos = set(), []
    for nome in ARQUIVOS_GAZETTEER:
        with (pasta / nome).open(encoding="utf-8", newline="") as f:
            for linha in csv.DictReader(f):
                chave = (linha["term"].strip().lower(), linha["code"])
                if chave[0] and chave not in vistos:
                    vistos.add(chave)
                    termos.append({c: linha[c] for c in COLUNAS_TERMOS})
    return termos


class Codificador:
    """Texto -> vetor unitário do SapBERT (token [CLS]). Usa a GPU quando houver."""

    def __init__(self, modelo: str = MODELO, dispositivo: str | None = None):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch = torch
        self.dispositivo = dispositivo or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizador = AutoTokenizer.from_pretrained(modelo)
        self.modelo = AutoModel.from_pretrained(modelo).to(self.dispositivo).eval()

    def codificar(self, textos: list[str], lote: int = LOTE) -> np.ndarray:
        saida = []
        with self.torch.inference_mode():
            for i in range(0, len(textos), lote):
                entrada = self.tokenizador(textos[i:i + lote], padding=True, truncation=True,
                                           max_length=MAX_TOKENS, return_tensors="pt").to(self.dispositivo)
                cls = self.modelo(**entrada).last_hidden_state[:, 0]
                saida.append(self.torch.nn.functional.normalize(cls, dim=1).float().cpu().numpy())
        return np.concatenate(saida) if saida else np.zeros((0, self.modelo.config.hidden_size), np.float32)


@lru_cache(maxsize=2)
def codificador(modelo: str = MODELO) -> Codificador:
    return Codificador(modelo)


def construir_indice(saida: Path = INDICE, modelo: str = MODELO) -> Path:
    """Codifica todos os termos e salva vetores.npy (float16), termos.csv e info.json."""
    termos = ler_termos()
    vetores = codificador(modelo).codificar([t["term"].lower() for t in termos])
    saida.mkdir(parents=True, exist_ok=True)
    np.save(saida / "vetores.npy", vetores.astype(np.float16))
    with (saida / "termos.csv").open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS_TERMOS)
        escritor.writeheader()
        escritor.writerows(termos)
    (saida / "info.json").write_text(json.dumps({"modelo": modelo, "termos": len(termos),
                                                 "dimensao": int(vetores.shape[1])}, indent=2))
    return saida


class Indice:
    """Vetores dos termos já carregados, com busca do vizinho mais próximo."""

    def __init__(self, pasta: Path = INDICE):
        if not (pasta / "vetores.npy").is_file():
            raise FileNotFoundError(f"{pasta} não tem índice: rode "
                                    "`python -m project3.src.normalizacao.normalizacao indice` antes")
        self.info = json.loads((pasta / "info.json").read_text())
        with (pasta / "termos.csv").open(encoding="utf-8", newline="") as f:
            self.termos = list(csv.DictReader(f))
        self.vetores = np.load(pasta / "vetores.npy").astype(np.float32)

    def buscar(self, consultas: np.ndarray, k: int = 1, mascara: np.ndarray | None = None) -> list[list[Vizinho]]:
        """Os k termos mais parecidos com cada vetor de consulta; `mascara` restringe os termos."""
        resultado = []
        for i in range(0, len(consultas), 1024):
            sims = consultas[i:i + 1024] @ self.vetores.T
            if mascara is not None:
                sims[:, ~mascara] = -np.inf
            melhores = np.argpartition(-sims, k - 1, axis=1)[:, :k] if k < sims.shape[1] else \
                np.tile(np.arange(sims.shape[1]), (len(sims), 1))
            for linha, idx in zip(sims, melhores):
                idx = idx[np.argsort(-linha[idx])]
                resultado.append([Vizinho(self.termos[j]["code"], self.termos[j]["term"],
                                          self.termos[j]["preferred_term"], self.termos[j]["category"],
                                          float(linha[j])) for j in idx if np.isfinite(linha[j])])
        return resultado


@lru_cache(maxsize=2)
def indice(pasta: Path = INDICE) -> Indice:
    return Indice(pasta)


def vizinhos(textos: list[str], k: int = 1, pasta: Path = INDICE) -> list[list[Vizinho]]:
    """Os k termos do índice mais parecidos com cada texto."""
    if not textos:
        return []
    idx = indice(pasta)
    return idx.buscar(codificador(idx.info["modelo"]).codificar([t.lower() for t in textos]), k)


def mascara_do_tipo(idx: Indice, tipo: str) -> np.ndarray | None:
    """Termos cujas categorias combinam com o tipo; None quando o tipo aceita qualquer categoria."""
    categorias = CATEGORIAS_DO_TIPO.get(tipo)
    if categorias is None:
        return None
    if not hasattr(idx, "_mascaras"):
        idx._mascaras = {}
    if tipo not in idx._mascaras:
        idx._mascaras[tipo] = np.array([t["category"] in categorias for t in idx.termos])
    return idx._mascaras[tipo]


def ler_limiar(arquivo: Path = ARQUIVO_LIMIAR) -> float:
    return float(json.loads(arquivo.read_text())["limiar"]) if arquivo.is_file() else LIMIAR_PADRAO


def _lexico_p2(textos: list[str], textos_caso: list[str]) -> list[str]:
    """Código do léxico do P2 (casamento exato, com siglas definidas no caso); "" quando não conhece."""
    from project2.src.tipos import lexico

    return [lexico.consultar(t, caso).mesh for t, caso in zip(textos, textos_caso)]


def normalizar(textos: list[str], tipos: list[str] | None = None, *, metodo: str = METODO_PADRAO,
               textos_caso: list[str] | None = None, limiar: float | None = None,
               filtrar_tipo: bool = False, pasta: Path = INDICE) -> list[tuple[str, float]]:
    """(código, score) de cada texto; código vazio quando nada passa do limiar.

    metodo="lexico+sapbert" (padrão): o léxico do P2 responde primeiro (score 1.0); o SapBERT cobre
    o que o léxico não conhece. metodo="sapbert": só o vizinho mais próximo do SapBERT.
    `tipos` e `textos_caso` (texto do caso, para expandir siglas no léxico) são paralelos a `textos`.
    Com `filtrar_tipo`, o SapBERT só procura em categorias compatíveis com o tipo. O score do
    SapBERT volta mesmo quando o código fica vazio.
    """
    if metodo not in METODOS:
        raise ValueError(f"metodo deve ser um de {METODOS}")
    for nome, lista in (("tipos", tipos), ("textos_caso", textos_caso)):
        if lista is not None and len(lista) != len(textos):
            raise ValueError(f"textos e {nome} precisam ter o mesmo tamanho")
    if not textos:
        return []
    if metodo == "lexico+sapbert":
        lexico = _lexico_p2(textos, textos_caso or [""] * len(textos))
        faltam = [i for i, c in enumerate(lexico) if not c]
        sap = normalizar([textos[i] for i in faltam], [tipos[i] for i in faltam] if tipos else None,
                         metodo="sapbert", limiar=limiar, filtrar_tipo=filtrar_tipo, pasta=pasta)
        resposta = [(c, 1.0) for c in lexico]
        for i, r in zip(faltam, sap):
            resposta[i] = r
        return resposta
    limiar = ler_limiar() if limiar is None else limiar
    idx = indice(pasta)
    unicos = sorted({t.strip().lower() for t in textos})
    vetores = dict(zip(unicos, codificador(idx.info["modelo"]).codificar(unicos)))
    tipos = tipos or [""] * len(textos)
    resposta: list[tuple[str, float] | None] = [None] * len(textos)
    por_tipo: dict[str, list[int]] = {}
    for i, tipo in enumerate(tipos):
        por_tipo.setdefault(tipo if filtrar_tipo else "", []).append(i)
    for tipo, posicoes in por_tipo.items():
        consultas = np.stack([vetores[textos[i].strip().lower()] for i in posicoes])
        for i, viz in zip(posicoes, idx.buscar(consultas, 1, mascara_do_tipo(idx, tipo))):
            melhor = viz[0]
            resposta[i] = (melhor.codigo if melhor.score >= limiar else "", round(melhor.score, 4))
    return resposta  # type: ignore[return-value]


def textos_dos_casos(ids: set[str], corpus: Path | None) -> dict[str, str]:
    """case_id -> case_text dos casos pedidos, lidos com project2.src.comum (CSV ou Parquet)."""
    if corpus is None:
        return {}
    from project2.src.comum import iter_casos

    return {cid: texto for cid, texto in iter_casos(corpus) if cid in ids}


def normalizar_csv(entrada: Path, saida: Path, *, metodo: str = METODO_PADRAO, corpus: Path | None = None,
                   filtrar_tipo: bool = False, limiar: float | None = None, pasta: Path = INDICE) -> int:
    """Reescreve um CSV de menções tipadas com `mesh` e `mesh_score` preenchidos.

    `corpus` (opcional) é o arquivo dos casos; com ele o léxico expande siglas definidas no texto.
    """
    with entrada.open(encoding="utf-8", newline="") as f:
        leitor = csv.DictReader(f)
        colunas, linhas = list(leitor.fieldnames or []), list(leitor)
    for coluna in ("case_id", "texto", "tipo"):
        if coluna not in colunas:
            raise ValueError(f"{entrada} não tem a coluna {coluna!r}")
    colunas += [c for c in ("mesh", "mesh_score") if c not in colunas]
    casos = textos_dos_casos({l["case_id"] for l in linhas}, corpus)
    codigos = normalizar([l["texto"] for l in linhas], [l["tipo"] for l in linhas], metodo=metodo,
                         textos_caso=[casos.get(l["case_id"], "") for l in linhas],
                         filtrar_tipo=filtrar_tipo, limiar=limiar, pasta=pasta)
    for linha, (codigo, score) in zip(linhas, codigos):
        linha["mesh"], linha["mesh_score"] = codigo, f"{score:.4f}"
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=colunas)
        escritor.writeheader()
        escritor.writerows(linhas)
    return len(linhas)


# --- Calibração do limiar sem tocar no gold -------------------------------------------------------

def _palavras(termo: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", termo.lower()))


def validacao_sinonimos(idx: Indice, n: int = 5000, semente: int = 0) -> list[tuple[float, bool]]:
    """(score, acertou) ao buscar um sinônimo do MeSH que foi tirado do índice.

    Para n códigos com mais de um termo, escolhe um termo e o esconde, junto com todo termo de mesmas
    palavras (`Infarction, Myocardial` = `Myocardial Infarction`). Simula uma menção que o gazetteer
    não tem escrita igual: o vizinho mais próximo ainda dá o código certo?
    """
    chaves = [_palavras(t["term"]) for t in idx.termos]
    por_chave: dict[frozenset[str], list[int]] = {}
    por_codigo: dict[str, set[frozenset[str]]] = {}
    for j, (t, chave) in enumerate(zip(idx.termos, chaves)):
        por_chave.setdefault(chave, []).append(j)
        por_codigo.setdefault(t["code"], set()).add(chave)
    rng = np.random.default_rng(semente)
    candidatos = sorted(c for c, ks in por_codigo.items() if len(ks) > 1)
    escolhidos = rng.choice(len(candidatos), size=min(n, len(candidatos)), replace=False)
    resultado = []
    for c in escolhidos:
        codigo = candidatos[c]
        chave = sorted(por_codigo[codigo], key=sorted)[rng.integers(len(por_codigo[codigo]))]
        consulta = por_chave[chave][0]
        sims = idx.vetores @ idx.vetores[consulta]
        sims[por_chave[chave]] = -np.inf
        resultado.append((float(sims.max()), idx.termos[int(sims.argmax())]["code"] == codigo))
    return resultado


def escolher_limiar(pares: list[tuple[float, bool]], faixa: float = 0.05, minimo: float = 0.5) -> float:
    """Menor score a partir do qual toda faixa de largura `faixa` acerta pelo menos `minimo`.

    Abaixo do limiar, o vizinho mais próximo erra mais do que acerta: melhor deixar o código vazio.
    """
    scores = np.array([s for s, _ in pares])
    acertos = np.array([a for _, a in pares])
    limiar = 1.0
    for inicio in np.arange(0.99, 0.0, -0.01):
        na_faixa = (scores >= inicio) & (scores < inicio + faixa)
        if na_faixa.sum() >= 20 and acertos[na_faixa].mean() < minimo:
            break
        limiar = round(float(inicio), 2)
    return limiar


def calibrar(pasta: Path = INDICE, arquivo: Path = ARQUIVO_LIMIAR, curva: Path = CURVA, n: int = 5000) -> float:
    pares = validacao_sinonimos(indice(pasta), n)
    limiar = escolher_limiar(pares)
    acertos = [a for s, a in pares if s >= limiar]
    arquivo.write_text(json.dumps({
        "limiar": limiar, "modelo": indice(pasta).info["modelo"], "sinonimos": len(pares),
        "acuracia_acima": round(sum(acertos) / max(len(acertos), 1), 4),
        "cobertura": round(len(acertos) / len(pares), 4),
        "metodo": "sinônimo do MeSH escondido do índice; ver validacao_sinonimos e escolher_limiar",
    }, indent=2, ensure_ascii=False) + "\n")
    curva.parent.mkdir(parents=True, exist_ok=True)
    with curva.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(["faixa_inicio", "faixa_fim", "sinonimos", "acuracia"])
        for inicio in np.arange(0.40, 1.0, 0.05):
            na_faixa = [a for s, a in pares if inicio <= s < inicio + 0.05 or (inicio >= 0.95 and s >= 1)]
            escritor.writerow([f"{inicio:.2f}", f"{inicio + 0.05:.2f}", len(na_faixa),
                               f"{sum(na_faixa) / len(na_faixa):.4f}" if na_faixa else ""])
    return limiar


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    p_indice = sub.add_parser("indice", help="codifica os gazetteers e salva o índice")
    p_indice.add_argument("--saida", type=Path, default=INDICE)
    p_indice.add_argument("--modelo", default=MODELO)
    sub.add_parser("calibrar", help="escolhe o limiar com sinônimos do MeSH (sem usar o gold)")
    p_csv = sub.add_parser("csv", help="preenche mesh e mesh_score num CSV de menções tipadas")
    p_csv.add_argument("--entrada", type=Path, required=True)
    p_csv.add_argument("--saida", type=Path, required=True)
    p_csv.add_argument("--metodo", choices=METODOS, default=METODO_PADRAO)
    p_csv.add_argument("--corpus", type=Path, default=None,
                       help="casos (CSV/Parquet) para o léxico expandir siglas, ex.: project1/data/case_texts.csv")
    p_csv.add_argument("--filtrar-tipo", action="store_true", help="só categorias compatíveis com o tipo")
    p_csv.add_argument("--limiar", type=float, default=None)
    args = parser.parse_args(argv)
    if args.comando == "indice":
        print(f"índice salvo em {construir_indice(args.saida, args.modelo)}")
    elif args.comando == "calibrar":
        print(f"limiar = {calibrar()} (salvo em {ARQUIVO_LIMIAR.relative_to(REPO)})")
    else:
        n = normalizar_csv(args.entrada, args.saida, metodo=args.metodo, corpus=args.corpus,
                           filtrar_tipo=args.filtrar_tipo, limiar=args.limiar)
        print(f"{n} menções normalizadas em {args.saida}")


if __name__ == "__main__":
    main()
