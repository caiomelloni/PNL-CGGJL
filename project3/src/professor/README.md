# Professor — Etapa 2 (Frente B, Caio)

Um LLM extrai menções tipadas (`tipo` e `polaridade`) dos casos. Cada caso é cortado em trechos de
frases inteiras; o LLM devolve o texto de cada menção, e a ancoragem acha esse texto no trecho para
calcular `start`/`end`. O que não existe no texto é descartado e contado como alucinação.

## Como rodar

Pré-requisito: cliente LLM configurado ([`../llm/README.md`](../llm/README.md)). Da raiz do repositório:

~~~bash
python -m project3.src.professor.professor custo --n 50          # mede o custo e define N
python -m project3.src.professor.professor rodar --n-treino N [--n-validacao N]   # teste + validação + N de treino
python -m project3.src.professor.professor comparar --gold project3/data/interim/maccrobat/mencoes.csv        # direta × proposições
python -m project3.src.professor.professor exemplos --gold project3/data/interim/maccrobat/mencoes.csv        # zero-shot × few-shot
python -m unittest project3.tests.test_professor
~~~

Opções globais (antes do subcomando): `--corpus <arquivos de casos…>` (padrão: amostra do P1 e, se
convertido, o MACCROBAT), `--modelo` e `--exemplos maccrobat|nenhum|<csv>` (padrão: `maccrobat`). Só entram casos
presentes nos corpora. Rodar de novo é barato: o que já foi perguntado vem do cache.

A rodada da destilação (N = 100, abaixo) usou o MultiCaRe completo
(`python -m project2.src.comum.coletar --registro 20416562`, ~190 MB) para ter casos de treino além da amostra:

~~~bash
export P3_LLM_PROVEDOR=claude_cli   # sem isso o padrão é a API paga da Anthropic
python -m project3.src.professor.professor \
  --corpus project1/data/case_texts.csv project2/data/corpus/csv/full/cases.csv project3/data/interim/maccrobat/casos.csv \
  --exemplos maccrobat rodar --n-treino 100 --n-teste 15 --n-validacao 2
~~~

Caso repetido entre corpora vale o do primeiro arquivo, e em cada partição os casos do primeiro
corpus (a amostra) vêm antes dos outros. Por isso `--n-teste 15 --n-validacao 2` são exatamente os
casos da amostra, e os 100 de treino são os 39 da amostra mais 61 do corpus completo, na ordem fixa.
`--exemplos maccrobat` está ali só para separar a lista de `--corpus` do subcomando.

## Entradas e saídas

