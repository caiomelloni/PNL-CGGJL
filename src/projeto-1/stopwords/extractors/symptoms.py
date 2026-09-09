"""Extração da entidade Symptom."""

import re

from .common import Mention, detect_polarity, is_hedged, split_sentences

_TRIGGER_PATTERN = re.compile(
    r"(presented with|complains? of|complained of|denies|denied)\s+(?P<rest>[^.!?\n]+)",
    re.IGNORECASE,
)

_DURATION_PREFIX = re.compile(
    r"^(a\s+)?(?P<value>\d+|one|two|three|four|five|six)[\s-](?P<unit>day|week|month|year)s?\s+history\s+of\s+",
    re.IGNORECASE,
)


def extract_symptoms(text: str) -> list[Mention]:
    """Extrai sintomas a partir de gatilhos como 'presented with'/'denies'."""
    mentions = []
    for sentence in split_sentences(text):
        match = _TRIGGER_PATTERN.search(sentence.text)
        if match is None:
            continue

        trigger = match.group(1)
        rest = match.group("rest")

        duration = None
        duration_match = _DURATION_PREFIX.match(rest)
        if duration_match is not None:
            duration = f"{duration_match.group('value')} {duration_match.group('unit')}s"
            rest = rest[duration_match.end():]

        polarity = detect_polarity(sentence.text)
        hedged = is_hedged(sentence.text)

        for raw_label in _split_symptom_list(rest):
            cleaned = raw_label.strip()
            if not cleaned:
                continue
            local_start = sentence.text.find(cleaned)
            if local_start < 0:
                continue
            start = sentence.start + local_start
            mentions.append(Mention(
                node_type="Symptom",
                label=cleaned,
                attributes={"polarity": polarity, "duration": duration},
                sentence=sentence,
                trigger=trigger,
                char_start=start,
                char_end=start + len(cleaned),
                hedged=hedged,
            ))
    return mentions


def _split_symptom_list(text: str) -> list[str]:
    text = re.sub(r"\bassociated with\b", ",", text, flags=re.IGNORECASE)
    text = re.sub(r"\band\b", ",", text, flags=re.IGNORECASE)
    text = re.sub(r"\bor\b", ",", text, flags=re.IGNORECASE)
    return [part.strip() for part in text.split(",")]
