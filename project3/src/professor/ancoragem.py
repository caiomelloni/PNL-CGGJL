"""Ancoragem: acha no texto original cada menção que o LLM devolveu e calcula `start`/`end`.

O LLM devolve só o texto da menção. Para virar uma linha do contrato, a menção precisa de offsets com
`case_text[start:end] == texto`. O que não for achado no trecho enviado é alucinação e é descartado.
"""
from __future__ import annotations

import re
from collections import defaultdict

from project2.src.montagem.montagem import TIPOS


def padrao(alvo: str) -> re.Pattern:
    """Mesmas palavras, com qualquer espaço entre elas e sem diferenciar maiúsculas.

    O LLM costuma trocar quebras de linha por espaço; o texto gravado é sempre o do original.
    As bordas exigem fronteira de palavra: "pain" não casa dentro de "painful".
    """
    corpo = r"\s+".join(re.escape(p) for p in alvo.split())
    inicio = r"(?<!\w)" if alvo[0].isalnum() else ""
    fim = r"(?!\w)" if alvo[-1].isalnum() else ""
    return re.compile(inicio + corpo + fim, re.IGNORECASE)


def ancorar(texto: str, inicio: int, fim: int, itens: list) -> tuple[list[dict], list[dict]]:
    """Ancora os itens do LLM no trecho `texto[inicio:fim]`.

    Devolve (menções, alucinações). Menção: {start, end, texto, tipo, polaridade}.
    Se o mesmo texto aparece várias vezes no trecho, a k-ésima vez que o LLM o lista fica com a
    k-ésima ocorrência; repetições além das ocorrências são duplicatas e são ignoradas.
    """
    trecho = texto[inicio:fim]
    mencoes, alucinacoes, usados, vistos = [], [], defaultdict(int), set()
    for item in itens:
        if not isinstance(item, dict):
            alucinacoes.append({"texto": str(item)[:200], "tipo": "", "motivo": "item_invalido"})
            continue
        alvo = str(item.get("texto") or "").strip()
        tipo = str(item.get("tipo") or "").strip()
        if not alvo:
            alucinacoes.append({"texto": "", "tipo": tipo, "motivo": "texto_vazio"})
            continue
        if tipo not in TIPOS:
            alucinacoes.append({"texto": alvo, "tipo": tipo, "motivo": "tipo_invalido"})
            continue
        ocorrencias = list(padrao(alvo).finditer(trecho))
        if not ocorrencias:
            alucinacoes.append({"texto": alvo, "tipo": tipo, "motivo": "nao_encontrado"})
            continue
        chave = (alvo.casefold(), tipo)
        k = usados[chave]
        usados[chave] += 1
        if k >= len(ocorrencias):
            continue
        m = ocorrencias[k]
        s, e = inicio + m.start(), inicio + m.end()
        if (s, e, tipo) in vistos:
            continue
        vistos.add((s, e, tipo))
        # Contrato: present ou absent. Qualquer outra coisa vira o padrão, present.
        polaridade = "absent" if str(item.get("polaridade", "")).strip().lower() == "absent" else "present"
        mencoes.append({"start": s, "end": e, "texto": texto[s:e], "tipo": tipo, "polaridade": polaridade})
    return mencoes, alucinacoes
