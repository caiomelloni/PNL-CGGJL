"""Cliente LLM comum do Projeto 3: toda chamada de LLM passa por `chamar()`.

Três responsabilidades:
1. Cache em disco: a mesma pergunta (modelo, sistema, prompt, temperatura) nunca é paga duas vezes.
2. Provedor trocável: `P3_LLM_PROVEDOR=anthropic` (padrão) ou `ollama`, sem mudar quem chama.
3. Registro de uso: cada chamada vira uma linha em `data/interim/uso_llm.csv` (tokens, tempo, custo).

Variáveis de ambiente: `P3_LLM_PROVEDOR`, `P3_LLM_MODELO`, `P3_LLM_API_KEY` (Anthropic),
`P3_LLM_URL` (Ollama, padrão http://localhost:11434) e `P3_LLM_ESFORCO` (Anthropic, opcional).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CACHE = REPO / "project3/data/interim/cache_llm"
USO = REPO / "project3/data/interim/uso_llm.csv"
MODELO_ANTHROPIC = "claude-opus-5-5"
# USD por milhão de tokens (entrada, saída). Modelo fora da tabela (ex.: local) custa 0.
PRECOS = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
# Modelos que aceitam o fallback do servidor quando um classificador de segurança recusa o pedido.
COM_FALLBACK = {"claude-opus-5-5", "claude-sonnet-5-5"}
INSTRUCAO_JSON = "Respond with valid JSON only, with no text before or after it."
COLUNAS_USO = ["quando", "provedor", "modelo", "tokens_entrada", "tokens_saida", "segundos",
               "custo_usd", "do_cache", "chave"]


@dataclass(frozen=True)
class Resposta:
    texto: str
    modelo: str
    tokens_entrada: int
    tokens_saida: int
    segundos: float      # tempo da geração original, mesmo quando a resposta vem do cache
    do_cache: bool       # True: não houve chamada agora, logo não houve gasto agora
    custo_usd: float = 0.0


class RecusaLLM(RuntimeError):
    """O modelo recusou o pedido (stop_reason == "refusal")."""


# ================================================================== provedores ==
# Um provedor recebe a pergunta e devolve texto, tokens e custo. Trocar de provedor não muda `chamar`.
Provedor = Callable[..., dict]


def custo(modelo: str, entrada: int, saida: int, cache_escrita: int = 0, cache_leitura: int = 0) -> float:
    """Leitura de cache sai a 10% do preço de entrada e escrita a 125%, como na tabela da Anthropic."""
    p_in, p_out = PRECOS.get(modelo, (0.0, 0.0))
    return (entrada * p_in + cache_escrita * p_in * 1.25 + cache_leitura * p_in * 0.10 + saida * p_out) / 1e6


@lru_cache(maxsize=1)
def _cliente_anthropic():
    import anthropic  # só quem usa este provedor precisa do pacote

    # Sem P3_LLM_API_KEY o SDK procura as credenciais padrão (ANTHROPIC_API_KEY, `ant auth login`).
    return anthropic.Anthropic(api_key=os.environ.get("P3_LLM_API_KEY") or None)


def anthropic_(prompt: str, sistema: str, modelo: str, temperatura: float, json_: bool) -> dict:
    # Os modelos Claude atuais não aceitam `temperature`: ela só entra na chave do cache.
    params = {
        "model": modelo,
        "max_tokens": 16000,
        "messages": [{"role": "user", "content": prompt}],
    }
    if sistema:
        # O sistema (instruções + exemplos) é igual em todas as chamadas: marcá-lo para cache
        # do provedor faz as chamadas seguintes pagarem 10% por esse trecho.
        params["system"] = [{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}]
    if esforco := os.environ.get("P3_LLM_ESFORCO"):
        params["output_config"] = {"effort": esforco}
    if modelo in COM_FALLBACK:
        params.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    r = _cliente_anthropic().beta.messages.create(**params)
    if r.stop_reason == "refusal":
        raise RecusaLLM(getattr(r.stop_details, "explanation", None) or "recusado")
    u = r.usage
    escrita, leitura = u.cache_creation_input_tokens or 0, u.cache_read_input_tokens or 0
    return {
        "texto": "".join(b.text for b in r.content if b.type == "text"),
        "tokens_entrada": u.input_tokens + escrita + leitura,
        "tokens_saida": u.output_tokens,
        "custo_usd": custo(modelo, u.input_tokens, u.output_tokens, escrita, leitura),
    }


def ollama(prompt: str, sistema: str, modelo: str, temperatura: float, json_: bool) -> dict:
    from urllib.request import Request, urlopen

    corpo = {"model": modelo, "stream": False, "options": {"temperature": temperatura},
             "messages": ([{"role": "system", "content": sistema}] if sistema else [])
             + [{"role": "user", "content": prompt}]}
    if json_:
        corpo["format"] = "json"
    url = os.environ.get("P3_LLM_URL", "http://localhost:11434").rstrip("/") + "/api/chat"
    pedido = Request(url, json.dumps(corpo).encode(), {"Content-Type": "application/json"})
    with urlopen(pedido, timeout=600) as resposta:
        dados = json.load(resposta)
    return {"texto": dados["message"]["content"], "tokens_entrada": dados.get("prompt_eval_count", 0),
            "tokens_saida": dados.get("eval_count", 0), "custo_usd": 0.0}


PROVEDORES: dict[str, Provedor] = {"anthropic": anthropic_, "ollama": ollama}


def modelo_padrao(provedor: str | None = None) -> str:
    provedor = provedor or os.environ.get("P3_LLM_PROVEDOR", "anthropic")
    if modelo := os.environ.get("P3_LLM_MODELO"):
        return modelo
    if provedor == "anthropic":
        return MODELO_ANTHROPIC
    raise ValueError(f"Defina P3_LLM_MODELO para o provedor {provedor}")


# ===================================================================== chamar ==
def chave_cache(modelo: str, sistema: str, prompt: str, temperatura: float) -> str:
    bruto = json.dumps([modelo, sistema, prompt, temperatura], ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _registrar(provedor: str, resposta: Resposta, chave: str) -> None:
    USO.parent.mkdir(parents=True, exist_ok=True)
    novo = not USO.is_file()
    with USO.open("a", encoding="utf-8", newline="") as handle:
        escritor = csv.writer(handle)
        if novo:
            escritor.writerow(COLUNAS_USO)
        escritor.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), provedor,
                           resposta.modelo, resposta.tokens_entrada, resposta.tokens_saida,
                           round(resposta.segundos, 3), round(resposta.custo_usd, 6),
                           int(resposta.do_cache), chave[:16]])


def chamar(prompt: str, *, sistema: str = "", modelo: str | None = None, json: bool = False,
           temperatura: float = 0.0, provedor: str | Provedor | None = None) -> Resposta:
    """Responde `prompt`, lendo do cache quando a mesma pergunta já foi feita.

    `json=True` acrescenta ao sistema a instrução de responder só JSON (use `ler_json` na resposta).
    `provedor` aceita um nome de PROVEDORES ou uma função; os testes passam um provedor falso.
    """
    if provedor is None or isinstance(provedor, str):
        nome = provedor or os.environ.get("P3_LLM_PROVEDOR", "anthropic")
        if nome not in PROVEDORES:
            raise ValueError(f"Provedor desconhecido: {nome}. Use um de {sorted(PROVEDORES)}")
        funcao = PROVEDORES[nome]
    else:
        nome, funcao = getattr(provedor, "__name__", "personalizado"), provedor
    modelo = modelo or modelo_padrao(nome)
    if json:
        sistema = f"{sistema}\n\n{INSTRUCAO_JSON}" if sistema else INSTRUCAO_JSON

    chave = chave_cache(modelo, sistema, prompt, temperatura)
    arquivo = CACHE / chave[:2] / f"{chave}.json"
    if arquivo.is_file():
        salvo = _json_mod.loads(arquivo.read_text(encoding="utf-8"))
        resposta = Resposta(salvo["texto"], modelo, salvo["tokens_entrada"], salvo["tokens_saida"],
                            salvo["segundos"], True, salvo["custo_usd"])
    else:
        inicio = time.perf_counter()
        gerado = funcao(prompt, sistema, modelo, temperatura, json)
        resposta = Resposta(gerado["texto"], modelo, gerado["tokens_entrada"], gerado["tokens_saida"],
                            time.perf_counter() - inicio, False, gerado.get("custo_usd", 0.0))
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        # Grava num temporário e renomeia: uma interrupção no meio nunca deixa um cache corrompido.
        temporario = arquivo.with_suffix(".tmp")
        temporario.write_text(_json_mod.dumps(
            {"provedor": nome, "modelo": modelo, "texto": resposta.texto,
             "tokens_entrada": resposta.tokens_entrada, "tokens_saida": resposta.tokens_saida,
             "segundos": resposta.segundos, "custo_usd": resposta.custo_usd},
            ensure_ascii=False), encoding="utf-8")
        temporario.replace(arquivo)
    _registrar(nome, resposta, chave)
    return resposta


_json_mod = json  # `chamar` tem um parâmetro chamado `json` (contrato), que esconde o módulo


def ler_json(texto: str):
    """JSON da resposta, tolerando cercas ```json ... ``` em volta."""
    limpo = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", texto.strip())
    return _json_mod.loads(limpo)
