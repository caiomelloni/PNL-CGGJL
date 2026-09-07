# 03 — Formato JSON do grafo

> **O que é.** O formato de saída do programa que lê um caso clínico e devolve o grafo, e o formato de entrada da interface web que desenha esse grafo.
> **Um arquivo por caso.** O esquema do grafo — quais tipos de nó e de aresta existem — está no [02](02-esquema-grafo.md); aqui é só como escrever isso em JSON.

---

## Em uma olhada

Um caso com um paciente, um sintoma e a aresta entre os dois:

```json
{
  "format_version": "1.0",
  "case": {
    "case_id": "PMC5137649_01",
    "article_id": "PMC5137649",
    "case_text": "A 44-year-old woman presented with a 3-day history of right flank and lower quadrant abdominal pain associated with nausea and constipation."
  },
  "nodes": [
    {
      "id": "PMC5137649_01:P1",
      "type": "Patient",
      "label": "44-year-old woman",
      "attributes": {
        "age": 44,
        "age_unit": "years",
        "gender": "Female"
      },
      "anchor": {
        "start": 0,
        "end": 19,
        "text": "A 44-year-old woman"
      }
    },
    {
      "id": "PMC5137649_01:S1",
      "type": "Symptom",
      "label": "abdominal pain",
      "attributes": {
        "polarity": "present",
        "duration": "3 days"
      },
      "anchor": {
        "start": 54,
        "end": 99,
        "text": "right flank and lower quadrant abdominal pain"
      }
    }
  ],
  "edges": [
    {
      "id": "PMC5137649_01:e01",
      "source": "PMC5137649_01:P1",
      "target": "PMC5137649_01:S1",
      "relation": "HAS_SYMPTOM",
      "attributes": {
        "trigger": "presented with",
        "certainty": "asserted"
      },
      "anchor": {
        "start": 0,
        "end": 99,
        "text": "A 44-year-old woman presented with a 3-day history of right flank and lower quadrant abdominal pain"
      }
    }
  ]
}
```

Três blocos no topo, sempre nessa ordem:

| Bloco | O que guarda |
|---|---|
| `format_version` | Versão deste formato. Hoje `"1.0"`. A interface deve recusar o que não reconhece. |
| `case` | O texto do caso e sua identificação. |
| `nodes` | Os nós do grafo. |
| `edges` | As arestas. |

---

## `case`

| Campo | Tipo | Descrição |
|---|---|---|
| `case_id` | string | Identificador do caso, padrão `PMC<dígitos>_<NN>`. |
| `article_id` | string | PMCID do artigo de origem, padrão `PMC<dígitos>`. |
| `case_text` | string | O texto integral do caso, exatamente como veio de `cases.csv`. |

**Por que o texto vai junto.** Todo nó e toda aresta apontam para um trecho do `case_text` por posição de caractere. Sem o texto no mesmo arquivo, essas posições não significam nada e a interface não consegue destacar a evidência. É o que permite clicar num nó e ver de onde ele saiu.

---

## `nodes`

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `id` | string | ✅ | Único no arquivo. Convenção: `<case_id>:<letra><n>` — `PMC5137649_01:S1`. |
| `type` | string | ✅ | Um dos 12 tipos do [02](02-esquema-grafo.md). |
| `label` | string | ✅ | O nome normalizado. É o que a interface escreve dentro do nó. |
| `attributes` | objeto | ✅ | As propriedades do tipo. `{}` quando não há nenhuma. |
| `anchor` | objeto \| `null` | ✅ | O trecho que originou o nó. `null` só em `Concept`. |
| `mentions` | lista | ⬜ | Só quando a entidade aparece mais de uma vez. Ver abaixo. |

Os 12 tipos: `Patient`, `Symptom`, `History`, `Exam`, `ExamResult`, `Finding`, `Diagnosis`, `Medication`, `Treatment`, `AnatomicalSite`, `Outcome`, `Concept`.

