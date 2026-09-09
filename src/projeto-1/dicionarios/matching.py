"""Estratégia de casamento (matching) entre menções do texto e o gazetteer.

Encadeia três técnicas em ordem de rigor decrescente:

1. exact match — string idêntica após normalização;
2. longest match — mesma comparação exata, mas tentando primeiro a maior
   janela de tokens consecutivos antes de encolher; cobre conceitos
   multi-palavra;
3. fuzzy match — só usado quando (1) e (2) não encontraram nada para um
   token isolado; usa distância de edição (rapidfuzz) com threshold
   definido empiricamente (ver README.md, Fase 4) em 85.

Fuzzy match aqui é aplicado só a tokens isolados, não a janelas
multi-palavra — decisão deliberada de manter o escopo simples: janelas
multi-palavra aproximadas multiplicam o espaço de busca sem necessidade,
já que o MeSH já cataloga a maioria das variações de fraseado relevantes
como entry terms (ver Fase 1).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import nltk
from rapidfuzz import fuzz, process

from normalization import align_normalized_tokens, normalize_term, normalize_token

FUZZY_THRESHOLD = 85.0


@dataclass(frozen=True)
class Match:
    """Um casamento entre um span de tokens (índices no texto original) e
    um conceito do gazetteer."""

    start: int  # índice do primeiro token original (inclusive)
    end: int  # índice após o último token original (exclusivo)
    matched_key: str  # chave normalizada que casou
    code: str
    preferred_term: str
    strategy: str  # "exact" | "longest" | "fuzzy"
    score: float | None = None  # só preenchido para fuzzy


def _break_tie(entries: list[tuple[str, str]], key: str) -> tuple[str, str]:
    """Quando uma chave normalizada aponta para mais de um concept, prefere
    aquele cujo preferred_term normaliza exatamente para a mesma chave
    (ou seja: a chave é o termo canônico daquele concept, não um sinônimo
    emprestado de outro). Caso nenhum (ou mais de um) satisfaça isso —
    situação não observada nos dados reais, mas tratada por segurança —,
    desempata pelo code em ordem alfabética, por determinismo.
    """
    if len(entries) == 1:
        return entries[0]

    canonical = [e for e in entries if normalize_term(e[1]) == key]
    if len(canonical) == 1:
        return canonical[0]

    return sorted(entries, key=lambda e: e[0])[0]


def greedy_match(
    raw_tokens: list[str],
    gazetteer: dict[str, list[tuple[str, str]]],
    max_window: int = 4,
    normalize_fn: Callable[[str], str] = normalize_token,
) -> tuple[list[Match], list[int]]:
    """Exact + longest match sobre os tokens de um span/texto já tokenizado.

    Retorna (matches, indices_sem_match) — os índices (no array de tokens
    originais) que nenhuma janela conseguiu casar, candidatos ao fuzzy
    match em seguida.

    normalize_fn: mesmo propósito do parâmetro homônimo em
    normalization.align_normalized_tokens — trocável por uma normalização
    oficial do projeto sem alterar a lógica de casamento.
    """
    aligned = align_normalized_tokens(raw_tokens, normalize_fn)  # [(indice_original, token_normalizado)]
    matches: list[Match] = []
    unmatched: list[int] = []

    i, n = 0, len(aligned)
    while i < n:
        found = False
        for w in range(min(max_window, n - i), 0, -1):
            key = " ".join(tok for _, tok in aligned[i : i + w])
            if key in gazetteer:
                start = aligned[i][0]
                end = aligned[i + w - 1][0] + 1
                code, preferred_term = _break_tie(gazetteer[key], key)
                strategy = "exact" if w == 1 else "longest"
                matches.append(
                    Match(start, end, key, code, preferred_term, strategy)
                )
                i += w
                found = True
                break
        if not found:
            unmatched.append(aligned[i][0])
            i += 1

    return matches, unmatched


def fuzzy_match_leftover(
    raw_tokens: list[str],
    unmatched_indices: list[int],
    gazetteer: dict[str, list[tuple[str, str]]],
    threshold: float = FUZZY_THRESHOLD,
) -> list[Match]:
    """Tenta fuzzy match para cada índice que sobrou do greedy_match,
    token a token (não em janelas multi-palavra — ver docstring do módulo).
    """
    if not gazetteer:
        return []

    keys = list(gazetteer.keys())
    matches: list[Match] = []

    for index in unmatched_indices:
        from normalization import normalize_token

        token = normalize_token(raw_tokens[index])
        if not token:
            continue

        result = process.extractOne(
            token, keys, scorer=fuzz.ratio, score_cutoff=threshold
        )
        if result is None:
            continue

        matched_key, score, _ = result
        code, preferred_term = _break_tie(gazetteer[matched_key], matched_key)
        matches.append(
            Match(
                index,
                index + 1,
                matched_key,
                code,
                preferred_term,
                "fuzzy",
                score=score,
            )
        )

    return matches


def match_text(
    raw_tokens: list[str],
    gazetteer: dict[str, list[tuple[str, str]]],
    max_window: int = 4,
    fuzzy_threshold: float = FUZZY_THRESHOLD,
) -> list[Match]:
    """Pipeline completo: greedy (exact+longest) seguido de fuzzy no que sobrar.

    Usado quando se tem um texto corrido (várias menções possíveis dentro),
    não uma entidade já delimitada — ver link_label_to_concept para esse caso.
    """
    matches, unmatched = greedy_match(raw_tokens, gazetteer, max_window)
    matches += fuzzy_match_leftover(raw_tokens, unmatched, gazetteer, fuzzy_threshold)
    return sorted(matches, key=lambda m: m.start)


def link_label_to_concept(
    label: str,
    gazetteer: dict[str, list[tuple[str, str]]],
    max_window: int = 4,
    fuzzy_threshold: float = FUZZY_THRESHOLD,
    tokenize_fn: Callable[[str], list[str]] = nltk.word_tokenize,
) -> Match | None:
    """Ponto de entrada único para integração com qualquer pipeline externo.

    Ao contrário de match_text (que varre um texto inteiro em busca de
    várias menções), esta função assume que ALGUÉM JÁ DECIDIU os limites
    da entidade — o NER de qualquer uma das quatro estratégias (#3-#6) já
    produziu um label como "epigastric pain" ou "right flank and lower
    quadrant abdominal pain" — e só quer saber: isso corresponde a um
    conceito do gazetteer, ou não?

    Devolve o melhor Match encontrado (o de maior span; exact/longest têm
    prioridade sobre fuzzy porque só chegam a fuzzy os labels em que
    nenhuma janela exata casou) ou None se a menção não casou com nada —
    cobertura parcial é esperada, conforme o contrato da issue.

    Este é o único ponto do módulo que qualquer código externo precisa
    conhecer para reusar a estratégia de dicionário: as demais funções
    (greedy_match, fuzzy_match_leftover) são detalhe de implementação.
    """
    tokens = tokenize_fn(label)
    if not tokens:
        return None

    matches, _ = greedy_match(tokens, gazetteer, max_window)
    if matches:
        return max(matches, key=lambda m: m.end - m.start)

    if not gazetteer:
        return None

    whole_label = normalize_term(label)
    if not whole_label:
        return None

    result = process.extractOne(
        whole_label, list(gazetteer.keys()), scorer=fuzz.ratio, score_cutoff=fuzzy_threshold
    )
    if result is None:
        return None

    matched_key, score, _ = result
    code, preferred_term = _break_tie(gazetteer[matched_key], matched_key)
    return Match(0, len(tokens), matched_key, code, preferred_term, "fuzzy", score=score)
