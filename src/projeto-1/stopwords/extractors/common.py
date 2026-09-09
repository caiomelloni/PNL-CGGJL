"""Estruturas e utilitários compartilhados pelos extratores de entidade."""

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Sentence:
    """Uma sentença do case_text, com seus offsets no texto original."""

    text: str
    start: int
    end: int
    index: int


def split_sentences(text: str) -> list[Sentence]:
    """Quebra o texto em sentenças por pontuação terminal, preservando offsets."""
    sentences = []
    start = 0
    index = 0
    for match in re.finditer(r"[.!?\n]+", text):
        end = match.start()
        if end > start:
            sentences.append(Sentence(text=text[start:end], start=start, end=end, index=index))
            index += 1
        start = match.end()
    if start < len(text):
        sentences.append(Sentence(text=text[start:], start=start, end=len(text), index=index))
    return sentences


@dataclass(frozen=True)
class Mention:
    """Uma entidade extraída, com a evidência textual que a sustenta."""

    node_type: str
    label: str
    attributes: dict[str, Any]
    sentence: Sentence
    trigger: str
    char_start: int
    char_end: int
    hedged: bool


_NEGATION_TRIGGERS = (
    "no evidence of", "denies", "denied", "deny", "without",
    "free of", "ruled out", "negative for", "unremarkable for",
    " no ", "not ",
)

_HEDGE_SUSPECTED_TRIGGERS = ("suggesting", "suggestive of", "possible")
_HEDGE_PROBABLE_TRIGGERS = ("consistent with", "likely", "probable", "presumed")


def detect_polarity(sentence_text: str) -> str:
    """'absent' se a sentença contém um gatilho de negação, senão 'present'."""
    lowered = f" {sentence_text.lower()} "
    for trigger in _NEGATION_TRIGGERS:
        if trigger in lowered:
            return "absent"
    return "present"


def detect_certainty(sentence_text: str) -> str:
    """'suspected'/'probable'/'confirmed' conforme o hedge mais forte encontrado."""
    lowered = sentence_text.lower()
    for trigger in _HEDGE_SUSPECTED_TRIGGERS:
        if trigger in lowered:
            return "suspected"
    for trigger in _HEDGE_PROBABLE_TRIGGERS:
        if trigger in lowered:
            return "probable"
    return "confirmed"


def is_hedged(sentence_text: str) -> bool:
    return detect_certainty(sentence_text) != "confirmed"