**`attributes` nunca tem chave nula.** Se o texto não informa a duração de um sintoma, a chave `duration` simplesmente não aparece — em vez de `"duration": null`. Para quem consome: chave ausente e chave nula significariam a mesma coisa, e uma delas basta. Quais chaves cada tipo aceita está no [01 §1](01-dados-a-extrair.md#1-entidades), que também lista os valores admissíveis das chaves de domínio fechado.

**`mentions`** existe porque a mesma entidade costuma ser citada várias vezes (`stomach` aparece 7 vezes no exemplo completo) e vira **um** nó só. Quando isso acontece, `anchor` é a primeira menção e `mentions` traz **todas**, na ordem do texto, inclusive a primeira. Assim a interface consegue destacar todas as ocorrências de um nó de uma vez. Quando há uma menção só, `mentions` é omitido.

---

## `edges`

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `id` | string | ✅ | Único no arquivo. Convenção: `<case_id>:e<nn>`. |
| `source` | string | ✅ | `id` do nó de origem. |
| `target` | string | ✅ | `id` do nó de destino. |
| `relation` | string | ✅ | Uma das 13 relações da tabela abaixo. |
| `attributes` | objeto | ✅ | `trigger` e `certainty`; em `SAME_AS`, `score` e `method`. |
| `anchor` | objeto \| `null` | ✅ | O trecho que evidencia a relação. `null` só em `SAME_AS`. |

O grafo é **dirigido**: `source` e `target` não são intercambiáveis. Cada relação só aceita certos tipos nas pontas:

| `relation` | `source.type` | `target.type` |
|---|---|---|
| `HAS_SYMPTOM` | `Patient` | `Symptom` |
| `HAS_HISTORY` | `Patient` | `History` |
| `HAS_FINDING` | `Patient` | `Finding` |
| `UNDERWENT_EXAM` | `Patient` | `Exam` |
| `HAS_RESULT` | `Exam` | `ExamResult` |
| `REVEALS` | `Exam`, `Treatment` | `Finding` |
| `SUPPORTS` | `Symptom`, `Finding`, `ExamResult`, `History` | `Diagnosis` |
| `DIAGNOSED_WITH` | `Patient` | `Diagnosis` |
| `TREATED_WITH` | `Patient`, `Diagnosis` | `Treatment`, `Medication` |
| `LOCATED_IN` | `Symptom`, `Finding`, `Treatment` | `AnatomicalSite` |
| `HAS_OUTCOME` | `Patient` | `Outcome` |
| `REVISES` | `Diagnosis` | `Diagnosis` |
| `SAME_AS` | 7 tipos (ver [02](02-esquema-grafo.md)) | `Concept` |

Atributos das arestas:

| Chave | Valores | Descrição |
|---|---|---|
| `trigger` | texto | A marca lexical que fez o parser criar a relação — `presented with`, `underwent`. Útil para depurar a extração. |
| `certainty` | `asserted` \| `hedged` | Se o texto afirma a relação ou apenas a sugere (`suggesting`, `consistent with`). |
| `score` | 0 a 1 | Só em `SAME_AS`: confiança do casamento com o vocabulário. |
| `method` | texto | Só em `SAME_AS`: como o casamento foi obtido. |

---

## `anchor` — como a interface destaca o texto

```json
{ "start": 54, "end": 99, "text": "right flank and lower quadrant abdominal pain" }
```

- `start` e `end` são posições de caractere no `case_text`, **intervalo semiaberto**: `start` entra, `end` não. É a mesma convenção de `str[a:b]` em Python e de `String.slice(a, b)` em JavaScript, então recortar o trecho é direto:

  ```js
  const t = data.case.case_text.slice(node.anchor.start, node.anchor.end);
  // t === node.anchor.text, sempre
  ```

- `text` é redundante de propósito: guardar o trecho junto do offset deixa o arquivo legível por humanos e transforma "o offset está certo?" numa comparação de uma linha. É a checagem mais barata que pega o erro mais comum, que é offset deslocado por normalização de texto.

- **Uma pegadinha para a interface web.** As posições contam *code points* (é o que Python usa), enquanto o `.slice()` do JavaScript conta *unidades UTF-16*. Os dois coincidem em todo caractere do plano básico — inclusive `×`, `–` e acentuados —, e divergiriam só diante de caracteres fora dele, como emoji, que não esperamos em texto clínico. Se aparecer, o `text` denuncia na hora, porque a comparação acima falha.

- `anchor` é `null` só onde não há texto de onde ancorar: nós `Concept`, que não vêm do caso, e as arestas `SAME_AS`, que ligam a eles.

---

## Regras que o parser precisa garantir

O JSON Schema (abaixo) cobre a **forma** do arquivo. Estas seis regras são sobre a **coerência** dele, e nenhuma dá para expressar em JSON Schema:

1. Todo `id` é único dentro do arquivo — entre nós e entre arestas.
2. Todo `source` e todo `target` existem em `nodes`.
3. Toda âncora satisfaz `case_text[start:end] == text`.
4. Existe **exatamente um** nó `Patient`.
5. Nenhum nó fica solto: todo nó, exceto `Concept`, se liga ao `Patient` por algum caminho, ignorando a direção das setas.
6. Toda aresta respeita a tabela de `source.type` → `target.type`.

Vale ainda combinar a **ordem**, para que a interface renderize sempre igual: `nodes` na ordem da primeira menção no texto, `edges` na ordem em que as relações aparecem.

---

## Validando um arquivo

A forma, com o JSON Schema em [`schema/grafo-caso.schema.json`](schema/grafo-caso.schema.json):

```python
import json, jsonschema

schema = json.load(open("docs/schema/grafo-caso.schema.json"))
grafo  = json.load(open("saida/PMC5137649_01.json"))
jsonschema.Draft202012Validator(schema).validate(grafo)
```

A coerência: as quatro primeiras regras cabem em poucas linhas. A 5 (nó solto) pede uma travessia do grafo a partir do `Patient`, e a 6 (combinação de tipos), a tabela de `source.type` → `target.type` em código.

```python
t   = grafo["case"]["case_text"]
ids = {n["id"] for n in grafo["nodes"]}

assert len(ids) == len(grafo["nodes"]), "id de nó repetido"
assert len({e["id"] for e in grafo["edges"]}) == len(grafo["edges"]), "id de aresta repetido"
assert sum(n["type"] == "Patient" for n in grafo["nodes"]) == 1, "precisa de um Patient"

for x in grafo["nodes"] + grafo["edges"]:
    for a in ([x["anchor"]] if x["anchor"] else []) + x.get("mentions", []):
        assert t[a["start"]:a["end"]] == a["text"], f"âncora errada em {x['id']}"

for e in grafo["edges"]:
    assert e["source"] in ids and e["target"] in ids, f"id solto em {e['id']}"
```

O `id` do nó ou da aresta em toda mensagem de erro é de propósito: é o que permite achar o problema no arquivo sem procurar.

---

## Arquivos

| Arquivo | Para quê |
|---|---|
| [`schema/grafo-caso.schema.json`](schema/grafo-caso.schema.json) | O contrato em JSON Schema (draft 2020-12), para validar a saída do parser em teste. |
| [`exemplos/PMC5137649_01.json`](exemplos/PMC5137649_01.json) | Um caso real inteiro neste formato — 52 nós e 61 arestas, feito à mão. Serve de alvo para o parser e de dado de teste para a interface antes de o parser existir. |

O schema é **gerado a partir das tabelas do [01](01-dados-a-extrair.md)**, para que os domínios fechados não virem duas fontes de verdade que divergem. Mexeu nas tabelas do 01, o schema precisa ser regerado.

---

## Vários casos

Um arquivo por caso, nomeado `<case_id>.json`. Para processar a amostra inteira, um diretório com os 56 arquivos — não um arquivo só com tudo dentro. Assim a interface carrega um caso sem ler os outros, um caso com erro não invalida o lote, e o `git diff` de uma reextração mostra só o que mudou.
