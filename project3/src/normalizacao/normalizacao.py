"""Normalização de menções clínicas para códigos MeSH por embeddings (Etapa 5, Frente C).

Cada termo dos gazetteers do projeto 1 (MeSH e sítios anatômicos) vira um vetor do SapBERT,
um BERT biomédico treinado para que sinônimos fiquem próximos. Uma menção recebe o código do
termo mais parecido (similaridade de cosseno).

    python -m project3.src.normalizacao.normalizacao indice
"""
from __future__ import annotations

import argparse
import csv
import json
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)
    p_indice = sub.add_parser("indice", help="codifica os gazetteers e salva o índice")
    p_indice.add_argument("--saida", type=Path, default=INDICE)
    p_indice.add_argument("--modelo", default=MODELO)
    args = parser.parse_args(argv)
    if args.comando == "indice":
        print(f"índice salvo em {construir_indice(args.saida, args.modelo)}")


if __name__ == "__main__":
    main()
