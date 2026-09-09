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

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET


# Categoria (rótulo livre, usado como coluna no gazetteer persistido) ->
# prefixos de TreeNumber que definem essa categoria. Ver justificativa de
# cada mapeamento em README.md, Fase 1. Mantido aqui (não em normalization.py
# nem em matching.py) porque é conhecimento específico da fonte MeSH — um
# vocabulário diferente, no futuro, teria seu próprio critério de categoria.
CATEGORY_PREFIXES: dict[str, tuple[str, ...]] = {
    "diseases": ("C",),  # Diagnosis, History, Symptom, Finding
    "drugs": ("D",),  # Medication
    "exams": ("E01",),  # Exam
    "treatments": ("E02", "E04"),  # Treatment
    "mental_disorders": ("F03",),  # Diagnosis (psiquiátrico)
}

GAZETTEER_CSV_COLUMNS = ("term", "code", "preferred_term", "category")


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


def build_gazetteer_rows(
    xml_path: str | Path,
    category_prefixes: dict[str, tuple[str, ...]] = CATEGORY_PREFIXES,
) -> list[dict[str, str]]:
    """Uma única passada pelo XML, gerando uma linha crua por (termo, categoria).

    "Crua" = exatamente como está no MeSH, sem normalizar nada — é essa
    lista que vira o gazetteer versionado em disco (ver save_gazetteer_csv).
    Um descriptor que pertença a mais de uma categoria (tree numbers em
    ramos diferentes) gera uma linha por categoria em que se encaixa.
    """
    rows: list[dict[str, str]] = []

    for descriptor in iter_descriptors(xml_path):
        matched_categories = [
            name
            for name, prefixes in category_prefixes.items()
            if _matches_prefix(descriptor.tree_numbers, prefixes)
        ]
        if not matched_categories:
            continue

        for category in matched_categories:
            for term in descriptor.terms:
                rows.append(
                    {
                        "term": term,
                        "code": descriptor.code,
                        "preferred_term": descriptor.preferred_term,
                        "category": category,
                    }
                )

    return rows


def save_gazetteer_csv(rows: list[dict[str, str]], csv_path: str | Path) -> None:
    """Persiste as linhas cruas (ver build_gazetteer_rows) num CSV versionável."""
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=GAZETTEER_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def load_gazetteer_rows(csv_path: str | Path) -> list[dict[str, str]]:
    """Lê de volta o CSV gerado por save_gazetteer_csv."""
    csv_path = Path(csv_path)

    with csv_path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def rows_to_raw_gazetteer(
    rows: list[dict[str, str]],
    category: str | None = None,
) -> dict[str, list[tuple[str, str]]]:
    """Agrupa linhas cruas (de load_gazetteer_rows) por termo, sem normalizar.

    category: se informado, mantém só linhas dessa categoria. Se None,
    junta todas as categorias no mesmo dicionário (uso raro — normalmente
    quem consome quer uma categoria por vez, ver README).
    """
    gazetteer: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for row in rows:
        if category is not None and row["category"] != category:
            continue

        entry = (row["code"], row["preferred_term"])
        if entry not in gazetteer[row["term"]]:
            gazetteer[row["term"]].append(entry)

    return dict(gazetteer)
