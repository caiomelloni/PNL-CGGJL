# Aluno — Etapa 3 (Frente B, Caio)

Um modelo pequeno aprende a imitar o professor (destilação) e extrai o corpus inteiro sem custo de
LLM. O rótulo de cada palavra carrega tipo e polaridade (`B-Symptom-absent`), então o aluno sozinho
gera menções tipadas no contrato. Dois modelos com a mesma rotulagem: um BioBERT (padrão) e o CRF do
P2 (`project2/src/entidades`).

## Como rodar

Pré-requisitos: `pip install -r project2/src/entidades/requirements.txt -r project3/src/aluno/requirements.txt`
as menções do professor em `treino` ([`../professor/README.md`](../professor/README.md)) e, para a
`curva`, o MACCROBAT convertido (`project3/src/dados/maccrobat.py`).
Da raiz do repositório (`--modelo crf` antes do subcomando troca para o CRF):

~~~bash
python -m project3.src.aluno.aluno treinar         # models/aluno/bert/ (~8 min no MPS com 99 casos)
python -m project3.src.aluno.aluno curva           # data/resultados/curva_aluno.csv (~15 min)
python -m project3.src.aluno.aluno prever --todos  # data/interim/aluno/mencoes_tipadas.csv
python -m unittest project3.tests.test_aluno
~~~

`--corpus <arquivos de casos…>` (antes do subcomando) troca a amostra do P1 + MACCROBAT por outros
corpora, como o MultiCaRe completo: `treinar` e `curva` precisam dele para os casos de treino que não
estão na amostra (passe a amostra primeiro, depois `project2/data/corpus/csv/full/cases.csv` e o
MACCROBAT). Em `prever`, não passe o corpus completo: ele preveria os ~20 mil casos de teste e
validação. `prever` também grava `data/interim/aluno/resumo.json` (tempo por caso). O BioBERT
(`dmis-lab/biobert-base-cased-v1.2`) é baixado do Hugging Face no primeiro `treinar`.

## Entradas e saídas

| Arquivo | Entrada/Saída | Colunas | Versionado? |
|---|---|---|---|
| `data/interim/professor/mencoes_tipadas.csv` | Entrada | contrato de menções; só `treino` treina | Não |
| `models/aluno/{bert,crf}/` | Saída | modelo e `metadados.json` | Não |
| `data/interim/aluno/mencoes_tipadas.csv` | Saída | [contrato de menções](../../docs/tarefas.md#menções-tipadas-contrato-de-project2datamencoes_tipadascsv), `fonte=aluno:bert-v1` ou `aluno:crf-v1` | Não |
| `data/resultados/curva_aluno.csv` | Saída | `modelo, fracao, casos_treino, casos_validacao, f1_exato, f1_sobreposicao, acuracia_tipo, macro_f1_tipo, f1_absent` | Sim |

## API

- `modelo_aluno("bert"|"crf")` → módulo com `treinar(casos, mencoes)`, `prever_caso(modelo, case_id, texto)`,
  `salvar(modelo, pasta)` e `carregar(pasta)`.
- `casos_de_treino(particoes, mencoes, fracao)` → casos de `treino`; falha se houver caso de teste.
- `confianca` de cada menção = média da probabilidade do rótulo escolhido nas suas palavras.

## Resultados

Treinado com os rótulos do professor em 99 casos de `treino` (dos N = 100 da
[rodada do professor](../professor/README.md#rodada-da-destilação-um-subconjunto-não-o-corpus-inteiro);
um caso sem menção fica de fora) e medido contra o gabarito humano dos 30 documentos de `validacao`
do MACCROBAT ([`curva_aluno.csv`](../../data/resultados/curva_aluno.csv)):

| Modelo | Casos | F1 exato | F1 sobreposição | Acerto de tipo | F1 `absent` |
|---|---|---|---|---|---|
| CRF | 10 | 0,37 | 0,67 | 0,29 | 0,32 |
| CRF | 99 | 0,49 | 0,77 | 0,43 | 0,57 |
| BERT | 10 | 0,55 | 0,81 | 0,57 | 0,43 |
| BERT | 25 | 0,56 | 0,82 | 0,57 | 0,71 |
| BERT | 99 | 0,58 | 0,83 | 0,58 | 0,73 |

O BERT chega perto do próprio professor nessa validação (F1 exato 0,60) e quase não melhora acima de
25 casos; o CRF ainda sobe com 99. Mais rótulos do professor não devem mudar muito o aluno.

Processamento (MacBook, GPU MPS): treinar o BERT com 99 casos levou 7,5 min, e o CRF 36 s; a curva
levou 14 min (BERT) e 1 min (CRF). O BERT prevê ~0,13 s por caso, contra ~34 s do professor: o
`teste` inteiro do MultiCaRe (~10 mil casos) sai em ~21 min, sem custo de LLM. No gold do P2, o aluno
tem F1 exato 0,58, contra 0,61 do professor ([`extracao.csv`](../../data/resultados/extracao.csv)).

## Limitações

- BIO plano: entre menções sobrepostas fica a mais longa (o professor já evita sobreposição).
- Hiperparâmetros fixos (CRF `c1`/`c2`; BERT 8 épocas, taxa 5e-5), para não ajustar na validação da curva.
- Casos de treino em que o professor não achou nenhuma menção ficam de fora do treino.
- A curva é medida no MACCROBAT, e não no MultiCaRe: a amostra tem só 2 casos de `validacao` na
  divisão oficial. As convenções de anotação do MACCROBAT (sem `Finding`) puxam os números para baixo.
