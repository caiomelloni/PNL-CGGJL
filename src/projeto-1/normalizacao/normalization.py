"""Funções para normalizar rótulos extraídos de casos clínicos."""

import re
import unicodedata


_WHITESPACE_PATTERN = re.compile(r"\s+")

# Pontuação removida somente quando aparece nas extremidades.
# O hífen não está aqui porque pode fazer parte de termos como "C-reactive".
_BOUNDARY_PUNCTUATION = " \t\n\r.,;:!?\"'`()[]{}"


def normalize_unicode(text: str) -> str:
    """Padroniza representações Unicode equivalentes."""
    return unicodedata.normalize("NFKC", text)


def normalize_whitespace(text: str) -> str:
    """Substitui sequências de espaços por um único espaço."""
    return _WHITESPACE_PATTERN.sub(" ", text).strip()


def strip_boundary_punctuation(text: str) -> str:
    """Remove pontuação apenas do começo e do fim do texto."""
    return text.strip(_BOUNDARY_PUNCTUATION)


def normalize_label(text: str) -> str:
    """Produz a forma normalizada básica de um rótulo clínico."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    normalized = normalize_unicode(text)
    normalized = normalize_whitespace(normalized)
    normalized = strip_boundary_punctuation(normalized)
    normalized = normalized.casefold()
    normalized = normalize_whitespace(normalized)

    return normalized