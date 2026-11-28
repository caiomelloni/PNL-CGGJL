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
python -m project3.src.aluno.aluno treinar         # models/aluno/bert/ (~3 min no MPS)
python -m project3.src.aluno.aluno curva           # data/resultados/curva_aluno.csv (~8 min)
python -m project3.src.aluno.aluno prever --todos  # data/interim/aluno/mencoes_tipadas.csv
python -m unittest project3.tests.test_aluno
~~~

`--corpus <arquivos de casos…>` (antes do subcomando) troca a amostra do P1 + MACCROBAT por outros
corpora, como o MultiCaRe completo. `prever` também grava `data/interim/aluno/resumo.json` (tempo por caso). O BioBERT
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

Treinado com os rótulos do professor nos 39 casos de `treino` e medido contra o gabarito humano dos
30 documentos de `validacao` do MACCROBAT ([`curva_aluno.csv`](../../data/resultados/curva_aluno.csv)):

| Modelo | F1 exato | F1 sobreposição | Acerto de tipo | F1 `absent` |
|---|---|---|---|---|
| CRF | 0,43 | 0,70 | 0,36 | 0,49 |
| BERT | 0,57 | 0,82 | 0,58 | 0,69 |

O BERT chega perto do próprio professor nessa validação (F1 exato 0,60) e prevê ~0,13 s por caso,
contra 12,9 s do professor ([`extracao.csv`](../../data/resultados/extracao.csv)). De 50% para 100% dos
rótulos o F1 exato estabiliza; só tipo e `absent` ainda sobem um pouco.

## Limitações

- BIO plano: entre menções sobrepostas fica a mais longa (o professor já evita sobreposição).
- Hiperparâmetros fixos (CRF `c1`/`c2`; BERT 8 épocas, taxa 5e-5), para não ajustar na validação da curva.
- Casos de treino em que o professor não achou nenhuma menção ficam de fora do treino.
- A curva é medida no MACCROBAT, e não no MultiCaRe: a amostra tem só 2 casos de `validacao` na
  divisão oficial. As convenções de anotação do MACCROBAT (sem `Finding`) puxam os números para baixo.
