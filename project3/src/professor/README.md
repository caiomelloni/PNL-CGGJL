# Professor — Etapa 2 (Frente B, Caio)

Um LLM extrai menções tipadas (`tipo` e `polaridade`) dos casos. Cada caso é cortado em trechos de
frases inteiras; o LLM devolve o texto de cada menção, e a ancoragem acha esse texto no trecho para
calcular `start`/`end`. O que não existe no texto é descartado e contado como alucinação.

## Como rodar

Pré-requisito: cliente LLM configurado ([`../llm/README.md`](../llm/README.md)). Da raiz do repositório:

~~~bash
python -m project3.src.professor.professor custo --n 50          # mede o custo e define N
python -m project3.src.professor.professor rodar --n-treino N    # teste + validação + N de treino
python -m project3.src.professor.professor comparar --gold <menções anotadas de validação>
python -m unittest project3.tests.test_professor
~~~

Opções globais (antes do subcomando): `--corpus` (padrão `project1/data/case_texts.csv`), `--modelo`,
`--exemplos <csv>|nenhum`. Rodar de novo é barato: o que já foi perguntado vem do cache.

## Entradas e saídas

| Arquivo | Entrada/Saída | Colunas | Versionado? |
|---|---|---|---|
| `data/divisoes.csv` (Frente A) | Entrada | [contrato](../../docs/tarefas.md#divisoescsv-frente-a-versionado) | Sim |
| `data/interim/maccrobat/{casos,mencoes}.csv` (Frente A) | Entrada | exemplos few-shot, só `treino` | Não |
| `prompts/extracao.md`, `prompts/proposicoes.md` | Entrada | prompts | Sim |
| `data/interim/professor/mencoes_tipadas.csv` | Saída | [contrato de menções](../../docs/tarefas.md#menções-tipadas-contrato-de-project2datamencoes_tipadascsv), `fonte=llm:<modelo>` | Não |
| `data/interim/professor/alucinacoes.csv` | Saída | `case_id, texto, tipo, motivo` | Não |
| `data/interim/professor/execucao.csv` | Saída | chamadas, menções, alucinações, tokens, segundos e custo por caso | Não |
| `data/resultados/custo_professor.csv` | Saída | custo, tokens e tempo por caso | Sim |
| `data/resultados/quebra_frases.csv` | Saída | `direta` × `proposicoes` na validação | Sim |

`motivo`: `nao_encontrado` (alucinação), `tipo_invalido`, `texto_vazio` ou `item_invalido`.

## API

- `extrair_caso(case_id, texto, sistema, variante="direta")` → (menções, alucinações, estatísticas).
- `ancoragem.ancorar(texto, inicio, fim, itens)` → (menções com offsets, descartadas).
- `divisoes.ler_divisoes()` → `{case_id: particao}`; `garantir_fora_do_teste(ids, particoes)` falha se houver caso de teste.

## Resultados

`claude-sonnet-5-5` via `claude_cli`, zero-shot, 38 casos de treino
([`custo_professor.csv`](../../data/resultados/custo_professor.csv)): 86,2 menções e US$ 0,048
estimados por caso (US$ 48 por 1000 casos), 22,6 s por caso, 1 alucinação em 3.275 menções.

Quebra de frases, 10 casos de validação ([`quebra_frases.csv`](../../data/resultados/quebra_frases.csv)):
a variante `proposicoes` custa 70% mais e concorda com a direta em F1 0,90 (exato), sem
menos alucinação. Sem gabarito de validação, a direta fica como padrão.

## Limitações

- Sem `divisoes.csv`, usa uma divisão provisória: gold = `teste`, 1 em cada 5 artigos em `validacao`.
- Sem MACCROBAT, roda zero-shot; o silver do P2 só entra com `--exemplos`.
- `comparar` só mede F1 se houver anotação de casos de `validacao`; sem ela, compara contagem,
  alucinação, custo e a concordância entre as variantes.
- `confianca` fica vazia: o LLM não dá probabilidade por menção.
