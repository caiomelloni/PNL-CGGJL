"""Extração de entidades clínicas com regras clássicas."""

import re
from dataclasses import dataclass
from decimal import Decimal

from case_reader import ClinicalCase
from graph import GraphBuilder
from models import Node


_PATIENT_DEMOGRAPHICS = re.compile(
    r"""
    \b
    (?P<age>\d+(?:\.\d+)?)
    \s*[- ]
    (?P<age_unit>year|month|day)s?
    [- ]old
    \s+
    (?P<gender>
        woman|man|female|male|girl|boy|infant|child|patient
    )
    \b
    """,
    re.VERBOSE | re.IGNORECASE,
)

_GESTATIONAL_AGE = re.compile(
    r"""
    \bborn\s+at\s+
    (?P<whole>\d+)
    (?:\s+(?P<numerator>\d+)/(?P<denominator>\d+))?
    \s+weeks?
    (?:\s+of)?
    \s+gestational\s+age
    \b
    """,
    re.VERBOSE | re.IGNORECASE,
)

_GENDER_VALUES = {
    "woman": "Female",
    "female": "Female",
    "girl": "Female",
    "man": "Male",
    "male": "Male",
    "boy": "Male",
}

_AGE_UNITS = {
    "year": "years",
    "month": "months",
    "day": "days",
}

