"""Extração da entidade Outcome."""

import re

from .common import Mention, detect_polarity, split_sentences

_OUTCOME_KEYWORDS = {
    "death": ("expired", "died", "death"),
    "discharge": ("discharged",),
    "resolution": ("resolution", "resolved"),
    "recurrence": ("recurrence", "recurred"),
    "improvement": ("improved", "improvement"),
    "complication": ("complication",),
}

_DURATION_PATTERN = re.compile(
    r"(postoperative day\s+\d+|\d+\s*(day|week|month|year)s?)",
    re.IGNORECASE,
)


def extract_outcomes(text: str) -> list[Mention]:
    """Extrai o desfecho do caso, preferindo o que vem após uma adversativa."""
    mentions = []
    for sentence in split_sentences(text):
        lowered = sentence.text.lower()
        search_text = lowered
        offset = 0
        for connector in (" but ", " later "):
            if connector in search_text:
                tail = search_text.rsplit(connector, 1)[-1]
                offset = len(sentence.text) - len(tail)
                search_text = tail

        outcome_type = None
        matched_keyword = None
        for candidate_type, keywords in _OUTCOME_KEYWORDS.items():
            for keyword in keywords:
                if keyword in search_text:
                    outcome_type = candidate_type
                    matched_keyword = keyword
                    break
            if outcome_type is not None:
                break

        if outcome_type is None:
            continue

        duration_match = _DURATION_PATTERN.search(sentence.text)
        duration = duration_match.group(0) if duration_match else None

        start = sentence.start + offset + search_text.find(matched_keyword)
        mentions.append(Mention(
            node_type="Outcome",
            label=matched_keyword,
            attributes={
                "type": outcome_type,
                "polarity": detect_polarity(sentence.text),
                "timing": duration,
                "length_of_stay": duration if outcome_type == "discharge" else None,
            },
            sentence=sentence,
            trigger=matched_keyword,
            char_start=start,
            char_end=start + len(matched_keyword),
            hedged=False,
        ))
    return mentions
