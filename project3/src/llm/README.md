# Cliente LLM — Etapa 2 (Frente B, Caio)

Ponto único por onde passa toda chamada de LLM do Projeto 3. Guarda as respostas em cache em disco
(a mesma pergunta não é paga duas vezes), troca de provedor por variável de ambiente e registra o uso
de cada chamada.

## Como rodar

~~~bash
pip install -r project3/src/llm/requirements.txt
export P3_LLM_API_KEY=...                 # Anthropic; nunca em código nem commit
export P3_LLM_MODELO=claude-opus-5-5      # padrão do provedor anthropic
# ou, local: export P3_LLM_PROVEDOR=ollama P3_LLM_MODELO=<modelo baixado>
python -m unittest project3.tests.test_llm
~~~

| Variável | Uso |
|---|---|
| `P3_LLM_PROVEDOR` | `anthropic` (padrão) ou `ollama` |
| `P3_LLM_MODELO` | modelo padrão; obrigatório no Ollama |
| `P3_LLM_API_KEY` | chave da Anthropic (sem ela, o SDK usa `ANTHROPIC_API_KEY`) |
| `P3_LLM_URL` | endereço do Ollama (padrão `http://localhost:11434`) |
| `P3_LLM_ESFORCO` | `effort` da Anthropic (`low`…`max`); vazio = padrão do modelo |

## Entradas e saídas

| Arquivo | Entrada/Saída | Colunas | Versionado? |
|---|---|---|---|
| `data/interim/cache_llm/<hash>.json` | Saída | texto, tokens, segundos, custo | Não |
| `data/interim/uso_llm.csv` | Saída | `quando, provedor, modelo, tokens_entrada, tokens_saida, segundos, custo_usd, do_cache, chave` | Não |

## API

~~~python
from project3.src.llm import chamar, ler_json
r = chamar(prompt, sistema="", modelo=None, json=False, temperatura=0.0)
# r.texto, r.modelo, r.tokens_entrada, r.tokens_saida, r.segundos, r.do_cache, r.custo_usd
dados = ler_json(r.texto)   # JSON da resposta, aceita cercas ```json
~~~

- A chave do cache é o hash de (modelo, sistema, prompt, temperatura).
- `segundos` e `custo_usd` são os da geração original, mesmo vindo do cache; `do_cache` diz se houve gasto agora.
- Nos testes, `chamar(..., provedor=funcao)` troca o provedor por uma função falsa.

## Resultados

Sem números próprios: o custo medido aparece em [`custo_professor.csv`](../../data/resultados/custo_professor.csv).

## Limitações

- Os modelos Claude atuais não aceitam `temperature`: na Anthropic ela só entra na chave do cache.
- Preços em `PRECOS` (USD por milhão de tokens) são fixos no código; modelo fora da tabela custa 0.
- Sem chamadas em paralelo nem Batch API.