_SYMPTOM_TRIGGER = re.compile(
    r"""
    \b(?P<trigger>
        presented\s+with
        |complained\s+of
        |admitted\s+with
        |reported
    )\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

_DURATION_PREFIX = re.compile(
    r"""
    ^
    (?:an?\s+)?
    (?P<value>
        \d+(?:\.\d+)?
        |one|two|three|four|five
        |six|seven|eight|nine|ten
    )
    [- ]
    (?P<unit>day|week|month|year)s?
    \s+history\s+of\s+
    """,
    re.VERBOSE | re.IGNORECASE,
)

_ASSOCIATION_SEPARATOR = re.compile(
    r"\b(?:associated\s+with|accompanied\s+by)\b",
    re.IGNORECASE,
)

_LIST_SEPARATOR = re.compile(
    r"\s*(?:,|\band\b|\bor\b)\s*",
    re.IGNORECASE,
)

_GLOBAL_NEGATION = re.compile(
    r"^(?:no|without)\s+",
    re.IGNORECASE,
)

_ATOMIC_SYMPTOMS = {
    "fever",
    "cough",
    "nausea",
    "constipation",
    "diarrhea",
    "vomiting",
    "emesis",
    "fatigue",
    "headache",
    "dyspnea",
    "weight loss",
    "night sweating",
    "abdominal distention",
}

_HISTORY_TRIGGER = re.compile(
    r"""
    \b(?P<trigger>
        family\s+history\s+(?:significant\s+for|of)
        |past\s+medical\s+history\s+(?:significant\s+for|of)
        |medical\s+history\s+(?:significant\s+for|of)
        |surgical\s+history\s+(?:significant\s+for|of)
        |medication\s+history\s+(?:significant\s+for|of)
    )\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

_HISTORY_SCOPE_STOP = re.compile(
    r"\b(?:who\s+presented|presented\s+with|was\s+admitted)\b",
    re.IGNORECASE,
)

_SURGERY_TERMS = re.compile(
    r"\b(?:surgery|replacement|resection|repair|transplantation|\w+ectomy)\b",
    re.IGNORECASE,
)

_EXPOSURE_TERMS = re.compile(
    r"\b(?:smoking|tobacco|alcohol|radiation|exposure)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractedEntity:
    """Nó extraído acompanhado de sua evidência textual."""

    node: Node
    evidence_text: str
    trigger: str
    char_start: int
    char_end: int


def _extract_text_demographics(
    case_text: str,
) -> tuple[Decimal | None, str | None, str | None]:
    """Extrai idade, unidade e gênero diretamente do texto."""
    match = _PATIENT_DEMOGRAPHICS.search(case_text)

    if match is not None:
        gender_word = match.group("gender").casefold()

        return (
            Decimal(match.group("age")),
            _AGE_UNITS[match.group("age_unit").casefold()],
            _GENDER_VALUES.get(gender_word),
        )

    gestational_match = _GESTATIONAL_AGE.search(case_text)

    if gestational_match is not None:
        age = Decimal(gestational_match.group("whole"))
        numerator = gestational_match.group("numerator")
        denominator = gestational_match.group("denominator")

        if numerator is not None and denominator is not None:
            if Decimal(denominator) == 0:
                raise ValueError(
                    "gestational age has zero denominator"
                )

            age += Decimal(numerator) / Decimal(denominator)

        return age, "weeks_gestational", None

    return None, None, None


def extract_patient(
    case: ClinicalCase,
    graph: GraphBuilder,
) -> Node:
    """Cria o nó Patient que ancora o grafo do caso."""
    if case.case_id != graph.case_id:
        raise ValueError(
            "case and graph use different case_id values"
        )

    if case.case_text != graph.case_text:
        raise ValueError(
            "case and graph use different case_text values"
        )

    text_age, text_age_unit, text_gender = (
        _extract_text_demographics(case.case_text)
    )

    age = text_age if text_age is not None else case.age
    gender = (
        text_gender
        if text_gender is not None
        else case.gender or "Unknown"
    )

    return graph.add_node(
        "Patient",
        f"case {case.case_id}",
        {
            "article_id": case.article_id,
            "age": age,
            "age_unit": text_age_unit,
            "gender": gender,
        },
    )


def _find_sentence_end(text: str, start: int) -> int:
    """Encontra o fim da sentença sem incluir sua pontuação."""
    match = re.search(r"[.!?\n]", text[start:])

    if match is None:
        return len(text)

    return start + match.start()


def _clean_symptom_label(text: str) -> str:
    """Remove conectores superficiais de uma menção."""
    cleaned = text.strip(" \t,;:()")
    cleaned = re.sub(
        r"^(?:a|an|the)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = _GLOBAL_NEGATION.sub("", cleaned)
    return cleaned.strip()


def _is_atomic_symptom_list(text: str) -> bool:
    """Verifica se todos os itens coordenados são sintomas conhecidos."""
    parts = [
        _clean_symptom_label(part).casefold()
        for part in _LIST_SEPARATOR.split(text)
        if _clean_symptom_label(part)
    ]

    return (
        len(parts) > 1
        and all(part in _ATOMIC_SYMPTOMS for part in parts)
    )


def _split_symptom_scope(
    scope: str,
) -> tuple[list[str], int]:
    """Divide o escopo e informa quantos itens são o sintoma principal."""
    association = _ASSOCIATION_SEPARATOR.search(scope)

    if association is not None:
        main_text = scope[:association.start()]
        associated_text = scope[association.end():]

        main_parts = [_clean_symptom_label(main_text)]
        associated_parts = [
            _clean_symptom_label(part)
            for part in _LIST_SEPARATOR.split(associated_text)
        ]

        parts = main_parts + associated_parts
        return [part for part in parts if part], len(main_parts)

    if (
        _GLOBAL_NEGATION.match(scope)
        or _is_atomic_symptom_list(scope)
    ):
        parts = [
            _clean_symptom_label(part)
            for part in _LIST_SEPARATOR.split(scope)
        ]
        cleaned_parts = [part for part in parts if part]
        return cleaned_parts, len(cleaned_parts)

    return [_clean_symptom_label(scope)], 1


def _normalized_duration(match: re.Match[str]) -> str:
    """Padroniza uma duração encontrada antes do sintoma."""
    value = match.group("value").casefold()
    unit = match.group("unit").casefold()
    suffix = "" if value in {"1", "one"} else "s"

    return f"{value} {unit}{suffix}"


def extract_symptoms(
    case_text: str,
    graph: GraphBuilder,
) -> list[ExtractedEntity]:
    """Extrai sintomas introduzidos por gatilhos explícitos."""
    if case_text != graph.case_text:
        raise ValueError("case_text and graph use different texts")

    extracted: list[ExtractedEntity] = []

    for trigger_match in _SYMPTOM_TRIGGER.finditer(case_text):
        scope_start = trigger_match.end()
        sentence_end = _find_sentence_end(case_text, scope_start)
        scope = case_text[scope_start:sentence_end].strip()
        evidence_start = trigger_match.start()
        evidence_text = case_text[evidence_start:sentence_end].strip()

        if not scope:
            continue

        global_polarity = (
            "absent" if _GLOBAL_NEGATION.match(scope) else "present"
        )
        duration = None
        duration_match = _DURATION_PREFIX.match(scope)

        if duration_match is not None:
            duration = _normalized_duration(duration_match)
            scope = scope[duration_match.end():]

        symptom_labels, main_count = _split_symptom_scope(scope)

        for index, raw_label in enumerate(symptom_labels):
            attributes = {
                "polarity": global_polarity,
                "duration": (
                    duration
                    if duration is not None and index < main_count
                    else None
                ),
            }
            node = graph.add_node("Symptom", raw_label, attributes)

            extracted.append(
                ExtractedEntity(
                    node=node,
                    evidence_text=evidence_text,
                    trigger=trigger_match.group("trigger"),
                    char_start=evidence_start,
                    char_end=sentence_end,
                )
            )

    return extracted


def _history_category(raw_label: str, trigger: str) -> str:
    """Classifica a natureza do antecedente por pistas lexicais."""
    trigger_folded = trigger.casefold()

    if "medication history" in trigger_folded:
        return "medication"

    if "surgical history" in trigger_folded:
        return "surgery"

    if _SURGERY_TERMS.search(raw_label):
        return "surgery"

    if _EXPOSURE_TERMS.search(raw_label):
        return "exposure"

    return "condition"


def extract_history(
    case_text: str,
    graph: GraphBuilder,
) -> list[ExtractedEntity]:
    """Extrai antecedentes introduzidos por gatilhos explícitos."""
    if case_text != graph.case_text:
        raise ValueError("case_text and graph use different texts")

    extracted: list[ExtractedEntity] = []

    for trigger_match in _HISTORY_TRIGGER.finditer(case_text):
        scope_start = trigger_match.end()
        sentence_end = _find_sentence_end(case_text, scope_start)
        scope = case_text[scope_start:sentence_end].strip()
        stop_match = _HISTORY_SCOPE_STOP.search(scope)

        if stop_match is not None:
            scope = scope[:stop_match.start()].strip(" \t,;")

        if not scope:
            continue

        trigger = trigger_match.group("trigger")
        subject = (
            "family"
            if trigger.casefold().startswith("family")
            else "patient"
        )
        relation_degree = "unspecified" if subject == "family" else None
        evidence_end = scope_start + len(
            case_text[scope_start:sentence_end]
        )

        if stop_match is not None:
            evidence_end = scope_start + stop_match.start()

        evidence_text = case_text[
            trigger_match.start():evidence_end
        ].strip()

        labels = [
            _clean_symptom_label(part)
            for part in _LIST_SEPARATOR.split(scope)
        ]

        for raw_label in (label for label in labels if label):
            node = graph.add_node(
                "History",
                raw_label,
                {
                    "subject": subject,
                    "polarity": "present",
                    "relation_degree": relation_degree,
                    "category": _history_category(raw_label, trigger),
                },
            )
            extracted.append(
                ExtractedEntity(
                    node=node,
                    evidence_text=evidence_text,
                    trigger=trigger,
                    char_start=trigger_match.start(),
                    char_end=evidence_end,
                )
            )

    return extracted
