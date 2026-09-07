"""Construção de resultados laboratoriais a partir de medições e faixas."""

import re
from dataclasses import dataclass

from measurement_extraction import (
    ExtractedMeasurement,
    ExtractedReferenceRange,
    find_measurements,
    find_reference_ranges,
)


# Um ponto entre dois dígitos é decimal; os demais pontos encerram sentença.
_SENTENCE_BOUNDARY = re.compile(r"\.(?!\d)|[!?]|\n+")


@dataclass(frozen=True)
class LabResultCandidate:
    """Resultado quantitativo encontrado em uma sentença."""

    measurement: ExtractedMeasurement
    reference_range: ExtractedReferenceRange | None
    evidence_text: str
    char_start: int
    char_end: int


def _sentence_span(
    text: str,
    position: int,
) -> tuple[int, int]:
    """Encontra os offsets da sentença que contém uma posição."""
    start = 0
    end = len(text)

    for boundary in _SENTENCE_BOUNDARY.finditer(text):
        if boundary.end() <= position:
            start = boundary.end()
            continue

        if boundary.start() >= position:
            end = boundary.end()
            break

    while start < end and text[start].isspace():
        start += 1

    while end > start and text[end - 1].isspace():
        end -= 1

    return start, end


def _range_distance(
    measurement: ExtractedMeasurement,
    reference_range: ExtractedReferenceRange,
) -> int:
    """Calcula a distância textual entre uma medição e uma faixa."""
    if reference_range.char_start >= measurement.char_end:
        return reference_range.char_start - measurement.char_end

    if measurement.char_start >= reference_range.char_end:
        return measurement.char_start - reference_range.char_end

    return 0


def _units_are_compatible(
    measurement: ExtractedMeasurement,
    reference_range: ExtractedReferenceRange,
) -> bool:
    """Verifica se medição e faixa podem representar a mesma grandeza."""
    measurement_unit = measurement.measurement.unit
    range_unit = reference_range.reference_range.unit

    return (
        measurement_unit is None
        or range_unit is None
        or measurement_unit == range_unit
    )


def _nearest_compatible_range(
    measurement: ExtractedMeasurement,
    ranges: list[ExtractedReferenceRange],
    sentence_start: int,
    sentence_end: int,
) -> ExtractedReferenceRange | None:
    """Seleciona a faixa compatível mais próxima na mesma sentença."""
    candidates = [
        reference_range
        for reference_range in ranges
        if reference_range.char_start >= sentence_start
        and reference_range.char_end <= sentence_end
        and _units_are_compatible(measurement, reference_range)
    ]

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda reference_range: _range_distance(
            measurement,
            reference_range,
        ),
    )


def find_lab_result_candidates(
    text: str,
) -> list[LabResultCandidate]:
    """Reúne medições e faixas encontradas na mesma sentença."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    measurements = find_measurements(text)
    ranges = find_reference_ranges(text)
    results: list[LabResultCandidate] = []

    for measurement in measurements:
        sentence_start, sentence_end = _sentence_span(
            text,
            measurement.char_start,
        )

        reference_range = _nearest_compatible_range(
            measurement,
            ranges,
            sentence_start,
            sentence_end,
        )

        results.append(
            LabResultCandidate(
                measurement=measurement,
                reference_range=reference_range,
                evidence_text=text[sentence_start:sentence_end],
                char_start=sentence_start,
                char_end=sentence_end,
            )
        )

    return results