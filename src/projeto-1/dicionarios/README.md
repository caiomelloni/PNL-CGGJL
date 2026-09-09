# Dicionários, tesauros e ontologias — issue #6

> Parte do Projeto 1 (MC896, 2026). Ver o contrato comum das issues #3–#6, as entidades/atributos em [`docs/projeto-1/01-dados-a-extrair.md`](../../../docs/projeto-1/01-dados-a-extrair.md) e o esquema do grafo em [`docs/projeto-1/02-esquema-grafo.md`](../../../docs/projeto-1/02-esquema-grafo.md).

Este README acompanha o desenvolvimento do pipeline: cada processo abaixo ganha sua descrição quando é implementado, e a seção de progresso no final é atualizada a cada fase concluída.

## O pipeline

A partir de um `case_id`, o texto do caso (`case_text`) passa pelos seguintes processos até virar as tabelas de nós e arestas:

1. **Leitura do caso.** Localiza a linha correspondente ao `case_id` em `sample/cases.csv` e recupera o texto bruto. Sem isso não há o que processar — é a entrada do pipeline.

2. **Normalização do texto.** Reduz o texto a uma forma canônica (minúsculas, tokenização, tratamento de pontuação e parênteses) antes de qualquer comparação. A importância: sem normalizar, `"Type 2 Diabetes Mellitus"` e `"type 2 diabetes mellitus"` seriam tratadas como strings diferentes e o casamento com o dicionário falharia por uma diferença que não tem relevância clínica nenhuma. A mesma função é aplicada tanto ao texto do caso quanto às entradas do gazetteer (processo 3) — se normalizássemos os dois de formas diferentes, o casamento não funcionaria nem para os casos mais óbvios.

3. **Construção do gazetteer a partir do MeSH.** Processa o thesaurus MeSH (arquivo `desc2026.xml`) e monta uma estrutura de busca rápida que mapeia cada termo — o nome oficial de um conceito e todos os seus sinônimos (*entry terms*) — para um código estável (ex. `D003924`). Sem esse pré-processamento, cada consulta exigiria varrer o XML inteiro do MeSH, e não haveria como saber que `"T2DM"` e `"type 2 diabetes mellitus"` apontam para o mesmo conceito — essa equivalência já vem catalogada no MeSH como sinônimos do mesmo *descriptor*.

4. **Extração de menções candidatas (NER baseado em regras).** Antes de tentar casar qualquer coisa com o dicionário, é preciso decidir *quais trechos* do texto são candidatos a entidade (um sintoma, um diagnóstico, um exame...). Isso é feito com regras determinísticas — padrões de POS-tagging, gatilhos lexicais (`presented with`, `diagnosed with`) — sem modelo de linguagem. Sem esse passo, só seria possível comparar palavra por palavra contra o dicionário, perdendo conceitos de mais de uma palavra (`"chronic kidney disease"`) e desperdiçando tempo comparando palavras irrelevantes do texto (artigos, verbos, etc.).

5. **Casamento (matching) com o gazetteer.** Cada menção candidata é comparada contra o gazetteer em ordem de rigor decrescente: primeiro **exact match** (string idêntica após normalização), depois **longest match** (para conceitos multi-palavra, tentando a maior janela de tokens antes de janelas menores) e por fim **fuzzy match** (distância de edição, para pegar variações não previstas como erros de digitação), com um threshold de similaridade e uma regra de desempate quando mais de um conceito casa. A importância de encadear as três, em vez de usar só uma: exact match sozinho tem cobertura baixa (só pega o que já está listado literalmente como sinônimo); fuzzy match sozinho, sem as etapas mais estritas antes, arrisca casar termos parecidos que não deveriam ser equivalentes.

6. **Ligação ao grafo (`Concept` + `SAME_AS`).** Toda menção que teve casamento bem-sucedido gera um nó `Concept` (com `vocabulary`, `code` e `preferred_term`) e uma aresta `SAME_AS` ligando a entidade original a esse conceito. Menções sem casamento continuam como nó normal, sem `Concept`/`SAME_AS`. Sem esse passo, o resultado do matching ficaria só na memória do programa — é aqui que ele vira, de fato, parte das tabelas de nós e arestas exigidas pelo contrato.

