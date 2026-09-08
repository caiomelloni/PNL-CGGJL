"""Extração de entidades clínicas com regras clássicas."""

import re
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