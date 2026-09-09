"""Normalização de texto — usada igualmente no case_text e nas chaves do gazetteer.

Escopo deliberadamente mínimo (ver justificativa em README.md, seção do
processo 2): normalização Unicode (NFKC), remoção de pontuação nas bordas
do token e lowercasing. Sem stemming, sem lematização, sem remoção de
stop-words — variação morfológica não coberta pelo vocabulário fica a
cargo do fuzzy match (Fase 4), não desta etapa.

A normalização nunca substitui o texto original: ela só produz a *chave*
usada para consulta no gazetteer. O `label` do nó continua usando o texto
original, sem alteração.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable

import nltk

_STRIP_CHARS = ".,;:()[]{}\"'`"


def normalize_token(token: str) -> str:
    """Normaliza um único token já separado pelo tokenizador.

    Pode retornar string vazia (ex. token era só pontuação) — quem chama
    é responsável por descartar tokens vazios.
    """
    token = unicodedata.normalize("NFKC", token)
    token = token.strip(_STRIP_CHARS)
    return token.lower()


def normalize_tokens(tokens: list[str]) -> list[str]:
    """Aplica normalize_token a uma lista de tokens, descartando vazios."""
    return [t for t in (normalize_token(tok) for tok in tokens) if t]


def align_normalized_tokens(
    tokens: list[str],
    normalize_fn: Callable[[str], str] = normalize_token,
) -> list[tuple[int, str]]:
    """Normaliza uma lista de tokens preservando o índice original de cada
    um, mas descartando por completo os que normalizam para vazio (tokens
    de pontuação pura, ex. ".", "(", ")").

    Esse descarte é proposital e não pode ficar a cargo de quem faz o
    casamento (Fase 4): um token de pontuação não pode ficar "no meio" de
    uma janela de busca, nem nas bordas — ele não é uma palavra, e uma
    janela que o inclua arrisca costurar span através de fronteiras que
    não deveriam se juntar (ex. o fim de uma frase com o início da
    próxima). Descartando aqui, o restante do pipeline nunca vê esses
    tokens — só os índices originais não-consecutivos denunciam que algo
    foi pulado.

    normalize_fn: injetável de propósito — permite trocar depois pela
    normalização "oficial" do projeto (se a equipe convergir numa única),
    sem alterar a lógica de alinhamento/descarte de pontuação em si.
    """
    aligned = []
    for index, token in enumerate(tokens):
        normalized = normalize_fn(token)
        if normalized:
            aligned.append((index, normalized))
    return aligned


def normalize_term(
    text: str,
    normalize_fn: Callable[[str], str] = normalize_token,
) -> str:
    """Normaliza uma string de termo inteira (ex. entrada do gazetteer).

    Tokeniza com o mesmo tokenizador usado no case_text (nltk.word_tokenize),
    normaliza cada token e junta de volta com espaço simples — garante que
    o termo do MeSH passe pelo mesmo processo aplicado ao texto do caso.
    """
    tokens = nltk.word_tokenize(text)
    return " ".join(t for t in (normalize_fn(tok) for tok in tokens) if t)


def build_normalized_gazetteer(
    raw_gazetteer: dict[str, list[tuple[str, str]]],
    normalize_fn: Callable[[str], str] = normalize_token,
) -> dict[str, list[tuple[str, str]]]:
    """Reconstrói um gazetteer (saída de mesh_parser.rows_to_raw_gazetteer)
    trocando cada chave pela sua forma normalizada.

    Duas chaves brutas diferentes podem colidir na mesma chave normalizada
    (ex. variação só de maiúscula) — as entradas são mescladas, sem
    duplicar (code, preferred_term) repetidos.

    normalize_fn: injetável, mesmo motivo do parâmetro homônimo em
    align_normalized_tokens — o gazetteer persistido em disco
    (gazetteer/mesh_gazetteer.csv) é sempre cru; é só aqui, no momento de
    carregar para uso, que uma normalização (esta ou uma futura oficial do
    projeto) entra em cena.
    """
    normalized: dict[str, list[tuple[str, str]]] = {}

    for raw_key, entries in raw_gazetteer.items():
        key = normalize_term(raw_key, normalize_fn)
        if not key:
            continue
        bucket = normalized.setdefault(key, [])
        for entry in entries:
            if entry not in bucket:
                bucket.append(entry)

    return normalized