7. **Validação cruzada com `mesh_terms`.** Compara os conceitos MeSH que o pipeline encontrou no texto do caso com a lista de `mesh_terms` que o próprio artigo já tem em `metadata.csv` (atribuída por curadores humanos do PubMed). A importância: como não existe um gabarito anotado à mão para os casos desta amostra, essa comparação é o único sinal independente de que o casamento está encontrando conceitos plausíveis — mesmo sabendo que `mesh_terms` descreve o artigo inteiro, não o caso específico, então não deve ser tratado como gabarito perfeito.

8. **Gazetteer próprio para `AnatomicalSite`.** Sítios anatômicos não têm, neste projeto, um vocabulário oficial associado — por isso essa categoria usa uma estrutura equivalente ao gazetteer do MeSH, mas com códigos internos (`ANAT001`, `ANAT002`, ...) definidos e curados por nós. A abordagem concreta para essa parte ainda está em definição (adiada deliberadamente — ver progresso abaixo).

## Progresso

- **Leitura do caso (1) e insumos para a normalização (2):** ambiente configurado (`nltk`, `rapidfuzz`) e `sample/cases.csv`/`sample/metadata.csv` inspecionados de verdade — 56 casos de 50 artigos, formato de `case_text` e das colunas de lista de `metadata.csv` confirmados. `mesh_terms` (necessário para o processo 7) usa um formato próprio de lista entre colchetes com escape de aspas (ex. `'Research Support, Non-U.S. Gov\'t'`); um parser dedicado para esse formato já foi implementado e validado nos 50 artigos da amostra.

