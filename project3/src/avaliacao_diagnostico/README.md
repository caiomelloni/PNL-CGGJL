# Avaliação do diagnóstico — Etapa 8 (Frente C, Lucas)

Mede o ajudante de diagnóstico. Para cada caso de teste, verifica se algum código certo aparece
entre as 5 sugestões de cada sistema da frente D (top-1, top-3, top-5 e MRR). Também verifica
que nada do diagnóstico vazou para a consulta ou para os casos citados como fonte.

## Como rodar

Da raiz do repositório:

```bash
curl -L -o project3/data/external/mesh/desc2026.xml --create-dirs \
    https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc2026.xml   # ~300 MB, uma vez
python -m project3.src.avaliacao_diagnostico.arvore          # árvore MeSH para o acerto hierárquico
python -m project3.src.avaliacao_diagnostico.avaliar         # lê predicoes.csv da frente D
python -m unittest discover -s project3/src/avaliacao_diagnostico/tests -t .
```

Análise de memorização (regra 5 de [`vazamento-de-dados.md`](../../docs/vazamento-de-dados.md)):
`avaliar --metadados <csv com article_id e year> --corte <ano de corte do LLM>`. Outras opções:
`--predicoes`, `--grafos`, `--divisoes`, `--arvore` e `--saida`.

## Entradas e saídas

| Arquivo | Entrada/Saída | Colunas | Versionado? |
|---|---|---|---|
| `data/processed/diagnostico/predicoes.csv` | entrada (frente D) | [contrato](../../docs/tarefas.md#predições-de-diagnóstico-frente-d--frente-c) | não |
| `data/processed/grafo/aluno/` (sem ele, `project2/data/grafo/`) | entrada | `<case_id>-nodes.csv` | não |
| `data/divisoes.csv` (sem ele, os 8 casos do gold do P2) | entrada (frente A) | `fonte, case_id, article_id, particao` | sim |
| `data/external/mesh/desc2026.xml` | entrada (NLM) | descritores do MeSH | não |
| `data/processed/mesh_arvore.csv` | saída de `arvore` | `code, preferred_term, tree_numbers` | não |
| `data/resultados/diagnostico.csv` | saída de `avaliar` | `grupo, sistema, casos, casos_sem_predicao, top1, top3, top5, mrr, top1_hier, …, mrr_hier` | sim |

Resposta certa de um caso: os códigos dos nós `Diagnosis` do grafo dele, sem os negados. Só entram
os casos de teste com pelo menos um desses códigos. Um caso sem predição conta como erro. As colunas
`_hier` aceitam também o pai ou o filho direto na árvore MeSH e nunca se misturam às exatas.

## API

```python
from project3.src.avaliacao_diagnostico import avaliar, vazamento

avaliar.avaliar(predicoes, certos, arvore=None) -> list[dict]        # uma linha de métricas por sistema
vazamento.problemas_da_consulta(consulta, nodes) -> list[str]        # tipo proibido ou diagnóstico na consulta
vazamento.problemas_das_fontes(predicoes, artigos=None) -> list[str] # fonte do mesmo artigo do caso testado
```

O `avaliar` **para com erro** se alguma sugestão citar um caso do mesmo artigo. Os testes de
integração em `tests/test_vazamento.py` rodam `montar_consulta` (frente D) em todos os grafos e checam o
`predicoes.csv` real. Eles ficam pulados enquanto esses arquivos não existem.

## Resultados

Ainda não há números: falta o `predicoes.csv` da frente D. Com os grafos do P2, só 2 dos 8 casos do
gold têm um `Diagnosis` com código.

## Limitações

- Até sair o `divisoes.csv` e o grafo do aluno, o conjunto de teste tem 2 casos.
- A resposta certa vem do grafo extraído, não de uma anotação manual, então erros da extração
  viram erros do gabarito. Por exemplo, no P2 o caso de tuberculose PMC3437073_01 tem como
  diagnóstico só Granuloma.
- A análise por ano depende de a frente A confirmar que `metadata.csv` tem o ano de publicação.
- O teste de nome na consulta casa palavras inteiras. Uma paráfrase do diagnóstico que não use
  o nome nem o código escapa.