| Arquivo | Entrada/Saída | Colunas | Versionado? |
|---|---|---|---|
| `data/divisoes.csv` (Frente A) | Entrada | [contrato](../../docs/tarefas.md#divisoescsv-frente-a-versionado) | Sim |
| `data/interim/maccrobat/{casos,mencoes}.csv` (Frente A) | Entrada | casos extras; gabarito de `validacao`; few-shot opcional (só `treino`) | Não |
| `prompts/extracao.md`, `prompts/proposicoes.md` | Entrada | prompts | Sim |
| `data/interim/professor/mencoes_tipadas.csv` | Saída | [contrato de menções](../../docs/tarefas.md#menções-tipadas-contrato-de-project2datamencoes_tipadascsv), `fonte=llm:<modelo>` | Não |
| `data/interim/professor/alucinacoes.csv` | Saída | `case_id, texto, tipo, motivo` | Não |
| `data/interim/professor/execucao.csv` | Saída | chamadas, menções, alucinações, tokens, segundos e custo por caso | Não |
| `data/resultados/custo_professor.csv` | Saída | custo, tokens e tempo por caso | Sim |
| `data/resultados/quebra_frases.csv` | Saída | `direta` × `proposicoes` na validação | Sim |
| `data/resultados/few_shot.csv` | Saída | zero-shot × few-shot do MACCROBAT na validação | Sim |

`motivo`: `nao_encontrado` (alucinação), `tipo_invalido`, `texto_vazio` ou `item_invalido`.

## API

- `extrair_caso(case_id, texto, sistema, variante="direta")` → (menções, alucinações, estatísticas).
- `ancoragem.ancorar(texto, inicio, fim, itens)` → (menções com offsets, descartadas).
- `divisoes.ler_divisoes()` → `{case_id: particao}`; `garantir_fora_do_teste(ids, particoes)` falha se houver caso de teste.

## Resultados

`claude-sonnet-5-5` via `claude_cli`, zero-shot, 38 casos de treino
([`custo_professor.csv`](../../data/resultados/custo_professor.csv)): 86,2 menções e US$ 0,048
estimados por caso (US$ 48 por 1000 casos), 22,6 s por caso, 1 alucinação em 3.275 menções.

Na validação, contra o gabarito humano de 30 documentos do MACCROBAT:

| Configuração | F1 exato | F1 sobreposição | Acerto de tipo | F1 `absent` | US$/caso |
|---|---|---|---|---|---|
| zero-shot, direta | 0,572 | 0,829 | 0,566 | 0,726 | 0,061 |
| **few-shot, direta** (padrão) | **0,604** | **0,834** | **0,589** | **0,745** | 0,063 |
| zero-shot, proposições | 0,571 | 0,827 | 0,565 | 0,744 | 0,107 |

Fontes: [`few_shot.csv`](../../data/resultados/few_shot.csv) e [`quebra_frases.csv`](../../data/resultados/quebra_frases.csv).
Quebrar em proposições não melhora o F1 e custa 77% mais.

### Rodada da destilação: um subconjunto, não o corpus inteiro

O professor rodou em **117 casos**: os 15 de `teste` e os 2 de `validacao` da amostra, mais **N = 100
de `treino`**. Não rodou nos ~10 mil casos de `teste` nem nos ~79 mil de `treino` do MultiCaRe: no
custo medido, isso passaria de US$ 600 e 90 h só para o teste. O aluno aprende com esses 100 casos e
é ele quem processa o resto do corpus. A curva do aluno
([`../aluno/README.md`](../aluno/README.md#resultados)) mostra que o BERT quase não melhora acima de
25 casos, então a falta de mais rótulos do professor não deve ser o gargalo.

Custo da rodada (`claude-sonnet-5-5` via `claude_cli`, few-shot, em 28/11/2026; só chamadas novas, o
resto veio do cache):

| Medida | Valor |
|---|---|
| Casos com chamadas novas | 100 (todos de `treino`) |
| Chamadas ao LLM | 336 |
| Tokens | 2,15 M de entrada + 0,49 M de saída (~21,6 mil + 4,9 mil por caso) |
| Custo | US$ 6,42 equivalentes na API, **pagos com a cota da assinatura** (sem gasto em dinheiro) |
| Tempo | 56 min de LLM (~34 s por caso), em série |
| Menções | 10.823 nos 117 casos (92,5 por caso), 0 alucinações, 0 respostas inválidas |
| Extrapolação | US$ 0,064 e 34 s por caso: ~US$ 650 e ~94 h no `teste` inteiro do MultiCaRe |

No gold do P2 (8 casos de `teste`), o professor tem F1 exato 0,61 e sobreposição 0,65
([`extracao.csv`](../../data/resultados/extracao.csv)).

## Limitações

- Sem `divisoes.csv`, usa uma divisão provisória: gold = `teste`, 1 em cada 5 artigos em `validacao`.
- Few-shot do MACCROBAT por padrão (melhor na [validação](../../data/resultados/few_shot.csv)), mas o
  MACCROBAT segue outra convenção de fronteira e não tem `Finding`; o ganho medido é contra o gabarito dele.
- `comparar` só mede F1 se houver anotação de casos de `validacao`; sem ela, compara contagem,
  alucinação, custo e a concordância entre as variantes.
- `confianca` fica vazia: o LLM não dá probabilidade por menção.
- Rótulos do professor só em 117 casos (100 de treino); o `teste` dele é o da amostra (15 casos, 8 com gold).
- O custo em US$ é o que a CLI informa como equivalente na API; com `claude_cli` ele consome cota
  da assinatura do Claude Code, não dinheiro.
