# Avaliação da extração — Etapa 6 (Frente A, George)

Consolida a comparação entre `regras_p1`, `p2`, `professor` e `aluno` sobre o gabarito do P2 (`gold_p2`) e a partição `teste` do MACCROBAT (`maccrobat_teste`), reusando `project2.src.avaliacao.avaliar` e registrando alucinações, tempo e custo por caso.

## Como rodar

```bash
python -m project3.src.avaliacao.extracao avaliar
python -m unittest discover -s project3/tests -v
```

## Entradas e saídas

| Arquivo | Entrada/Saída | Colunas | Versionado? |
|---|---|---|---|
| `project2/data/gold/{mencoes,relacoes}.csv` | Entrada | contrato gold P2 | Sim |
| `project3/data/interim/maccrobat/mencoes.csv` | Entrada | [menções tipadas](../../docs/tarefas.md#menções-tipadas-contrato-de-project2datamencoes_tipadascsv) | Não |
| `project3/data/divisoes.csv` | Entrada | `fonte, case_id, article_id, particao` | Sim |
| `project3/data/interim/{professor,aluno}/mencoes_tipadas.csv` | Entrada (opcional) | contrato de menções tipadas | Não |
| `project3/data/resultados/extracao.csv` | Saída | métricas de menções, tipos, polaridade, relações, grafo + `alucinacoes`, `segundos_por_caso`, `custo_usd_por_caso` | Sim |

## API

- `extracao.avaliar_extracao(sistemas=None, ..., saida=...) -> list[dict]`: executa a avaliação completa e grava `extracao.csv`.
- `extracao.sistemas_padrao(raiz=REPO) -> list[SistemaConfig]`: retorna as configurações padrão de `regras_p1`, `p2`, `professor` e `aluno`.

## Resultados

- Baselines atuais em [extracao.csv](../../data/resultados/extracao.csv) (`gold_p2`, 8 casos, 224 menções):
  - `regras_p1`: F1 menções `0.1742` (exato) / `0.3345` (sobreposição); F1 relações `0.1032` / `0.3016`; `0` alucinações.
  - `p2`: F1 menções `0.0952` (exato) / `0.2063` (sobreposição); F1 relações `0.0909` / `0.2000`; `0` alucinações.

## Limitações

- `professor` e `aluno` entram automaticamente na tabela assim que a Frente B publicar seus CSVs em `project3/data/interim/{professor,aluno}/`.
- Em `maccrobat_teste`, relações ficam vazias porque as do MACCROBAT não correspondem às nossas; a polaridade vem dos atributos `POLARITY` do brat.
