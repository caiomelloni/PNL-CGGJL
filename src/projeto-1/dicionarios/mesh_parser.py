"""Parsing em streaming do thesaurus MeSH (desc*.xml, formato NLM).

Extrai apenas o necessário para o gazetteer (DescriptorUI, nome preferido,
tree numbers e termos/sinônimos), sem carregar a árvore XML inteira em
memória — o arquivo de descriptors tem ~300MB, na maior parte ocupado por
listas de qualificadores que não usamos aqui.

Não normaliza nada: essa etapa fica a cargo do módulo de normalização
(Fase 2), aplicado igualmente sobre o texto dos casos e sobre as entradas
geradas aqui.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class MeshDescriptor:
    """Um DescriptorRecord do MeSH, já reduzido ao que usamos."""

    code: str
    preferred_term: str
    tree_numbers: tuple[str, ...]
    terms: tuple[str, ...]  # preferred_term + todos os entry terms, sem duplicatas


def iter_descriptors(xml_path: str | Path):
    """Percorre o XML em streaming, gerando um MeshDescriptor por vez.

    Usa iterparse + elem.clear() para não reter na memória os elementos já
    processados — necessário dado o tamanho do arquivo.
    """
    xml_path = Path(xml_path)
    context = ET.iterparse(str(xml_path), events=("end",))

    for _, elem in context:
        if elem.tag != "DescriptorRecord":
            continue

        code_elem = elem.find("DescriptorUI")
        name_elem = elem.find("DescriptorName/String")

        if code_elem is None or name_elem is None:
            elem.clear()
            continue

        code = code_elem.text.strip()
        preferred_term = name_elem.text.strip()

        tree_numbers = tuple(
            tn.text.strip()
            for tn in elem.findall("TreeNumberList/TreeNumber")
            if tn.text
        )

        terms_seen: list[str] = [preferred_term]
        for term_string in elem.findall("ConceptList/Concept/TermList/Term/String"):
            if term_string.text:
                term = term_string.text.strip()
                if term and term not in terms_seen:
                    terms_seen.append(term)

        yield MeshDescriptor(
            code=code,
            preferred_term=preferred_term,
            tree_numbers=tree_numbers,
            terms=tuple(terms_seen),
        )

        elem.clear()


def _matches_prefix(tree_numbers: tuple[str, ...], prefixes: tuple[str, ...]) -> bool:
    return any(tn.startswith(prefix) for tn in tree_numbers for prefix in prefixes)


def build_raw_gazetteer(
    xml_path: str | Path,
    tree_prefixes: tuple[str, ...] | None = None,
) -> dict[str, list[tuple[str, str]]]:
    """Monta {termo: [(code, preferred_term), ...]}, sem normalizar.

    tree_prefixes: se informado, mantém só descriptors cujo tree number
    comece por algum desses prefixos (ex. ("C",) para doenças). Se None,
    inclui o MeSH inteiro.
    """
    gazetteer: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for descriptor in iter_descriptors(xml_path):
        if tree_prefixes is not None and not _matches_prefix(
            descriptor.tree_numbers, tree_prefixes
        ):
            continue

        for term in descriptor.terms:
            entry = (descriptor.code, descriptor.preferred_term)
            if entry not in gazetteer[term]:
                gazetteer[term].append(entry)

    return dict(gazetteer)
