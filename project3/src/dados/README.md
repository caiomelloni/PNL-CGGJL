# Dados, divisões e grafo do corpus — Etapas 1 e 4 (Frente A, George)

Prepara os dois corpora do Projeto 3 (MultiCaRe completo e MACCROBAT convertido para o contrato do P2), gera a divisão fixa treino/validação/teste sem vazamento (`divisoes.csv`) e constrói os grafos do corpus em lotes com retomada.

## Como rodar

```bash
python -m project2.src.comum.coletar --registro 20416562
python -m project3.src.dados.maccrobat tudo
python -m project3.src.dados.divisoes gerar
python -m project3.src.dados.grafo_corpus gerar --mencoes project2/data/mencoes_tipadas.csv --corpus project2/data/corpus/csv/full/cases.csv --saida project3/data/processed/grafo/p2_amostra --tamanho-lote 20
python -m unittest discover -s project3/tests -v
```

*(Quando a Frente B gerar `project3/data/interim/aluno/mencoes_tipadas.csv`, rode `python -m project3.src.dados.grafo_corpus gerar` com os caminhos padrão.)*

## Entradas e saídas

| Arquivo | Entrada/Saída | Colunas | Versionado? |
|---|---|---|---|
| `project2/data/corpus/csv/full/{cases,metadata}.csv` | Entrada | contrato P2 (`metadata.csv` inclui `year`) | Não |
| `project3/src/dados/mapa_maccrobat.csv` | Entrada | `tipo_maccrobat, tipo_p3, observacao` | Sim |
| `project3/data/interim/maccrobat/{casos,mencoes}.csv` | Saída | [contratos](../../docs/tarefas.md#contratos) | Não |
| `project3/data/divisoes.csv` | Saída | `fonte, case_id, article_id, particao` | Sim |
| `project3/data/processed/grafo/aluno/<case_id>-{nodes,edges}.csv` | Saída | `NODE_COLUMNS`, `EDGE_COLUMNS` (P2) | Não |

## API

- `divisoes.carregar_divisoes(caminho=...) -> list[dict[str, str]]`: lê `divisoes.csv`.
- `divisoes.carregar_gold(caminho_gold=...) -> set[str]`: lê os 8 `case_id`s do gold do P2.
- `maccrobat.converter(entrada=..., saida=..., caminho_mapa=...) -> dict`: converte brat para CSV no contrato P2/P3.
- `grafo_corpus.gerar_grafos(mencoes=..., corpus=..., saida=..., tamanho_lote=500, ...) -> dict`: encadeia relações + montagem do P2 em lotes com retomada.

## Resultados

- **MultiCaRe v3.0.1** (Zenodo `20416562`): `98.641` casos em `76.137` artigos (`year` 100% preenchido, 1990–2026); todos os 8 casos gold em `teste` em [divisoes.csv](../../data/divisoes.csv).
- **MACCROBAT2020** (CC BY 4.0, DOI `10.6084/m9.figshare.9764942.v2`): `200` casos (`140` treino, `30` validação, `30` teste), `17.739` menções convertidas (`14` PMIDs comuns ao MultiCaRe sincronizados na mesma partição).
- Validação da etapa de avaliação em [extracao.csv](../../data/resultados/extracao.csv).

## Limitações

- MACCROBAT não separa `Finding` de `Sign_symptom` (`Finding` tem 0 ocorrências no MACCROBAT); negações (`POLARITY NEG`/`MAYBE_NEG` via `A` → `E` → `T`) são mapeadas para `absent` e as demais para `present`.
- `35` menções descontínuas (`;` nos offsets brat) são descartadas para manter `texto == case_text[start:end]`.
- Os grafos finais de `aluno/` dependem de `project3/data/interim/aluno/mencoes_tipadas.csv` (Frente B).
