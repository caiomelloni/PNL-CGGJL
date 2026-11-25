# Normalização MeSH — Etapa 5 (Frente C, Lucas)

Liga cada menção tipada a um código MeSH (ou `ANATnnn` do gazetteer anatômico do P1). O léxico do P2
responde primeiro, com casamento exato e siglas definidas no caso. O que ele não conhece vai para o
vizinho mais próximo no espaço de embeddings do [SapBERT](https://huggingface.co/cambridgeltl/SapBERT-from-PubMedBERT-fulltext),
que junta sinônimos como `heart attack` e `myocardial infarction`.

## Como rodar

Da raiz do repositório:

```bash
pip install -r project3/src/normalizacao/requirements.txt
python -m project3.src.normalizacao.normalizacao indice      # ~3 min na GPU; baixa o SapBERT
python -m project3.src.normalizacao.normalizacao calibrar    # ~1 min; regrava limiar.json
python -m project3.src.normalizacao.normalizacao csv --entrada project2/data/mencoes_tipadas.csv \
    --saida project3/data/interim/mencoes_normalizadas.csv --corpus project1/data/case_texts.csv
python -m project3.src.normalizacao.comparar                 # tabela no gold do P2
python -m unittest discover -s project3/src/normalizacao/tests -t .
```

`calibrar` só é necessário se o índice ou o modelo mudar: o `limiar.json` versionado já tem o valor.
Opções do `csv`: `--metodo sapbert` (sem o léxico), `--filtrar-tipo`, `--limiar`.

## Entradas e saídas

| Arquivo | Entrada/Saída | Colunas | Versionado? |
|---|---|---|---|
| `project1/src/dicionarios/gazetteer/{mesh,anatomical_site}_gazetteer.csv` | entrada | `term, code, preferred_term, category` | sim (P1) |
| qualquer CSV de [menções tipadas](../../docs/tarefas.md#menções-tipadas-contrato-de-project2datamencoes_tipadascsv) | entrada | contrato + `case_id, texto, tipo` obrigatórias | — |
| CSV de saída do `csv` | saída | as mesmas colunas, `mesh` reescrito, mais `mesh_score` | não |
| `data/processed/indice_mesh/` | saída de `indice` | `vetores.npy`, `termos.csv`, `info.json` (171 305 termos) | não |
| `src/normalizacao/limiar.json` | saída de `calibrar` | limiar e acurácia na validação | sim |
| `data/resultados/normalizacao_calibracao.csv` | saída de `calibrar` | `faixa_inicio, faixa_fim, sinonimos, acuracia` | sim |
| `data/resultados/normalizacao.csv` | saída de `comparar` | `sistema, grupo, mencoes, com_codigo_previsto, acertos, acuracia, precisao, cobertura, acuracia_hier` | sim |

`mesh_score` vale 1.0 quando o código veio do léxico e a similaridade de cosseno do SapBERT nos
outros casos. Ele vem preenchido mesmo quando o `mesh` fica vazio, por estar abaixo do limiar.

## API

```python
from project3.src.normalizacao.normalizacao import normalizar, vizinhos

normalizar(textos, tipos=None, *, metodo="lexico+sapbert", textos_caso=None,
           limiar=None, filtrar_tipo=False) -> list[tuple[str, float]]   # (código ou "", score)
vizinhos(textos, k=1) -> list[list[Vizinho]]   # os k termos mais parecidos (codigo, termo, score…)
```

A frente D usa `normalizar([rótulo do LLM, ...])` para dar código aos diagnósticos sugeridos.

## Resultados

Limiar **0,78**, escolhido sem o gold. O método esconde do índice 5 000 sinônimos do MeSH, junto
com as variantes que têm as mesmas palavras, e pega o ponto abaixo do qual o vizinho mais próximo
erra mais do que acerta ([curva](../../data/resultados/normalizacao_calibracao.csv)).

Acurácia de código nas 130 menções do gold do P2 que têm código ([tabela](../../data/resultados/normalizacao.csv)):

| Sistema | Acurácia | Acurácia hierárquica | Precisão | Cobertura |
|---|---|---|---|---|
| léxico do P2 | 0,885 | 0,892 | 0,966 | 0,915 |
| SapBERT | 0,646 | 0,677 | 0,824 | 0,785 |
| **léxico do P2 + SapBERT** (padrão) | **0,915** | **0,923** | 0,952 | 0,962 |

A acurácia hierárquica também aceita o pai ou o filho direto na árvore MeSH. Para essa coluna, o
`comparar` precisa da árvore gerada pelo [`avaliacao_diagnostico`](../avaliacao_diagnostico/README.md#como-rodar).

## Limitações

- O padrão `lexico+sapbert` foi escolhido **depois** de ver a tabela acima, ou seja, é uma
  seleção feita no conjunto de teste. O limiar não foi.
- Os códigos do gold seguem a convenção do léxico, que é o código da palavra principal ("Chest X-rays" →
  Chest). Isso favorece o léxico e pune o SapBERT quando ele acerta um conceito mais específico ("fall in
  blood pressure" → Hypotension). O crédito hierárquico recupera pouco disso (+0,03 no SapBERT),
  porque esses conceitos costumam ficar em outro ramo da árvore, e não no pai ou no filho.
- Conceitos suplementares do MeSH (`C…`) não estão no gazetteer. Nenhum sistema chega a eles.
- O SapBERT dá código a 37% das menções que o gold deixa sem código, por exemplo em `ExamResult` e `Outcome`.
- O `--filtrar-tipo` não mudou a acurácia no gold.