- **Construção do gazetteer a partir do MeSH (processo 3):** feita. `desc2026.xml` (NLM, ~313 MB) baixado localmente (não versionado — ver `.gitignore`) sob licença pública, com atribuição obrigatória à NLM ([termos oficiais](https://www.nlm.nih.gov/databases/download/terms_and_conditions_mesh.html)), sem restrição de redistribuição. Parser em streaming implementado em `mesh_parser.py` (`iterparse`, sem carregar a árvore inteira em memória — 31.110 descriptors processados em ~3,6s). A restrição "procurar só na categoria certa do MeSH" é implementada filtrando por prefixo do `TreeNumber` na hora de **construir** o gazetteer (não na hora de buscar) — descriptors fora do prefixo nunca entram no dicionário daquela categoria:

  | Entidade (doc 01) | Sub-ramo MeSH | Termos (com sinônimos) | Descriptors únicos |
  |---|---|---:|---:|
  | `Diagnosis`, `History`, `Symptom`, `Finding` | `C` — Diseases | 58.284 | 5.069 |
  | `Medication` | `D` — Chemicals and Drugs | 94.012 | 10.688 |
  | `Exam` | `E01` — Diagnosis (técnicas) | 7.787 | 784 |
  | `Treatment` | `E02`+`E04` — Therapeutics / Surgical Procedures | 11.076 | 1.236 |
  | `Diagnosis` (psiquiátrico) | `F03` — Mental Disorders | 3.063 | 235 |
  | `AnatomicalSite`, `Patient`, `ExamResult`, `Outcome` | *(nenhum)* | — | — |

  Validado com termos reais do caso de exemplo: `"Type 2 Diabetes Mellitus"` e `"NIDDM"` resolvem para o mesmo código (`D003924`) que `"Diabetes Mellitus, Type 2"`; `"Pancreatitis"` → `D010195`; `"Oseltamivir"` → `D053139`. Uma limitação real já observada: `"CT"` (sigla) **não** está cadastrada como sinônimo de `Tomography, X-Ray Computed` no MeSH — siglas curtas/ambíguas em geral não entram no thesaurus, então precisam ser resolvidas dentro do próprio caso (padrão `termo por extenso (SIGLA)`), não via o dicionário.

- **Normalização (processo 2):** implementada em `normalization.py`. Escopo mínimo por decisão deliberada: NFKC + lowercase + remoção de pontuação nas bordas do token, **sem stemming, lematização ou remoção de stop-words** — variação morfológica não coberta pelo MeSH fica a cargo do fuzzy match (processo 5), não da normalização; ver justificativa completa nas notas de progresso da Fase 2 abaixo. A normalização nunca sobrescreve o texto original: só gera a chave usada para consulta no gazetteer, o `label` do nó continua com o texto tal como apareceu no caso (evita ter que reconstruir manualmente a grafia de termos sensíveis a maiúscula, como `IgG`/`CA 19-9`).

  Testado com os casos difíceis que o próprio doc 01 já sinalizava: `"(CEA)"` → `"cea"` (parênteses descartados), `"CA 19-9"` → `"ca 19-9"` (hífen interno preservado pelo tokenizador), `"IgG"` → `"igg"`, `"Diabetes Mellitus, Type 2"` e `"Type 2 Diabetes Mellitus"` → ambos sem a vírgula. Reaplicando aos ~58 mil termos do gazetteer da categoria `C`, o número de chaves caiu de 58.284 para 58.062 — a diferença são colisões de maiúscula/pontuação que agora compartilham uma única entrada.

  **Bug real encontrado e corrigido durante o teste:** ao juntar tokens normalizados numa janela pra formar a chave de busca, um token que normaliza para string vazia (pontuação pura, ex. `"."`) podia ser silenciosamente absorvido dentro de uma janela — a chave ficava correta (o vazio some ao juntar), mas o span consumido incluía a pontuação (ex. `"constipation ."` em vez de `"constipation"`), o que arriscaria unir span através de fronteiras de frase em outros casos. Corrigido expondo `align_normalized_tokens()`, que descarta tokens vazios *antes* de qualquer janela ser formada, preservando o índice original de cada token restante para reconstruir o span correto depois.

- Os processos 4 (NER), 5 (matching), 6 (ligação ao grafo) e 7 (validação cruzada) ainda não têm código implementado. O processo 8 (gazetteer próprio de `AnatomicalSite`) segue adiado por decisão do autor.

## Limitações e discussão futura (notas para `docs/projeto-1/06-dicionarios.md`)

- **Um gazetteer sozinho não substitui o NER.** Cogitamos varrer o `case_text` inteiro direto contra o dicionário (sem uma etapa prévia de NER por regras) e descartamos essa ideia: (1) qualquer menção que não esteja cadastrada no MeSH nunca seria sequer candidata a nó — cobertura zero para o que o vocabulário não prevê, o que contradiz o contrato ("menção sem match ainda vira nó normal", já que sem NER não haveria "menção" para começo de conversa); (2) o dicionário não informa atributos como `polarity`/`duration`/`certainty` — isso só vem do contexto textual ao redor da menção (gatilhos do doc 01); (3) o mesmo conceito MeSH muda de tipo de entidade dependendo do gatilho ao redor (`"history of hypertension"` → `History`, `"diagnosed with hypertension"` → `Diagnosis`), algo que o dicionário não decide sozinho; (4) sem uma âncora de contexto, o risco de falso positivo (bater por coincidência com um termo médico obscuro) aumenta. Por isso o NER por regras (processo 4) continua necessário mesmo numa estratégia cujo foco é o dicionário — o dicionário entra depois, para enriquecer (ou não) uma entidade que o NER já decidiu que existe.

## Como reproduzir o experimento

*(seção a preencher quando o pipeline tiver um ponto de entrada único capaz de rodar sobre `sample/cases.csv`)*

Vai cobrir, no mínimo:
- como criar o ambiente virtual e instalar as dependências (`requirements.txt`);
- como (e de onde) obter o arquivo do MeSH (`desc2026.xml`) usado no processo 3, já que ele não é versionado no repositório;
- o comando para rodar o pipeline sobre um `case_id` específico e onde as tabelas de nós/arestas resultantes são salvas;
- o comando para rodar em lote sobre todos os casos da amostra e gerar o relatório de validação cruzada do processo 7.
