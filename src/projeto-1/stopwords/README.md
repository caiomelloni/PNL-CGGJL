# Stop-words

Pipeline `case_text` → grafo de conhecimento (issue #5), e o experimento que decide se, onde e com
qual lista aplicar remoção de stop-words. Ver a decisão completa em
[docs/projeto-1/05-stopwords.md](../../../docs/projeto-1/05-stopwords.md).

## Estrutura

- `core/`: modelos (`Node`, `Edge`) e `GraphBuilder` (dedup, ids);
- `extractors/`: um módulo por entidade + `relations.py` para as 12 arestas;
- `lexicon/`: as 4 listas versionadas (`data/`) + `masking.py`/`label_cleaning.py`/`loader.py`;
- `exporters/`: exportação CSV;
- `experiment/`: as 4 condições, o diff por conteúdo, o runner e o relatório agregado;
- `tests/`: `unittest`, espelhando a estrutura acima;
- `output/`: nodes/edges csv dos 56 casos da amostra, na configuração final decidida;
- `experiment_output/`: `summary.csv`/`.json` e as tabelas do caso mais dramático.

## Execução

A partir da raiz do repositório:

```bash
cd src/projeto-1
python3 -m stopwords --cases ../../sample/cases.csv --case-id PMC5137649_01
python3 -m stopwords --cases ../../sample/cases.csv --all-cases --output stopwords/output
```

`--condition` aceita `BASELINE` (padrão), `NAIVE_UNPROTECTED`, `GUARDED_GLOBAL`, `GUARDED_LABEL`.
`--wordlist` aceita `nltk_stopwords`, `spacy_stopwords`, `custom_clinical` — obrigatório para
qualquer condição além de `BASELINE`.

## Testes

```bash
cd src/projeto-1
python3 -m unittest discover -s stopwords/tests -t . -p "test_*.py"
```
