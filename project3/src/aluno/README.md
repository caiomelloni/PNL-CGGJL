# Aluno — Etapa 3 (Frente B, Caio)

Um CRF aprende a imitar o professor (destilação) e extrai o corpus inteiro sem custo de LLM. Usa as
mesmas pistas por palavra do CRF do P2 (`project2/src/entidades`), mas o rótulo de cada palavra
carrega tipo e polaridade (`B-Symptom-absent`), então ele sozinho gera menções tipadas no contrato.

## Como rodar

Pré-requisito: `pip install -r project2/src/entidades/requirements.txt` e as menções do professor
em `treino` e `validacao` ([`../professor/README.md`](../professor/README.md)). Da raiz do repositório:

~~~bash
python -m project3.src.aluno.aluno treinar                # models/aluno/crf.pkl
python -m project3.src.aluno.aluno curva                  # data/resultados/curva_aluno.csv
python -m project3.src.aluno.aluno prever --todos [--corpus <cases.csv do corpus completo>]
python -m unittest project3.tests.test_aluno
~~~

## Entradas e saídas

| Arquivo | Entrada/Saída | Colunas | Versionado? |
|---|---|---|---|
| `data/interim/professor/mencoes_tipadas.csv` | Entrada | contrato de menções; só `treino` treina | Não |
| `models/aluno/crf.pkl`, `metadados.json` | Saída | modelo e parâmetros | Não |
| `data/interim/aluno/mencoes_tipadas.csv` | Saída | [contrato de menções](../../docs/tarefas.md#menções-tipadas-contrato-de-project2datamencoes_tipadascsv), `fonte=aluno:crf-v1` | Não |
| `data/resultados/curva_aluno.csv` | Saída | `fracao, casos_treino, casos_validacao, f1_exato, f1_sobreposicao, acuracia_tipo, macro_f1_tipo, f1_absent` | Sim |

## API

- `treinar(casos, mencoes)` → CRF treinado; `casos_de_treino(particoes, mencoes, fracao)` falha se houver caso de teste.
- `prever_caso(crf, case_id, texto)` → menções no contrato; `confianca` = média da probabilidade do rótulo nas palavras da menção.

## Resultados

Pendente: depende das menções do professor. A curva sairá em [`curva_aluno.csv`](../../data/resultados/curva_aluno.csv),
medida na `validacao` contra os rótulos do professor.

## Limitações

- BIO plano: entre menções sobrepostas fica a mais longa (o sítio anatômico dentro de um achado se perde).
- `c1`/`c2` fixos, sem busca, para não ajustar na mesma validação da curva.
- Casos de treino em que o professor não achou nenhuma menção ficam de fora do treino.
- Sem a versão BERT, que fica para se houver tempo.
