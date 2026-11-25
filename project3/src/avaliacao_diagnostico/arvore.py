"""Árvore do MeSH (tree numbers) para o acerto hierárquico do diagnóstico (Etapa 8, Frente C).

    python -m project3.src.avaliacao_diagnostico.arvore --xml project3/data/external/mesh/desc2026.xml

O XML de descritores vem da NLM:
https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc2026.xml
"""
from __future__ import annotations

import argparse
import csv
import sys
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
XML = REPO / "project3" / "data" / "external" / "mesh" / "desc2026.xml"
ARVORE = REPO / "project3" / "data" / "processed" / "mesh_arvore.csv"


def gerar(xml: Path = XML, saida: Path = ARVORE) -> int:
    """Escreve `code, preferred_term, tree_numbers` (tree numbers separados por `;`)."""
    pasta = str(REPO / "project1" / "src" / "dicionarios")
    if pasta not in sys.path:
        sys.path.insert(0, pasta)
    from mesh_parser import iter_descriptors

    saida.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with saida.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(["code", "preferred_term", "tree_numbers"])
        for d in iter_descriptors(xml):
            escritor.writerow([d.code, d.preferred_term, ";".join(d.tree_numbers)])
            n += 1
    return n


class Arvore:
    """Relações de pai e filho entre códigos MeSH, pelos tree numbers (C14.280 é pai de C14.280.647)."""

    def __init__(self, numeros: dict[str, tuple[str, ...]]):
        self.numeros = numeros
        self.codigo_do_no = {tn: c for c, tns in numeros.items() for tn in tns}

    @classmethod
    def ler(cls, caminho: Path = ARVORE) -> "Arvore":
        if not caminho.is_file():
            raise FileNotFoundError(f"{caminho} não existe: rode "
                                    "`python -m project3.src.avaliacao_diagnostico.arvore` antes")
        with caminho.open(encoding="utf-8", newline="") as f:
            return cls({l["code"]: tuple(t for t in l["tree_numbers"].split(";") if t) for l in csv.DictReader(f)})

    def pais(self, codigo: str) -> set[str]:
        return {self.codigo_do_no[tn.rsplit(".", 1)[0]] for tn in self.numeros.get(codigo, ())
                if "." in tn and tn.rsplit(".", 1)[0] in self.codigo_do_no}

    def parentes(self, a: str, b: str) -> bool:
        """Mesmo código, ou um é pai direto do outro (um nível; avós não contam)."""
        return a == b or a in self.pais(b) or b in self.pais(a)


@lru_cache(maxsize=1)
def arvore(caminho: Path = ARVORE) -> Arvore:
    return Arvore.ler(caminho)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xml", type=Path, default=XML)
    parser.add_argument("--saida", type=Path, default=ARVORE)
    args = parser.parse_args(argv)
    print(f"{gerar(args.xml, args.saida)} descritores em {args.saida}")


if __name__ == "__main__":
    main()
