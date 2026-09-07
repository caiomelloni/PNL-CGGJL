# 02 — Esquema do grafo de conhecimento

> Entregável da [issue #2](https://github.com/caiomelloni/PNL-CGGJL/issues/2) — Projeto 1 (MC896, 2026).
> A issue [#1](https://github.com/caiomelloni/PNL-CGGJL/issues/1) definiu **o que** extrair ([`01-dados-a-extrair.md`](01-dados-a-extrair.md)). Este documento define **como representar** o que foi extraído: o esquema das duas tabelas, o nível de decomposição do grafo, as convenções de identificador e a ancoragem no texto. **Como extrair** é assunto das issues [#3](https://github.com/caiomelloni/PNL-CGGJL/issues/3)–[#6](https://github.com/caiomelloni/PNL-CGGJL/issues/6).

O esquema abaixo é aplicado à mão a um caso real da amostra na [§9](#9-exemplo-aplicado--pmc5137649_01), que serve tanto de referência para a implementação quanto de teste do próprio esquema — a [§8](#8-ajustes-ao-doc-01-revelados-pela-aplicação) registra as três lacunas que essa aplicação revelou.

---

## 1. Resumo das decisões

| Questão em aberto | Decisão | Onde |
|---|---|---|
| Nível de decomposição | Híbrido, próximo do `example1`. Atributo só vira nó se passar no teste de três critérios da §3 — na prática só `AnatomicalSite` e `Concept` passam. Valor e unidade de exame **não** viram nós. | [§3](#3-nível-de-decomposição) |
| Colunas das tabelas | As do enunciado, mais `case_id` e a ancoragem (`char_start`, `char_end`, `mention`/`evidence_text`) promovidas a colunas próprias. | [§2](#2-esquema-das-colunas) |
| Serialização de `attributes` | **JSON** de um nível, não `chave=valor;`. | [§2.3](#23-serialização-de-attributes) |
| Escopo dos `node_id` | Únicos globalmente, por construção: prefixados pelo `case_id`. Nós **não** são compartilhados entre casos — `Hypertension` em dois casos são dois nós. | [§6](#6-convenção-de-identificadores) |
| Ancoragem no texto | Guardamos **offsets e trecho**, nas arestas **e nos nós**. | [§7](#7-ancoragem-no-texto) |
| `SAME_AS` / vocabulários | Previstos no esquema: tipo de nó `Concept` (o único global) e relação `SAME_AS`. Opcionais; quais vocabulários é decisão da [#6](https://github.com/caiomelloni/PNL-CGGJL/issues/6). | [§5.3](#53-same_as-e-o-tipo-concept) |

---

## 2. Esquema das colunas

O enunciado sugere `node_id, type, label, attributes` e `edge_id, source_id, target_id, relation, attributes`. Mantemos essas colunas e **acrescentamos quatro**, sem remover nenhuma.

### 2.1 `nodes.csv`

| Coluna | Tipo | Obrigatória | Descrição |
|---|---|---|---|
| `node_id` | string | ✅ | Identificador do nó, no formato da [§6](#6-convenção-de-identificadores). |
| `case_id` | string | ✅ | Caso a que o nó pertence. Vazio apenas para nós `Concept`. |
| `type` | enum | ✅ | Um dos 12 tipos da [§4](#4-tipos-de-nó). |
| `label` | string | ✅ | Forma normalizada, conforme as regras da [#4](https://github.com/caiomelloni/PNL-CGGJL/issues/4). |
| `attributes` | JSON | ✅ | Atributos semânticos do doc 01. `{}` quando não há nenhum. |
| `char_start` | int | ⬜ | Início da menção no `case_text`. Vazio para `Concept`. |
| `char_end` | int | ⬜ | Fim (exclusivo) da menção. Vazio para `Concept`. |
| `mention` | string | ⬜ | Trecho literal do `case_text` que originou o nó. Vazio para `Concept`. |

### 2.2 `edges.csv`

| Coluna | Tipo | Obrigatória | Descrição |
|---|---|---|---|
| `edge_id` | string | ✅ | Identificador da aresta, no formato da [§6](#6-convenção-de-identificadores). |
| `case_id` | string | ✅ | Caso a que a aresta pertence. |
| `source_id` | string | ✅ | `node_id` da origem. |
| `target_id` | string | ✅ | `node_id` do destino. |
| `relation` | enum | ✅ | Uma das 13 relações da [§5](#5-tipos-de-aresta). |
| `attributes` | JSON | ✅ | `trigger` e `certainty` (doc 01 §2.1). |
| `char_start` | int | ⬜ | Início do trecho que evidencia a relação. |
| `char_end` | int | ⬜ | Fim (exclusivo) do trecho. |
| `evidence_text` | string | ⬜ | Trecho literal que evidencia a relação. |

**Por que `case_id` como coluna.** A amostra são 56 casos em **um** par de tabelas. Sem essa coluna, toda consulta por caso vira parsing de string do `node_id`, e o `join` com `cases.csv` e `metadata.csv` deixa de ser direto. É redundante com o prefixo do `node_id` de propósito: o prefixo garante unicidade, a coluna garante consultabilidade.

**Por que a ancoragem virou coluna.** O enunciado sugere guardar o trecho dentro de `attributes` da aresta. Deixamos fora por três razões: (i) `evidence_text` é longo e domina visualmente o campo, escondendo os atributos semânticos; (ii) auditar a extração é filtrar e ordenar por offset, e dentro do JSON isso exige desserializar todas as linhas; (iii) o mesmo campo passa a valer para nós, e `attributes` de nó tem esquema próprio por tipo — misturar ancoragem ali quebraria a validação. Com a separação, `attributes` fica **exclusivamente** para os atributos definidos no doc 01.

**Serialização física.** As duas tabelas são CSV RFC 4180 (`,` como separador, aspas duplas escapadas duplicando), UTF-8, com cabeçalho. O JSON de `attributes` fica dentro de uma célula entre aspas — daí a exigência de escape correto.

### 2.3 Serialização de `attributes`

**Decisão: JSON de um nível**, não `chave=valor` separado por `;`.

O formato `chave=valor;` do `example1` não tem escape definido, e nossos valores quebram-no de imediato: `basis` do doc 01 é texto livre, `reference_range_raw` guarda `normal range, 0-0.04 ng/mL`, e `frequency` admite texto livre. Basta um `;` ou um `=` dentro de qualquer um desses para o campo virar ambíguo, e não há como distinguir o separador do conteúdo depois. JSON resolve isso com escape padrão e ainda dá três coisas de graça:

- **tipo**: `"age": 44` e `"contrast": true` chegam como número e booleano em `json.loads`, sem heurística de conversão;
- **ausência explícita**: uma chave ausente significa "o texto não informa" (doc 01 permite `null` em quase todo atributo). **Não emitimos `"x": null`** — a chave simplesmente não aparece, o que encurta as linhas sem perder informação;
- **estrutura**: `mentions` (§7) precisa de lista de pares, que `chave=valor;` não representa.

Regras: um único nível de aninhamento (exceto `mentions`, que é lista de pares de inteiros); nós sem atributo recebem `{}`, nunca célula vazia; a ordem das chaves não é significativa.

---

## 3. Nível de decomposição

Os dois exemplos do enunciado são os extremos. No `example1`, `850 U/L` é um nó `ExamResult` com `value=850; unit=U/L` em `attributes`. No `example2`, `850` e `U/L` são nós próprios ligados por `HAS_VALUE` e `HAS_UNIT`, e as entidades apontam para vocabulários via `SAME_AS`.

### 3.1 O critério

Um atributo do doc 01 **vira nó** se, e somente se, satisfizer pelo menos um destes três critérios:

- **(a) Compartilhamento.** É alvo de relação vinda de mais de um tipo de entidade, ou precisa ser referenciado por mais de uma entidade do mesmo caso.
- **(b) Atributos próprios.** Tem, ele mesmo, atributos que só fazem sentido colados a ele e não à entidade que o contém.
- **(c) Eixo de consulta.** É uma dimensão pela qual o enunciado pede explicitamente que o grafo seja consultável.

Não satisfazendo nenhum, fica em `attributes`. O critério é aplicado atributo a atributo — não precisa ser uniforme, e não é: o próprio `example2` deixa `type=procedure` agregado enquanto decompõe valor e unidade.

### 3.2 O critério aplicado

| Item | `example1` | `example2` | **Nossa decisão** | Critério |
|---|---|---|---|---|
| `AnatomicalSite` | atributo do achado | nó | **nó** | (a) `Symptom`, `Finding` e `Treatment` apontam para ele; (c) o enunciado pede "regiões anatômicas" como categoria |
| Conceito de vocabulário externo | — | nó + `SAME_AS` | **nó `Concept`** | (a) é o único ponto onde casos distintos se encontram |
| `value` de `ExamResult` | `attributes` | nó + `HAS_VALUE` | **`attributes`** | falha em (a), (b) e (c) |
| `unit` de `ExamResult` | `attributes` | nó + `HAS_UNIT` | **`attributes`** | falha em (a), (b) e (c) |
| `reference_range_*` | `attributes` | nó | **`attributes`** (3 chaves) | falha nos três; a decomposição em `low`/`high`/`raw` já dá a consultabilidade numérica |
| `size` de `Finding` | `attributes` | nó | **`attributes`** | falha nos três |
| `dose_value` / `dose_unit` | `attributes` | nó | **`attributes`** | falha nos três |
| `duration`, `onset`, `timing` | `attributes` | — | **`attributes`** | falha nos três |
| `type` de `Treatment` | `attributes` | `attributes` | **`attributes`** | igual aos dois exemplos |
| `evidence_text` / offsets | `attributes` da aresta | — | **colunas próprias** | §2.2 |

### 3.3 Por que não decompor valor e unidade

O `example2` decompõe `850` e `U/L` para ganhar reuso e consultabilidade. No nosso caso os dois ganhos não se materializam:

- **Reuso não existe.** Dois casos raramente têm o mesmo valor medido, e quando têm (`6` de `6iu/ml`) o compartilhamento é acidental — une resultados que nada têm em comum. Unidade tem reuso real, mas já a normalizamos para UCUM (doc 01 §3.3), o que dá o mesmo agrupamento por `GROUP BY unit` sem nó nenhum.
- **Consultabilidade já existe.** "Todos os exames com valor acima de X" é `json_extract(attributes,'$.value') > X` sobre uma coluna, contra dois `join` no estilo RDF. A decomposição aqui piora a consulta que ela deveria facilitar.
- **`ExamResult` já é a decomposição.** O doc 01 separou `ExamResult` de `Finding` justamente para dar ao valor um nó com esquema fixo. Decompor de novo é decompor duas vezes a mesma coisa.

**O custo, medido.** No caso trabalhado da §9 temos 52 nós, 61 arestas e 122 pares chave-valor em `attributes` de nós. No estilo `example2`, cada par vira um nó e uma aresta: com reuso perfeito de literais (63 pares distintos) seriam **115 nós e 183 arestas**; sem reuso, **174 e 183**. Ou seja, 2,2× a 3,3× mais nós e 3× mais arestas para um caso — e a diferença cai quase toda em nós-literal do tipo `"present"` ou `"6 cm"`, que não são entidades clínicas e não respondem nenhuma pergunta que o enunciado faça.

**Onde concordamos com o `example2`.** `AnatomicalSite` e `Concept` são nós exatamente pelo argumento do `example2` — os dois passam no critério (a). A discordância não é sobre decompor, é sobre *o que* decompor.

---

## 4. Tipos de nó

Lista fechada, 12 tipos. Os 11 primeiros vêm do doc 01 §1; `Concept` é acrescentado aqui.

| `type` | Prefixo do id | Escopo | Chaves de `attributes` |
|---|---|---|---|
| `Patient` | `P` | caso | `article_id`, `age`, `age_unit`, `gender` |
| `Symptom` | `S` | caso | `polarity`, `duration`, `onset`, `course`, `severity` |
| `Finding` | `F` | caso | `source`, `polarity`, `certainty`, `size` |
| `History` | `H` | caso | `subject`, `polarity`, `relation_degree`, `category` |
| `Exam` | `E` | caso | `modality`, `timing`, `abbreviation`, `contrast` |
| `ExamResult` | `R` | caso | `value`, `unit`, `reference_range_low`, `reference_range_high`, `reference_range_raw`, `interpretation`, `interpretation_source`, `raw_text` |
| `Diagnosis` | `D` | caso | `certainty`, `polarity`, `role`, `basis` |
| `Medication` | `M` | caso | `dose_value`, `dose_unit`, `frequency`, `route`, `duration`, `dose_change`, `timing` |
| `Treatment` | `T` | caso | `type`, `status`, `converted_to`, `timing`, `intent` |
| `AnatomicalSite` | `A` | caso | `laterality`, `region_qualifier` |
| `Outcome` | `O` | caso | `type`, `timing`, `length_of_stay`, `follow_up_duration`, `polarity` |
| `Concept` | `C` | **global** | `vocabulary`, `code`, `preferred_term` |

Os domínios de valor de cada chave são os do doc 01 §1 e não se repetem aqui. Três chaves reservadas podem aparecer em qualquer tipo: `abbreviation` (sigla definida no caso), `mentions` (§7) e `notes` (texto livre para casos que o esquema não cobre, a ser esvaziado à medida que o esquema evolui).

---

## 5. Tipos de aresta

### 5.1 Lista fechada e combinações válidas

13 relações. As 12 do doc 01 §2 mais `SAME_AS`. Qualquer par origem→destino fora desta tabela é erro de extração e deve ser rejeitado pela validação.

| `relation` | Origem válida | Destino válido |
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
| `SAME_AS` | `Symptom`, `Finding`, `Exam`, `Diagnosis`, `Medication`, `Treatment`, `AnatomicalSite` | `Concept` |

Duas mudanças em relação ao doc 01, ambas motivadas pela aplicação da §9 e detalhadas na §8: `REVEALS` aceita `Treatment` como origem, e `SUPPORTS` aceita `History`.

### 5.2 Regras estruturais

1. **Todo grafo tem exatamente um `Patient`**, e é o nó de grau mais alto. Um caso sem `Patient` é erro.
2. **Toda aresta liga nós do mesmo `case_id`**, com uma exceção: `SAME_AS`, cujo destino é sempre um `Concept` global.
3. **Nenhum nó órfão**, exceto `Concept`. Todo nó de caso alcança o `Patient` por algum caminho não direcionado. Nó desconectado significa que a relação não foi extraída — é falha, não representação válida.
4. **`REVISES` não pode ter ciclo.** Se um diagnóstico revisa outro que o revisa de volta, a extração errou a ordem temporal.
5. **Multigrafo dirigido.** Dois nós podem ser ligados por mais de uma aresta se as relações forem distintas. Duas arestas com mesma `(source_id, target_id, relation)` são duplicata e devem ser fundidas, preservando o menor `char_start`.

### 5.3 `SAME_AS` e o tipo `Concept`

O esquema **prevê** ancoragem em vocabulário controlado, mas não a exige. A escolha dos vocabulários é da [#6](https://github.com/caiomelloni/PNL-CGGJL/issues/6); o que fica decidido aqui é a forma:

- O `Concept` é o **único tipo global**: `case_id`, `char_start`, `char_end` e `mention` ficam vazios, e o `node_id` é `CONCEPT:<vocabulário>:<código>` — por exemplo `CONCEPT:UMLS:C0000000` (código ilustrativo). Nós idênticos de casos distintos convergem aqui, e é só aqui.
- `attributes` traz `vocabulary`, `code` e `preferred_term`; a aresta `SAME_AS` traz `score` (confiança do casamento) e `method` (como foi obtido), além de `trigger` e `certainty` vazios, já que a relação não vem de gatilho textual.
- Um mesmo nó pode ter `SAME_AS` para mais de um vocabulário. Nenhum `SAME_AS` é obrigatório: entidade sem casamento simplesmente não tem a aresta.

Consequência prática: enquanto a #6 não decidir, as tabelas saem sem nenhuma linha `Concept` e sem nenhuma aresta `SAME_AS` — e continuam válidas. O exemplo da §9 é gerado nesse estado.

---

## 6. Convenção de identificadores

**`node_id` = `<case_id>:<prefixo><n>`** — por exemplo `PMC5137649_01:S1`. O prefixo é o da tabela da §4; `n` é sequencial por tipo dentro do caso, na ordem de primeira menção no texto.

**`edge_id` = `<case_id>:e<nn>`** — por exemplo `PMC5137649_01:e01`, sequencial dentro do caso.

**`Concept`**: `CONCEPT:<vocabulário>:<código>`, sem `case_id`.

### 6.1 Os ids são globais, os nós não são compartilhados

Os ids são **únicos em toda a amostra** por construção — o prefixo de caso garante isso sem coordenação entre quem processa cada caso.

Nós idênticos de casos diferentes são **duplicados, não compartilhados**. O diagnóstico `Hypertension` em dois casos são dois nós, com ids distintos. Três razões:

1. **Os atributos são asserções do caso, não propriedades do conceito.** Um `Diagnosis` com `certainty=suspected` num caso e `confirmed` noutro não pode ser um nó só — fundi-los obrigaria a escolher um valor, apagando o que o texto de cada caso afirma. O mesmo vale para `polarity` e `role`.
2. **A ancoragem é por caso.** `char_start`/`char_end` só fazem sentido dentro de um `case_text`. Um nó compartilhado teria de carregar uma lista de âncoras por caso, que é exatamente a estrutura que estamos evitando.
3. **A avaliação é por caso.** Comparar a extração com uma referência é comparar grafo a grafo; nó compartilhado embaralha o cálculo de precisão e cobertura entre casos.

O reuso entre casos, que é o ganho real que o compartilhamento traria, é obtido de forma limpa pelo `Concept`: dois `Diagnosis` de casos distintos que apontam para o mesmo `CONCEPT:...` são reconhecíveis como o mesmo conceito por um `join`, sem que nenhum dos dois perca seus atributos ou sua âncora.

**Dentro do caso, ao contrário, a unificação é obrigatória.** As menções repetidas da mesma entidade (`stomach` aparece 7 vezes no caso da §9; `EUS-FNA` e sua expansão são a mesma coisa) geram **um** nó, com as menções extras registradas em `mentions`. Duas menções só geram dois nós quando os atributos divergem — `stomach` sem qualificador e `posterior wall of the stomach` são `A1` e `A6`, porque `region_qualifier` os distingue.

### 6.2 `case_id` e `article_id`

`case_id` é coluna nas duas tabelas e prefixo de todo id. `article_id` **não** é coluna: fica em `attributes` do `Patient`, porque é propriedade do caso, é constante dentro dele e é derivável do `case_id` por prefixo. Quem precisar dos metadados do artigo faz `join` de `metadata.csv` por ele.

---

## 7. Ancoragem no texto

**Decisão: guardamos as duas coisas — offsets e trecho — e não só nas arestas, também nos nós.**

Nenhum dos dois basta sozinho. Offset sem trecho é ilegível: ninguém revisa `(1837, 1902)` sem abrir o `case_text` ao lado. Trecho sem offset é ambíguo: `the stomach` ocorre 7 vezes no caso da §9, e sem offset não dá para dizer qual ocorrência gerou o nó — o que inviabiliza contar acerto e erro por menção quando formos avaliar a extração.

**Regras:**

- Offsets são índices de caractere no `case_text` da linha correspondente de `cases.csv`, intervalo **semiaberto** `[char_start, char_end)` — a mesma convenção do fatiamento em Python, para que `case_text[char_start:char_end] == mention` seja verdade sem ajuste. Contam-se caracteres Unicode (`str`), não bytes, sobre o texto normalizado em NFC.
- **Nós** guardam a menção que os originou (`mention` + offsets). O enunciado só sugere ancorar arestas, mas sem âncora no nó não há como avaliar reconhecimento de entidade separado de extração de relação, que são etapas distintas nas issues [#3](https://github.com/caiomelloni/PNL-CGGJL/issues/3)–[#5](https://github.com/caiomelloni/PNL-CGGJL/issues/5).
- **Arestas** guardam o trecho que evidencia a relação (`evidence_text` + offsets): tipicamente o intervalo que cobre origem, gatilho e destino, e não a frase inteira quando ela for maior que isso.
- **Menções múltiplas**: quando a mesma entidade aparece várias vezes, `char_start`/`char_end`/`mention` apontam para a **primeira** menção, e a chave opcional `mentions` de `attributes` traz a lista completa de pares `[início, fim]`, inclusive a primeira. Ver `D2` na §9, cujo rótulo vem de uma menção e a sigla de outra.
- Toda linha com ancoragem deve satisfazer `case_text[char_start:char_end] == mention` (ou `== evidence_text`). É a asserção mais barata de validar e pega a classe de erro mais comum, que é offset deslocado por normalização de texto. Os offsets deste documento foram gerados com essa checagem.
- **`Concept` não tem ancoragem** — não vem do texto. A âncora do casamento é a do nó de origem do `SAME_AS`.

**Custo, e por que aceitamos.** Guardar trecho e offsets infla as tabelas: no caso da §9, `evidence_text` é de longe a coluna mais pesada. Aceitamos porque é a diferença entre um grafo que pode ser auditado e avaliado e um que só pode ser olhado — e a etapa de avaliação depende inteiramente disso.

---

## 8. Ajustes ao doc 01 revelados pela aplicação

Aplicar o esquema a um caso real expôs três lacunas do doc 01. Os ajustes já estão incorporados nas §4 e §5.

**1. `Finding.source` não cobria endoscopia nem observação cirúrgica.** O domínio era `physical_exam | imaging | pathology | lab`, mas o caso traz `no mucosal abnormalities of the stomach were noted` (endoscopia) e `the lesion was noted to be tightly adherent to both the stomach and pancreas` (observação intraoperatória). Forçá-los em `imaging` ou `physical_exam` seria falso. **Ajuste:** o domínio passa a `physical_exam | imaging | pathology | lab | endoscopy | surgical`.

**2. `REVEALS` não tinha origem para achado intraoperatório.** Quem produz `the lesion originated from the stomach` é a cirurgia, não um exame. As alternativas eram pendurar em `Patient` via `HAS_FINDING`, perdendo a procedência, ou estender a relação. **Ajuste:** `REVEALS` aceita `Exam` **ou** `Treatment` como origem — registrar de onde veio o achado é exatamente a razão de `REVEALS` existir, e uma cirurgia produz achado tanto quanto um exame. `HAS_FINDING` continua sendo o recurso para achado cujo produtor o texto não nomeia (ver `F18` na §9).

**3. `SUPPORTS` não aceitava `History`.** O doc 01 restringe a origem a `Symptom | Finding | ExamResult`, mas antecedente é evidência diagnóstica corriqueira em texto clínico. **Ajuste:** `History` entra no domínio de origem. O caso da §9 não exercita essa combinação; ela foi incluída por ser previsível na amostra.

Um quarto ponto foi **decidido sem mudar o esquema**: negação de um exame inteiro (`her physical examination was unremarkable`) é representada como um `Finding` **afirmado** de rótulo `unremarkable physical examination` (`polarity=present`), não como achado negado. O motivo é que não há um achado específico sendo negado — a negação é sobre o conjunto, e `polarity=absent` exigiria inventar o achado ausente. `polarity=absent` fica para negação de item nomeado (`no evidence of malignancy` → `F8`).

---

## 9. Exemplo aplicado — `PMC5137649_01`

Esquema aplicado à mão ao caso `PMC5137649_01` (artigo `PMC5137649`, cisto de duplicação gástrica confundido com neoplasia cística mucinosa do pâncreas). É o caso mais citado no doc 01 e exercita quase todo o esquema: revisão de diagnóstico, tratamento convertido, resultado de exame quantitativo, achado negado e desfecho múltiplo.

**Texto de referência.** Os offsets abaixo são relativos ao `case_text` reproduzido no [Anexo A](#anexo-a--case_text-de-referência), que é a seção *Case history* do artigo, com os quatro parágrafos unidos por `\n\n`. Se o `case_text` de `cases.csv` diferir dessa string (por limpeza de chamadas de figura, por exemplo), os offsets mudam — os rótulos, atributos e relações, não. Todo par `(char_start, char_end)` foi verificado contra o Anexo A pela asserção da §7.

**Cobertura.** 52 nós e 61 arestas, sem nó órfão e sem id pendente:

| Tipo de nó | n |   | Relação | n |
|---|---:|---|---|---:|
| `Finding` | 19 |   | `REVEALS` | 17 |
| `Exam` | 8 |   | `LOCATED_IN` | 12 |
| `AnatomicalSite` | 7 |   | `UNDERWENT_EXAM` | 8 |
| `Outcome` | 4 |   | `HAS_OUTCOME` | 4 |
| `Symptom` | 3 |   | `SUPPORTS` | 4 |
| `History` | 3 |   | `HAS_SYMPTOM` | 3 |
| `Treatment` | 3 |   | `HAS_HISTORY` | 3 |
| `Diagnosis` | 2 |   | `TREATED_WITH` | 3 |
| `ExamResult` | 2 |   | `DIAGNOSED_WITH` | 2 |
| `Patient` | 1 |   | `HAS_FINDING` | 2 |
| `Medication` | 0 |   | `HAS_RESULT` | 2 |
| `Concept` | 0 |   | `REVISES` | 1 |
|  |  |   | `SAME_AS` | 0 |

`Medication` fica em zero porque o caso é inteiramente cirúrgico — nenhum fármaco é nomeado. `Concept` e `SAME_AS` ficam em zero pela §5.3, à espera da [#6](https://github.com/caiomelloni/PNL-CGGJL/issues/6).

**Sete pontos que o exemplo demonstra:**

1. **Revisão de diagnóstico.** `D1` (`mucinous pancreatic cystic neoplasm`, `certainty=suspected`, gatilho `suggesting`) é substituído por `D2` (`gastric duplication cyst`, `certainty=confirmed`, gatilho `consistent with`), com `D2 --REVISES--> D1`. Os dois permanecem no grafo: apagar `D1` apagaria o raciocínio clínico do caso.
2. **Interpretação não inferida.** `R1` tem `value=12476.5`, `unit=ng/mL`, mas **sem** `interpretation` — a `case_text` não diz que o CEA está elevado (quem diz é a discussão do artigo, fora do escopo). Preencher `elevated` aqui seria conhecimento clínico nosso, que o doc 01 proíbe.
3. **Tratamento convertido.** `T2` tem `status=converted`, `converted_to=open resection`; o que de fato ocorreu é `T3`. Sem `status`, o grafo afirmaria que uma pancreatectomia laparoscópica foi realizada — e não foi.
4. **Achado negado é dado.** `F5`, `F6`, `F8`, `F12`, `F16`, `F17` e `O2` têm `polarity=absent`. `F8` (`no evidence of malignancy`) é o caso crítico: sem tratar a negação, o extrator produziria um diagnóstico de malignidade que o texto nega.
5. **Achado de cirurgia.** `F10`, `F11`, `F13` e `F14` vêm de `REVEALS` com origem `Treatment` (§8, ajuste 2). Já `F18` (`The gross margins were uninvolved`) usa `HAS_FINDING` a partir do `Patient`, porque o texto não nomeia quem produziu esse achado.
6. **Unificação e desambiguação de menção.** `stomach` ocorre 7 vezes e gera **dois** nós: `A1` (sem qualificador) e `A6` (`region_qualifier=posterior wall`), porque os atributos divergem. Já `D2` é um nó só, com `mentions` cobrindo a menção por extenso e a sigla `GDC` — que este caso nunca expande explicitamente, e cuja ligação depende da unificação intra-caso da §6.1.
7. **`certainty` da aresta separada da do nó.** As arestas `SUPPORTS` de `F9`, `R1` e `R2` para `D1` têm `certainty=hedged` (gatilho `suggesting`), enquanto `F19 --SUPPORTS--> D2` é `asserted` (gatilho `consistent with`). É a distinção entre a confiança na evidência e a confiança no elo evidência→conclusão.

### 9.1 Tabela de nós

| `node_id` | `case_id` | `type` | `label` | `attributes` | `char_start` | `char_end` | `mention` |
|---|---|---|---|---|---:|---:|---|
| `PMC5137649_01:P1` | `PMC5137649_01` | `Patient` | 44-year-old woman | `{"article_id": "PMC5137649", "age": 44, "age_unit": "years", "gender": "Female"}` | 0 | 19 | A 44-year-old woman |
| `PMC5137649_01:S1` | `PMC5137649_01` | `Symptom` | abdominal pain | `{"polarity": "present", "duration": "3 days"}` | 54 | 99 | right flank and lower quadrant abdominal pain |
| `PMC5137649_01:S2` | `PMC5137649_01` | `Symptom` | nausea | `{"polarity": "present"}` | 116 | 122 | nausea |
| `PMC5137649_01:S3` | `PMC5137649_01` | `Symptom` | constipation | `{"polarity": "present"}` | 127 | 139 | constipation |
| `PMC5137649_01:H1` | `PMC5137649_01` | `History` | past medical history | `{"subject": "patient", "polarity": "absent", "category": "condition"}` | 141 | 220 | Her past medical, family and medication history were otherwise non-contributory |
| `PMC5137649_01:H2` | `PMC5137649_01` | `History` | family history | `{"subject": "family", "polarity": "absent", "relation_degree": "unspecified", "category": "condition"}` | 141 | 220 | Her past medical, family and medication history were otherwise non-contributory |
| `PMC5137649_01:H3` | `PMC5137649_01` | `History` | medication history | `{"subject": "patient", "polarity": "absent", "category": "medication"}` | 141 | 220 | Her past medical, family and medication history were otherwise non-contributory |
| `PMC5137649_01:F1` | `PMC5137649_01` | `Finding` | unremarkable physical examination | `{"source": "physical_exam", "polarity": "present", "certainty": "confirmed"}` | 225 | 266 | her physical examination was unremarkable |
| `PMC5137649_01:E1` | `PMC5137649_01` | `Exam` | computed tomography | `{"modality": "imaging", "contrast": true, "timing": "initial"}` | 282 | 319 | contrast enhanced computed tomography |
| `PMC5137649_01:F2` | `PMC5137649_01` | `Finding` | cystic lesion | `{"source": "imaging", "polarity": "present", "certainty": "confirmed", "size": "6 cm"}` | 335 | 354 | a 6cm cystic lesion |
| `PMC5137649_01:A1` | `PMC5137649_01` | `AnatomicalSite` | stomach | `{}` | 363 | 374 | the stomach |
| `PMC5137649_01:A2` | `PMC5137649_01` | `AnatomicalSite` | pancreas | `{"region_qualifier": "body/tail"}` | 379 | 404 | body/tail of the pancreas |
| `PMC5137649_01:A3` | `PMC5137649_01` | `AnatomicalSite` | flank | `{"laterality": "right"}` | 54 | 65 | right flank |
| `PMC5137649_01:A4` | `PMC5137649_01` | `AnatomicalSite` | abdominal quadrant | `{"region_qualifier": "lower"}` | 70 | 84 | lower quadrant |
| `PMC5137649_01:E2` | `PMC5137649_01` | `Exam` | endoscopic ultrasound-guided fine needle aspiration | `{"modality": "endoscopy", "abbreviation": "EUS-FNA", "timing": "follow-up"}` | 441 | 448 | EUS-FNA |
| `PMC5137649_01:F3` | `PMC5137649_01` | `Finding` | normal pancreatic echotexture | `{"source": "imaging", "polarity": "present"}` | 465 | 494 | normal pancreatic echotexture |
| `PMC5137649_01:F4` | `PMC5137649_01` | `Finding` | cyst | `{"source": "imaging", "polarity": "present", "size": "6 cm × 9 cm"}` | 499 | 525 | a cyst measuring 6cm × 9cm |
| `PMC5137649_01:F5` | `PMC5137649_01` | `Finding` | internal septations | `{"source": "imaging", "polarity": "absent"}` | 535 | 583 | free of internal septations or associated masses |
| `PMC5137649_01:F6` | `PMC5137649_01` | `Finding` | associated masses | `{"source": "imaging", "polarity": "absent"}` | 535 | 583 | free of internal septations or associated masses |
| `PMC5137649_01:F7` | `PMC5137649_01` | `Finding` | gastric compression | `{"source": "imaging", "polarity": "present"}` | 596 | 618 | compressed the stomach |
| `PMC5137649_01:E3` | `PMC5137649_01` | `Exam` | fine needle aspiration of the cyst | `{"modality": "pathology", "abbreviation": "FNA"}` | 620 | 635 | FNA of the cyst |
| `PMC5137649_01:F8` | `PMC5137649_01` | `Finding` | malignancy | `{"source": "pathology", "polarity": "absent", "certainty": "confirmed"}` | 649 | 674 | no evidence of malignancy |
| `PMC5137649_01:F9` | `PMC5137649_01` | `Finding` | extracellular mucin | `{"source": "pathology", "polarity": "present"}` | 688 | 723 | the presence of extracellular mucin |
| `PMC5137649_01:E4` | `PMC5137649_01` | `Exam` | carcinoembryonic antigen | `{"modality": "laboratory", "abbreviation": "CEA"}` | 737 | 767 | carcinoembryonic antigen (CEA) |
| `PMC5137649_01:R1` | `PMC5137649_01` | `ExamResult` | 12,476.5 ng/mL | `{"value": 12476.5, "unit": "ng/mL", "raw_text": "12,476.5ng/ml"}` | 777 | 790 | 12,476.5ng/ml |
| `PMC5137649_01:E5` | `PMC5137649_01` | `Exam` | carbohydrate antigen 19-9 | `{"modality": "laboratory", "abbreviation": "CA 19-9"}` | 797 | 827 | carbohydrate antigen (CA) 19-9 |
| `PMC5137649_01:R2` | `PMC5137649_01` | `ExamResult` | 6 [IU]/mL | `{"value": 6, "unit": "[IU]/mL", "raw_text": "6iu/ml"}` | 837 | 843 | 6iu/ml |
| `PMC5137649_01:D1` | `PMC5137649_01` | `Diagnosis` | mucinous pancreatic cystic neoplasm | `{"certainty": "suspected", "polarity": "present", "role": "differential", "basis": "extracellular mucin and CEA level"}` | 856 | 910 | the diagnosis of a mucinous pancreatic cystic neoplasm |
| `PMC5137649_01:T1` | `PMC5137649_01` | `Treatment` | surgical resection | `{"type": "surgery", "status": "planned", "intent": "curative"}` | 938 | 969 | referred for surgical resection |
| `PMC5137649_01:T2` | `PMC5137649_01` | `Treatment` | laparoscopic distal pancreatectomy | `{"type": "surgery", "status": "converted", "converted_to": "open resection", "intent": "curative"}` | 972 | 1020 | A laparoscopic distal pancreatectomy was planned |
| `PMC5137649_01:A5` | `PMC5137649_01` | `AnatomicalSite` | lesser sac | `{}` | 1079 | 1093 | the lesser sac |
| `PMC5137649_01:A6` | `PMC5137649_01` | `AnatomicalSite` | stomach | `{"region_qualifier": "posterior wall"}` | 1132 | 1165 | the posterior wall of the stomach |
| `PMC5137649_01:F10` | `PMC5137649_01` | `Finding` | lesion adherent to stomach and pancreas | `{"source": "surgical", "polarity": "present"}` | 1167 | 1243 | the lesion was noted to be tightly adherent to both the stomach and pancreas |
| `PMC5137649_01:F11` | `PMC5137649_01` | `Finding` | lesion originating from the stomach | `{"source": "surgical", "polarity": "present"}` | 1313 | 1351 | the lesion originated from the stomach |
| `PMC5137649_01:E6` | `PMC5137649_01` | `Exam` | intraoperative endoscopy | `{"modality": "endoscopy", "timing": "intraoperative"}` | 1353 | 1377 | Intraoperative endoscopy |
| `PMC5137649_01:F12` | `PMC5137649_01` | `Finding` | gastric mucosal abnormalities | `{"source": "endoscopy", "polarity": "absent"}` | 1396 | 1446 | no mucosal abnormalities of the stomach were noted |
| `PMC5137649_01:F13` | `PMC5137649_01` | `Finding` | cyst adherent to the coeliac axis | `{"source": "surgical", "polarity": "present"}` | 1474 | 1515 | the cyst was adherent to the coeliac axis |
| `PMC5137649_01:A7` | `PMC5137649_01` | `AnatomicalSite` | coeliac axis | `{}` | 1499 | 1515 | the coeliac axis |
| `PMC5137649_01:F14` | `PMC5137649_01` | `Finding` | cyst arising from the posterior gastric wall | `{"source": "surgical", "polarity": "present"}` | 1606 | 1682 | the gastric duplication cyst was noted to be arising from the posterior wall |
| `PMC5137649_01:T3` | `PMC5137649_01` | `Treatment` | en bloc resection of the cyst with partial gastrectomy | `{"type": "surgery", "status": "performed", "intent": "curative"}` | 1729 | 1856 | an enbloc resection of the cyst along with a portion of the posterior wall of the stomach with a surgical stapler was performed |
| `PMC5137649_01:E7` | `PMC5137649_01` | `Exam` | oesophagogastroduodenoscopy | `{"modality": "endoscopy", "timing": "intraoperative"}` | 1858 | 1892 | Repeat oesophagogastroduodenoscopy |
| `PMC5137649_01:F15` | `PMC5137649_01` | `Finding` | intact staple line | `{"source": "endoscopy", "polarity": "present"}` | 1918 | 1969 | an intact staple line on the posterior stomach wall |
| `PMC5137649_01:F16` | `PMC5137649_01` | `Finding` | bleeding | `{"source": "endoscopy", "polarity": "absent"}` | 1974 | 2005 | no evidence of bleeding or leak |
| `PMC5137649_01:F17` | `PMC5137649_01` | `Finding` | leak | `{"source": "endoscopy", "polarity": "absent"}` | 1974 | 2005 | no evidence of bleeding or leak |
| `PMC5137649_01:F18` | `PMC5137649_01` | `Finding` | uninvolved gross margins | `{"source": "pathology", "polarity": "present"}` | 2007 | 2040 | The gross margins were uninvolved |
| `PMC5137649_01:E8` | `PMC5137649_01` | `Exam` | final pathology | `{"modality": "pathology", "timing": "postoperative"}` | 2043 | 2058 | Final pathology |
| `PMC5137649_01:F19` | `PMC5137649_01` | `Finding` | cyst with smooth internal cyst wall | `{"source": "pathology", "polarity": "present", "size": "9.5 cm × 4.5 cm × 2.0 cm"}` | 2068 | 2129 | a 9.5cm × 4.5cm × 2.0cm cyst with a smooth internal cyst wall |
| `PMC5137649_01:D2` | `PMC5137649_01` | `Diagnosis` | gastric duplication cyst | `{"certainty": "confirmed", "polarity": "present", "role": "principal", "basis": "final pathology", "abbreviation": "GDC", "mentions": [[1606, 1634], [2146, 2151]]}` | 2130 | 2151 | consistent with a GDC |
| `PMC5137649_01:O1` | `PMC5137649_01` | `Outcome` | discharged home | `{"type": "discharge", "polarity": "present", "timing": "postoperative day 4", "length_of_stay": "4 days"}` | 2164 | 2218 | The patient was discharged home on postoperative day 4 |
| `PMC5137649_01:O2` | `PMC5137649_01` | `Outcome` | complications | `{"type": "complication", "polarity": "absent"}` | 2261 | 2286 | without any complications |
| `PMC5137649_01:O3` | `PMC5137649_01` | `Outcome` | resolution of pain and nausea | `{"type": "resolution", "polarity": "present", "timing": "follow-up"}` | 2310 | 2352 | complete resolution of her pain and nausea |
| `PMC5137649_01:O4` | `PMC5137649_01` | `Outcome` | return to regular bowel function and activity | `{"type": "improvement", "polarity": "present", "timing": "follow-up"}` | 2358 | 2405 | a return to regular bowel function and activity |

### 9.2 Tabela de arestas

| `edge_id` | `case_id` | `source_id` | `target_id` | `relation` | `attributes` | `char_start` | `char_end` | `evidence_text` |
|---|---|---|---|---|---|---:|---:|---|
| `PMC5137649_01:e01` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:S1` | `HAS_SYMPTOM` | `{"trigger": "presented with", "certainty": "asserted"}` | 0 | 99 | A 44-year-old woman presented with a 3-day history of right flank and lower quadrant abdominal pain |
| `PMC5137649_01:e02` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:S2` | `HAS_SYMPTOM` | `{"trigger": "associated with", "certainty": "asserted"}` | 85 | 139 | abdominal pain associated with nausea and constipation |
| `PMC5137649_01:e03` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:S3` | `HAS_SYMPTOM` | `{"trigger": "associated with", "certainty": "asserted"}` | 85 | 139 | abdominal pain associated with nausea and constipation |
| `PMC5137649_01:e04` | `PMC5137649_01` | `PMC5137649_01:S1` | `PMC5137649_01:A3` | `LOCATED_IN` | `{"trigger": "premodificador anatomico", "certainty": "asserted"}` | 54 | 99 | right flank and lower quadrant abdominal pain |
| `PMC5137649_01:e05` | `PMC5137649_01` | `PMC5137649_01:S1` | `PMC5137649_01:A4` | `LOCATED_IN` | `{"trigger": "premodificador anatomico", "certainty": "asserted"}` | 54 | 99 | right flank and lower quadrant abdominal pain |
| `PMC5137649_01:e06` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:H1` | `HAS_HISTORY` | `{"trigger": "history were otherwise non-contributory", "certainty": "asserted"}` | 141 | 220 | Her past medical, family and medication history were otherwise non-contributory |
| `PMC5137649_01:e07` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:H2` | `HAS_HISTORY` | `{"trigger": "history were otherwise non-contributory", "certainty": "asserted"}` | 141 | 220 | Her past medical, family and medication history were otherwise non-contributory |
| `PMC5137649_01:e08` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:H3` | `HAS_HISTORY` | `{"trigger": "history were otherwise non-contributory", "certainty": "asserted"}` | 141 | 220 | Her past medical, family and medication history were otherwise non-contributory |
| `PMC5137649_01:e09` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:F1` | `HAS_FINDING` | `{"trigger": "physical examination", "certainty": "asserted"}` | 225 | 266 | her physical examination was unremarkable |
| `PMC5137649_01:e10` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:E1` | `UNDERWENT_EXAM` | `{"trigger": "underwent", "certainty": "asserted"}` | 268 | 319 | She underwent contrast enhanced computed tomography |
| `PMC5137649_01:e11` | `PMC5137649_01` | `PMC5137649_01:E1` | `PMC5137649_01:F2` | `REVEALS` | `{"trigger": "demonstrating", "certainty": "asserted"}` | 282 | 354 | contrast enhanced computed tomography, demonstrating a 6cm cystic lesion |
| `PMC5137649_01:e12` | `PMC5137649_01` | `PMC5137649_01:F2` | `PMC5137649_01:A1` | `LOCATED_IN` | `{"trigger": "between", "certainty": "asserted"}` | 335 | 404 | a 6cm cystic lesion between the stomach and body/tail of the pancreas |
| `PMC5137649_01:e13` | `PMC5137649_01` | `PMC5137649_01:F2` | `PMC5137649_01:A2` | `LOCATED_IN` | `{"trigger": "between", "certainty": "asserted"}` | 335 | 404 | a 6cm cystic lesion between the stomach and body/tail of the pancreas |
| `PMC5137649_01:e14` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:E2` | `UNDERWENT_EXAM` | `{"trigger": "underwent", "certainty": "asserted"}` | 414 | 448 | She subsequently underwent EUS-FNA |
| `PMC5137649_01:e15` | `PMC5137649_01` | `PMC5137649_01:E2` | `PMC5137649_01:F3` | `REVEALS` | `{"trigger": "revealed", "certainty": "asserted"}` | 450 | 494 | which revealed normal pancreatic echotexture |
| `PMC5137649_01:e16` | `PMC5137649_01` | `PMC5137649_01:E2` | `PMC5137649_01:F4` | `REVEALS` | `{"trigger": "revealed", "certainty": "asserted"}` | 456 | 525 | revealed normal pancreatic echotexture and a cyst measuring 6cm × 9cm |
| `PMC5137649_01:e17` | `PMC5137649_01` | `PMC5137649_01:E2` | `PMC5137649_01:F5` | `REVEALS` | `{"trigger": "free of", "certainty": "asserted"}` | 499 | 583 | a cyst measuring 6cm × 9cm that was free of internal septations or associated masses |
| `PMC5137649_01:e18` | `PMC5137649_01` | `PMC5137649_01:E2` | `PMC5137649_01:F6` | `REVEALS` | `{"trigger": "free of", "certainty": "asserted"}` | 499 | 583 | a cyst measuring 6cm × 9cm that was free of internal septations or associated masses |
| `PMC5137649_01:e19` | `PMC5137649_01` | `PMC5137649_01:E2` | `PMC5137649_01:F7` | `REVEALS` | `{"trigger": "but", "certainty": "asserted"}` | 584 | 618 | (Fig 2) but compressed the stomach |
| `PMC5137649_01:e20` | `PMC5137649_01` | `PMC5137649_01:F7` | `PMC5137649_01:A1` | `LOCATED_IN` | `{"trigger": "objeto direto", "certainty": "asserted"}` | 596 | 618 | compressed the stomach |
| `PMC5137649_01:e21` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:E3` | `UNDERWENT_EXAM` | `{"trigger": "FNA of", "certainty": "asserted"}` | 620 | 648 | FNA of the cyst demonstrated |
| `PMC5137649_01:e22` | `PMC5137649_01` | `PMC5137649_01:E3` | `PMC5137649_01:F8` | `REVEALS` | `{"trigger": "demonstrated", "certainty": "asserted"}` | 620 | 674 | FNA of the cyst demonstrated no evidence of malignancy |
| `PMC5137649_01:e23` | `PMC5137649_01` | `PMC5137649_01:E3` | `PMC5137649_01:F9` | `REVEALS` | `{"trigger": "did show", "certainty": "asserted"}` | 679 | 723 | did show the presence of extracellular mucin |
| `PMC5137649_01:e24` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:E4` | `UNDERWENT_EXAM` | `{"trigger": "as well as a", "certainty": "asserted"}` | 724 | 790 | as well as a carcinoembryonic antigen (CEA) level of 12,476.5ng/ml |
| `PMC5137649_01:e25` | `PMC5137649_01` | `PMC5137649_01:E4` | `PMC5137649_01:R1` | `HAS_RESULT` | `{"trigger": "level of", "certainty": "asserted"}` | 737 | 790 | carcinoembryonic antigen (CEA) level of 12,476.5ng/ml |
| `PMC5137649_01:e26` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:E5` | `UNDERWENT_EXAM` | `{"trigger": "and a", "certainty": "asserted"}` | 791 | 843 | and a carbohydrate antigen (CA) 19-9 level of 6iu/ml |
| `PMC5137649_01:e27` | `PMC5137649_01` | `PMC5137649_01:E5` | `PMC5137649_01:R2` | `HAS_RESULT` | `{"trigger": "level of", "certainty": "asserted"}` | 797 | 843 | carbohydrate antigen (CA) 19-9 level of 6iu/ml |
| `PMC5137649_01:e28` | `PMC5137649_01` | `PMC5137649_01:F9` | `PMC5137649_01:D1` | `SUPPORTS` | `{"trigger": "suggesting", "certainty": "hedged"}` | 688 | 910 | the presence of extracellular mucin as well as a carcinoembryonic antigen (CEA) level of 12,476.5ng/ml and a carbohydrate antigen (CA) 19-9 level of 6iu/ml, suggesting the diagnosis of a mucinous pancreatic cystic neoplasm |
| `PMC5137649_01:e29` | `PMC5137649_01` | `PMC5137649_01:R1` | `PMC5137649_01:D1` | `SUPPORTS` | `{"trigger": "suggesting", "certainty": "hedged"}` | 688 | 910 | the presence of extracellular mucin as well as a carcinoembryonic antigen (CEA) level of 12,476.5ng/ml and a carbohydrate antigen (CA) 19-9 level of 6iu/ml, suggesting the diagnosis of a mucinous pancreatic cystic neoplasm |
| `PMC5137649_01:e30` | `PMC5137649_01` | `PMC5137649_01:R2` | `PMC5137649_01:D1` | `SUPPORTS` | `{"trigger": "suggesting", "certainty": "hedged"}` | 688 | 910 | the presence of extracellular mucin as well as a carcinoembryonic antigen (CEA) level of 12,476.5ng/ml and a carbohydrate antigen (CA) 19-9 level of 6iu/ml, suggesting the diagnosis of a mucinous pancreatic cystic neoplasm |
| `PMC5137649_01:e31` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:D1` | `DIAGNOSED_WITH` | `{"trigger": "suggesting the diagnosis of", "certainty": "hedged"}` | 845 | 910 | suggesting the diagnosis of a mucinous pancreatic cystic neoplasm |
| `PMC5137649_01:e32` | `PMC5137649_01` | `PMC5137649_01:D1` | `PMC5137649_01:T1` | `TREATED_WITH` | `{"trigger": "therefore referred for", "certainty": "asserted"}` | 912 | 969 | The patient was therefore referred for surgical resection |
| `PMC5137649_01:e33` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:T2` | `TREATED_WITH` | `{"trigger": "was planned", "certainty": "asserted"}` | 972 | 1020 | A laparoscopic distal pancreatectomy was planned |
| `PMC5137649_01:e34` | `PMC5137649_01` | `PMC5137649_01:T2` | `PMC5137649_01:A5` | `LOCATED_IN` | `{"trigger": "entrance to", "certainty": "asserted"}` | 1067 | 1112 | entrance to the lesser sac was first obtained |
| `PMC5137649_01:e35` | `PMC5137649_01` | `PMC5137649_01:T2` | `PMC5137649_01:F10` | `REVEALS` | `{"trigger": "was noted to be", "certainty": "asserted"}` | 1167 | 1243 | the lesion was noted to be tightly adherent to both the stomach and pancreas |
| `PMC5137649_01:e36` | `PMC5137649_01` | `PMC5137649_01:T2` | `PMC5137649_01:F11` | `REVEALS` | `{"trigger": "it was evident that", "certainty": "asserted"}` | 1293 | 1351 | it was evident that the lesion originated from the stomach |
| `PMC5137649_01:e37` | `PMC5137649_01` | `PMC5137649_01:F11` | `PMC5137649_01:A1` | `LOCATED_IN` | `{"trigger": "originated from", "certainty": "asserted"}` | 1313 | 1351 | the lesion originated from the stomach |
| `PMC5137649_01:e38` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:E6` | `UNDERWENT_EXAM` | `{"trigger": "was performed", "certainty": "asserted"}` | 1353 | 1391 | Intraoperative endoscopy was performed |
| `PMC5137649_01:e39` | `PMC5137649_01` | `PMC5137649_01:E6` | `PMC5137649_01:F12` | `REVEALS` | `{"trigger": "were noted", "certainty": "asserted"}` | 1396 | 1446 | no mucosal abnormalities of the stomach were noted |
| `PMC5137649_01:e40` | `PMC5137649_01` | `PMC5137649_01:F12` | `PMC5137649_01:A1` | `LOCATED_IN` | `{"trigger": "of the", "certainty": "asserted"}` | 1399 | 1435 | mucosal abnormalities of the stomach |
| `PMC5137649_01:e41` | `PMC5137649_01` | `PMC5137649_01:T2` | `PMC5137649_01:F13` | `REVEALS` | `{"trigger": "was adherent to", "certainty": "asserted"}` | 1474 | 1515 | the cyst was adherent to the coeliac axis |
| `PMC5137649_01:e42` | `PMC5137649_01` | `PMC5137649_01:F13` | `PMC5137649_01:A7` | `LOCATED_IN` | `{"trigger": "adherent to", "certainty": "asserted"}` | 1474 | 1515 | the cyst was adherent to the coeliac axis |
| `PMC5137649_01:e43` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:T3` | `TREATED_WITH` | `{"trigger": "was performed", "certainty": "asserted"}` | 1729 | 1856 | an enbloc resection of the cyst along with a portion of the posterior wall of the stomach with a surgical stapler was performed |
| `PMC5137649_01:e44` | `PMC5137649_01` | `PMC5137649_01:T3` | `PMC5137649_01:A6` | `LOCATED_IN` | `{"trigger": "a portion of", "certainty": "asserted"}` | 1772 | 1818 | a portion of the posterior wall of the stomach |
| `PMC5137649_01:e45` | `PMC5137649_01` | `PMC5137649_01:T3` | `PMC5137649_01:F14` | `REVEALS` | `{"trigger": "was noted to be", "certainty": "asserted"}` | 1606 | 1682 | the gastric duplication cyst was noted to be arising from the posterior wall |
| `PMC5137649_01:e46` | `PMC5137649_01` | `PMC5137649_01:F14` | `PMC5137649_01:A6` | `LOCATED_IN` | `{"trigger": "arising from", "certainty": "asserted"}` | 1651 | 1682 | arising from the posterior wall |
| `PMC5137649_01:e47` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:E7` | `UNDERWENT_EXAM` | `{"trigger": "Repeat", "certainty": "asserted"}` | 1858 | 1901 | Repeat oesophagogastroduodenoscopy revealed |
| `PMC5137649_01:e48` | `PMC5137649_01` | `PMC5137649_01:E7` | `PMC5137649_01:F15` | `REVEALS` | `{"trigger": "revealed", "certainty": "asserted"}` | 1893 | 1969 | revealed the presence of an intact staple line on the posterior stomach wall |
| `PMC5137649_01:e49` | `PMC5137649_01` | `PMC5137649_01:E7` | `PMC5137649_01:F16` | `REVEALS` | `{"trigger": "and no evidence of", "certainty": "asserted"}` | 1918 | 2005 | an intact staple line on the posterior stomach wall and no evidence of bleeding or leak |
| `PMC5137649_01:e50` | `PMC5137649_01` | `PMC5137649_01:E7` | `PMC5137649_01:F17` | `REVEALS` | `{"trigger": "and no evidence of", "certainty": "asserted"}` | 1918 | 2005 | an intact staple line on the posterior stomach wall and no evidence of bleeding or leak |
| `PMC5137649_01:e51` | `PMC5137649_01` | `PMC5137649_01:F15` | `PMC5137649_01:A6` | `LOCATED_IN` | `{"trigger": "on the", "certainty": "asserted"}` | 1918 | 1969 | an intact staple line on the posterior stomach wall |
| `PMC5137649_01:e52` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:F18` | `HAS_FINDING` | `{"trigger": "were uninvolved", "certainty": "asserted"}` | 2007 | 2040 | The gross margins were uninvolved |
| `PMC5137649_01:e53` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:E8` | `UNDERWENT_EXAM` | `{"trigger": "revealed", "certainty": "asserted"}` | 2043 | 2067 | Final pathology revealed |
| `PMC5137649_01:e54` | `PMC5137649_01` | `PMC5137649_01:E8` | `PMC5137649_01:F19` | `REVEALS` | `{"trigger": "revealed", "certainty": "asserted"}` | 2043 | 2129 | Final pathology revealed a 9.5cm × 4.5cm × 2.0cm cyst with a smooth internal cyst wall |
| `PMC5137649_01:e55` | `PMC5137649_01` | `PMC5137649_01:F19` | `PMC5137649_01:D2` | `SUPPORTS` | `{"trigger": "consistent with", "certainty": "asserted"}` | 2102 | 2151 | a smooth internal cyst wall consistent with a GDC |
| `PMC5137649_01:e56` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:D2` | `DIAGNOSED_WITH` | `{"trigger": "consistent with", "certainty": "asserted"}` | 2043 | 2151 | Final pathology revealed a 9.5cm × 4.5cm × 2.0cm cyst with a smooth internal cyst wall consistent with a GDC |
| `PMC5137649_01:e57` | `PMC5137649_01` | `PMC5137649_01:D2` | `PMC5137649_01:D1` | `REVISES` | `{"trigger": "Final pathology revealed", "certainty": "asserted"}` | 2043 | 2151 | Final pathology revealed a 9.5cm × 4.5cm × 2.0cm cyst with a smooth internal cyst wall consistent with a GDC |
| `PMC5137649_01:e58` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:O1` | `HAS_OUTCOME` | `{"trigger": "was discharged home on", "certainty": "asserted"}` | 2164 | 2218 | The patient was discharged home on postoperative day 4 |
| `PMC5137649_01:e59` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:O2` | `HAS_OUTCOME` | `{"trigger": "without any", "certainty": "asserted"}` | 2235 | 2286 | tolerating a regular diet without any complications |
| `PMC5137649_01:e60` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:O3` | `HAS_OUTCOME` | `{"trigger": "she had", "certainty": "asserted"}` | 2302 | 2352 | she had complete resolution of her pain and nausea |
| `PMC5137649_01:e61` | `PMC5137649_01` | `PMC5137649_01:P1` | `PMC5137649_01:O4` | `HAS_OUTCOME` | `{"trigger": "she had", "certainty": "asserted"}` | 2302 | 2405 | she had complete resolution of her pain and nausea, and a return to regular bowel function and activity |
---

## Anexo A — `case_text` de referência

Seção *Case history* de [PMC5137649](https://pmc.ncbi.nlm.nih.gov/articles/PMC5137649/) (Royal College of Surgeons of England, acesso aberto), quatro parágrafos unidos por `\n\n`. 2.406 caracteres. É contra esta string exata que os offsets da §9 foram calculados e verificados.

```text
A 44-year-old woman presented with a 3-day history of right flank and lower quadrant abdominal pain associated with nausea and constipation. Her past medical, family and medication history were otherwise non-contributory and her physical examination was unremarkable. She underwent contrast enhanced computed tomography, demonstrating a 6cm cystic lesion between the stomach and body/tail of the pancreas (Fig 1). She subsequently underwent EUS-FNA, which revealed normal pancreatic echotexture and a cyst measuring 6cm × 9cm that was free of internal septations or associated masses (Fig 2) but compressed the stomach. FNA of the cyst demonstrated no evidence of malignancy but did show the presence of extracellular mucin as well as a carcinoembryonic antigen (CEA) level of 12,476.5ng/ml and a carbohydrate antigen (CA) 19-9 level of 6iu/ml, suggesting the diagnosis of a mucinous pancreatic cystic neoplasm. The patient was therefore referred for surgical resection.

A laparoscopic distal pancreatectomy was planned. At the time of the laparoscopic exploration, entrance to the lesser sac was first obtained and, on mobilising the posterior wall of the stomach, the lesion was noted to be tightly adherent to both the stomach and pancreas. The pancreas was mobilised free of the cyst and it was evident that the lesion originated from the stomach. Intraoperative endoscopy was performed and no mucosal abnormalities of the stomach were noted.

On further mobilisation, the cyst was adherent to the coeliac axis and the procedure was converted to an open resection. The stomach was fully mobilised and the gastric duplication cyst was noted to be arising from the posterior wall. It was dissected off the coeliac vessels and an enbloc resection of the cyst along with a portion of the posterior wall of the stomach with a surgical stapler was performed. Repeat oesophagogastroduodenoscopy revealed the presence of an intact staple line on the posterior stomach wall and no evidence of bleeding or leak. The gross margins were uninvolved.

Final pathology revealed a 9.5cm × 4.5cm × 2.0cm cyst with a smooth internal cyst wall consistent with a GDC (Figs 3–5). The patient was discharged home on postoperative day 4, doing well and tolerating a regular diet without any complications. On follow-up, she had complete resolution of her pain and nausea, and a return to regular bowel function and activity.
```
