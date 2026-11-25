# Projeto 3 — divisão de tarefas e contratos

Este documento é para quem vai implementar uma frente do Projeto 3, pessoa ou assistente de código.
Antes de começar, leia também:

- [`visao-geral.md`](visao-geral.md): o que o projeto faz e por quê (etapas 1 a 8);
- [`vazamento-de-dados.md`](vazamento-de-dados.md): regras que **toda** frente deve cumprir;
- [`../../project2/README.md`](../../project2/README.md): o pipeline que estamos estendendo.

**Resumo em uma frase:** um LLM ("professor") extrai menções clínicas de parte do MultiCaRe; um modelo
pequeno ("aluno") aprende com ele e extrai o corpus inteiro; o pipeline do P2 monta os grafos; uma
aplicação de **diagnóstico diferencial com RAG sobre o grafo** usa esse corpus.

## Quem faz o quê

| Frente | Etapas | Responsável | Pasta de código | Saída principal |
|---|---|---|---|---|
| A. Dados e avaliação da extração | 1, 4 e 6 | George | `src/dados/`, `src/avaliacao/` | divisões, MACCROBAT convertido, grafo do corpus, tabela P1 × P2 × P3 |
| B. Professor e destilação | 2 e 3 | Caio | `src/llm/`, `src/professor/`, `src/aluno/` | menções do LLM, modelo aluno |
| C. Normalização e avaliação do diagnóstico | 5 e 8 | Lucas | `src/normalizacao/`, `src/avaliacao_diagnostico/` | `mesh` preenchido, tabela top-k |
| D. Motor de diagnóstico (busca + RAG) | 7 | Gabriel | `src/diagnostico/` | `sugerir()` e predições |
| E. Interface e visualizador | 7 | João | `src/app/`, visualizador | aplicação e grafos P3 no site |

Todas as pastas acima ficam em `project3/`.

## Regras gerais (valem para todas as frentes)

1. **Estender, não reescrever.** Importe o P2 (`from project2.src.comum import ...`, `montagem.montar`,
   `relacoes prever`, `avaliacao.avaliar`). Não copie código do P2 para o P3 e não altere `project1/`
   nem `project2/`. Se precisar de uma mudança lá, abra uma issue.
2. **Mesmos contratos do P2.** Os mesmos tipos de entidade, relações e colunas de CSV (seção
   [Contratos](#contratos)). Não crie tipo, relação ou coluna nova sem atualizar este documento.
3. **Texto e offsets.** Leia os casos com `project2.src.comum` (`iter_casos`, `iter_registros`).
   Offsets são índices de caractere Python em `[start, end)` sobre o `case_text` original, com
   `texto == case_text[start:end]`. Nunca normalize o texto antes de calcular offsets.
4. **Gabarito é sagrado.** Os casos de `project2/data/gold/casos.txt` e a partição `teste` de
   `divisoes.csv` não entram em treino, nem em exemplos de prompt, nem no ajuste de prompt ou de
   hiperparâmetros. Use `casos_gold()` e a partição `validacao` para ajustar.
5. **Toda chamada de LLM passa pelo cliente comum** (`project3/src/llm/`), que guarda as respostas em
   cache. Não chame a API do provedor diretamente.
6. **Segredos.** Chave de API só por variável de ambiente (`P3_LLM_API_KEY`). Nunca em código,
   notebook ou commit.
7. **O que vai para o git.** Código, testes, README e entradas feitas à mão (`divisoes.csv`,
   prompts, mapeamentos). **Não** vão: cache de LLM, modelos treinados, corpus, CSVs gerados. Eles
   entram no `.gitignore` e o README do módulo diz como gerá-los. Exceção: `data/resultados/` e um
   grafo de exemplo, que o README final cita por link.
8. **Forma de cada módulo** (igual ao P2): pasta com `__init__.py`, `README.md` no modelo da seção
   [Documentação de cada módulo](#documentação-de-cada-módulo), `requirements.txt` se tiver
   dependência nova, testes `unittest` em `tests/`.
   Execução a partir da raiz: `python -m project3.src.<modulo>.<arquivo> <subcomando>`.
9. **Idioma.** Nomes de funções, variáveis, colunas, README e mensagens de commit em português, como
   no P2. Nomes de tipos e relações em inglês (`Symptom`, `HAS_SYMPTOM`), como no esquema.
10. **Não bloqueie ninguém.** Enquanto a etapa anterior não fica pronta, use as saídas do P2
    (`project2/data/mencoes_tipadas.csv`, `project2/data/relacoes.csv`, `project2/data/grafo/`), que já
    seguem o mesmo contrato.

## Estrutura de pastas

Segue o template da disciplina:

~~~
project3/
├── README.md                 <- entrega final (template do professor)
├── docs/                     <- estes documentos
├── data/
│   ├── external/             <- MACCROBAT original (não versionado)
│   ├── interim/              <- cache de LLM, menções intermediárias (não versionado)
│   ├── processed/            <- grafos, índices de busca (não versionado)
│   ├── divisoes.csv          <- partições treino/validação/teste (versionado)
│   └── resultados/           <- tabelas de métricas (versionado)
├── models/                   <- modelo aluno (não versionado)
├── pipelines/notebooks/      <- notebook de demonstração
├── src/                      <- código, um módulo por pasta
├── tests/
└── assets/{images,slides}/
~~~

## Contratos

### Tipos e relações (iguais ao P2)

Tipos de entidade: `History`, `Symptom`, `Finding`, `Exam`, `ExamResult`, `Diagnosis`, `Treatment`,
`Medication`, `AnatomicalSite`, `Outcome`. Mais `Patient` (sempre `P1`) e `Concept` (criado pela
montagem). Relações e domínios: `DOMINIO` em `project2/src/montagem/montagem.py`. Guia de anotação:
`project2/docs/guia-anotacao.md`.

### `divisoes.csv` (frente A, versionado)

| Coluna | Valores |
|---|---|
| `fonte` | `multicare` ou `maccrobat` |
| `case_id` | id do caso |
| `article_id` | PMCID (MultiCaRe) ou id do documento (MACCROBAT) |
| `particao` | `treino`, `validacao` ou `teste` |

- A divisão é **por `article_id`**: casos do mesmo artigo ficam sempre na mesma partição.
- Os 8 casos do gold do P2 são sempre `teste`.
- Semente fixa, gerada uma vez e commitada. Depois disso não muda.

### Menções tipadas (contrato de `project2/data/mencoes_tipadas.csv`)

`case_id, id, start, end, texto, tipo, mesh, polaridade, confianca, fonte`

- `polaridade`: `present` ou `absent`;
- `confianca`: entre 0 e 1;
- `mesh`: pode ficar vazio, e a frente C preenche;
- `fonte`: identifica quem gerou, por exemplo `llm:<modelo>`, `aluno:<versao>`, `lexico`.

### Relações (contrato de `project2/data/relacoes.csv`)

`case_id, origem, destino, relacao, confianca`. `origem` é `P1` ou o `id` de uma menção.

### Grafos (contrato do P1/P2)

Um par por caso, `<case_id>-nodes.csv` e `<case_id>-edges.csv`, gerado por `montagem.montar`.
Colunas em `NODE_COLUMNS` e `EDGE_COLUMNS` de `project2/src/montagem/montagem.py`.

### Predições de diagnóstico (frente D → frente C)

`data/processed/diagnostico/predicoes.csv`:

| Coluna | Descrição |
|---|---|
| `sistema` | `grafo`, `llm`, `rag_texto`, `rag_grafo` ou `rag_grafo_p2` |
| `case_id` | caso testado |
| `rank` | 1 a 5 |
| `mesh` | código MeSH do diagnóstico sugerido (vazio se não normalizou) |
| `rotulo` | texto do diagnóstico sugerido |
| `score` | pontuação usada na ordenação |
| `casos_fonte` | `case_id`s que justificam a sugestão, separados por `;` |

---

## Frente A — Dados e avaliação da extração (George)

**Objetivo:** preparar os dados que todos usam, rodar o aluno no corpus inteiro e produzir a tabela
de comparação da extração.

**Entregas, em ordem:**

1. **Corpus completo.** Reusar `python -m project2.src.comum.coletar`, que gera
   `project2/data/corpus/csv/full/{cases,metadata}.csv`. Verificar e documentar:
   - número de casos e de artigos;
   - se `metadata.csv` tem ano de publicação (a regra 5 de `vazamento-de-dados.md` depende disso).
2. **MACCROBAT.** Baixar para `data/external/maccrobat/` e verificar a licença. Converter para o
   contrato de menções em `data/interim/maccrobat/{casos,mencoes}.csv`. Fatos a respeitar:
   - O formato original é brat (`.txt` + `.ann`).
   - Os tipos dele não são os nossos. Escrever o mapeamento à mão num arquivo versionado
     (`src/dados/mapa_maccrobat.csv`) e descartar os tipos sem equivalente (por exemplo `Age`, `Date`,
     `Severity`).
   - Não há equivalente direto para `Finding`. Documentar a decisão.
   - As relações do MACCROBAT (temporais, `MODIFY`…) não correspondem às nossas. Use o MACCROBAT
     **só para menções e tipos**.
   - Se não houver anotação de negação, deixar `polaridade` vazia e avaliar só fronteira e tipo.
3. **`divisoes.csv`**, conforme o contrato acima. Esta é a primeira entrega da frente e destrava
   as frentes B e C.
4. **Grafo do corpus (Etapa 4).** Pegar `aluno/mencoes_tipadas.csv` da frente B e encadear:
   1. `python -m project2.src.relacoes.relacoes prever --entrada <menções> --saida <relações>`;
   2. `python -m project2.src.montagem.montagem --mencoes ... --relacoes ... --corpus ... --saida data/processed/grafo/aluno/`.

   O resultado deve processar o corpus em lotes e poder retomar de onde parou.
5. **Avaliação da extração (Etapa 6).** Reusar `project2/src/avaliacao/avaliar.py`
   (`avaliar_mencoes`, `avaliar_tipos`, `avaliar_relacoes`, `avaliar_grafo`). Sistemas avaliados:
   - regras P1, P2, professor (LLM) e aluno;
   - no gold do P2 e na partição `teste` do MACCROBAT.

   Colunas adicionais: `alucinacoes` (menções descartadas por não existirem no texto),
   `segundos_por_caso` e `custo_usd_por_caso`. Saída em `data/resultados/extracao.csv`.

**Pronto quando:** `divisoes.csv` commitado com teste que garanta (a) nenhum `article_id` em duas
partições e (b) os 8 casos gold em `teste`; tabela de extração gerada por um único comando.

---

## Frente B — Professor e destilação (Caio)

**Objetivo:** extrair menções com LLM e treinar um modelo pequeno que o imite.

**Entregas, em ordem:**

1. **Cliente LLM comum** (`src/llm/`), a primeira entrega da frente, porque C e D dependem dele:

   ~~~python
   def chamar(prompt: str, *, sistema: str = "", modelo: str | None = None,
              json: bool = False, temperatura: float = 0.0) -> Resposta: ...
   # Resposta: texto, modelo, tokens_entrada, tokens_saida, segundos, do_cache
   ~~~

   - Cache em disco em `data/interim/cache_llm/`, com chave = hash de (modelo, sistema, prompt,
     temperatura).
   - Modelo padrão vindo de `P3_LLM_MODELO`.
   - Provedor trocável (API ou local via Ollama) sem mudar quem chama.
   - Registra uso em `data/interim/uso_llm.csv`.
2. **Professor (Etapa 2)** (`src/professor/`):
   - **Prompt:** definições dos 10 tipos (tiradas do guia de anotação) e regra de polaridade.
     Exemplos few-shot vêm **só** da partição `treino` (MACCROBAT ou silver). Prompts ficam versionados
     em arquivos `.md` ou `.txt`, não embutidos no código.
   - **Saída do LLM:** JSON com `texto`, `tipo`, `polaridade`.
   - **Ancoragem:** localizar cada `texto` no caso e calcular `start` e `end`.
     - Se o texto aparece mais de uma vez, usar a ocorrência na frase processada.
     - Se não aparece, descartar a menção e registrar em `alucinacoes.csv`
       (`case_id, texto, tipo, motivo`).
   - **Saída:** `data/interim/professor/mencoes_tipadas.csv`, com `fonte=llm:<modelo>`.
   - **Experimento de quebra de frases** (`breaking-sentences.md` do professor): uma variante que
     primeiro pede ao LLM para decompor a frase em proposições. Comparar com a extração direta na
     partição `validacao`.
   - Rodar em todo o `teste` (para a avaliação) e em N casos de `treino` (dados para o aluno).
     Definir N pelo custo medido nos primeiros 50 casos.
3. **Aluno (Etapa 3)** (`src/aluno/`):
   - **Treino:** com as menções do professor na partição `treino`, sem nenhum caso de `teste`.
   - **Modelo:** começar pelo CRF do P2 (`project2/src/entidades/`) retreinado com os rótulos do
     professor, que é a comparação mais limpa com o P2. Se houver tempo, um modelo BERT biomédico
     pequeno de classificação de tokens.
   - **Saída:** `aluno/mencoes_tipadas.csv` no mesmo contrato, com `fonte=aluno:<versao>`. O modelo
     vai para `models/aluno/`.
   - **Curva de aprendizado:** F1 do aluno em `validacao` com 10%, 25%, 50% e 100% dos rótulos do
     professor.

**Pronto quando:** `chamar` tem teste com um provedor falso (sem rede); professor e aluno geram
CSVs que passam na validação de contrato da montagem; a curva de aprendizado está em
`data/resultados/`.

---

## Frente C — Normalização e avaliação do diagnóstico (Lucas)

**Objetivo:** ligar cada menção ao código MeSH (Etapa 5) e medir o ajudante de diagnóstico (Etapa 8).

**Entregas:**

1. **Normalização** (`src/normalizacao/`):
   - **Entrada:** qualquer CSV de menções tipadas. **Saída:** o mesmo CSV com `mesh` preenchido e
     `mesh_score`.
   - **Vocabulário:** `project1/src/dicionarios/gazetteer/mesh_gazetteer.csv` (`term, code,
     preferred_term, category`, cerca de 174 mil termos).
   - **Método:** embeddings dos termos do MeSH, com índice salvo em `data/processed/indice_mesh/`.
     Para cada menção, o vizinho mais próximo e um limiar de similaridade; abaixo dele, `mesh` vazio.
     Sugestão de modelo: SapBERT ou outro específico para *entity linking* biomédico.
   - **Comparação:** contra a normalização do P2 (`rapidfuzz` + léxico), medindo a acurácia de código
     nas menções do gold que têm `mesh`.
   - **API:** `normalizar(textos: list[str], tipos: list[str]) -> list[tuple[str, float]]`. A
     frente D usa a mesma função para normalizar os diagnósticos sugeridos pelo LLM.
2. **Avaliação do diagnóstico** (`src/avaliacao_diagnostico/`):
   - **Conjunto de teste:** casos da partição `teste` do MultiCaRe com pelo menos um nó `Diagnosis`
     com `mesh`. A resposta certa são os códigos desses nós.
   - **Métricas:** top-1, top-3, top-5 e MRR por `sistema`, lidos de `predicoes.csv`. Considerar
     também um acerto "hierárquico" (código pai ou filho na árvore MeSH) como métrica separada,
     nunca misturada com o acerto exato.
   - **Testes de vazamento** (regra 6 de `vazamento-de-dados.md`). Um teste automático deve falhar se:
     - o código ou o rótulo do diagnóstico aparecer na consulta montada pela frente D;
     - algum `casos_fonte` tiver o mesmo `article_id` do caso testado.
   - **Análise de memorização:** as mesmas métricas separadas por ano de publicação (antes e depois
     da data de corte do LLM), se a frente A confirmar que o ano existe.
   - **Saída:** `data/resultados/diagnostico.csv`.

**Pronto quando:** normalização roda em qualquer CSV do contrato; a avaliação lê `predicoes.csv` de
mentira (escrita à mão no teste) e produz a tabela; os testes de vazamento existem e passam.

---

## Frente D — Motor de diagnóstico (Gabriel)

**Objetivo:** dado um conjunto de sintomas e achados, sugerir diagnósticos com base em casos
parecidos (Etapa 7).

**Entregas** (`src/diagnostico/`):

1. **Consulta a partir de um caso** (para avaliação):

   ~~~python
   def montar_consulta(nodes: list[dict], edges: list[dict]) -> list[dict]:
       """Só nós Symptom, Finding e ExamResult com polarity=present ou absent preservada."""
   ~~~

   - É uma **lista do que pode entrar**: nada de `Diagnosis`, `Treatment`, `Medication`, `Outcome`,
     `Concept`, arestas `SUPPORTS`, título ou id do artigo (ver `vazamento-de-dados.md`).
   - Achados negados (`absent`) entram marcados como negados, porque também ajudam no diagnóstico.
2. **Índice de casos:**
   - Um vetor por caso a partir dos códigos MeSH dos nós permitidos acima (por exemplo TF-IDF sobre
     códigos), mais o texto desses nós para busca por embeddings.
   - **Entrada:** `data/processed/grafo/aluno/`. Até ele ficar pronto, usar `project2/data/grafo/`.
3. **`sugerir(consulta, k=5, sistema="rag_grafo", excluir_artigos=set()) -> list[Sugestao]`**:
   - Busca os casos mais parecidos e **sempre** remove os casos de `excluir_artigos`.
   - Monta o prompt para o LLM só com os nós permitidos desses casos e seus diagnósticos.
   - Pede ao LLM uma lista ordenada em JSON, cada item citando os `case_id`s de origem.
   - Normaliza cada diagnóstico com `normalizar()` da frente C.
   - Chama o LLM pelo cliente comum.
4. **Sistemas de comparação** (mesma assinatura, valor de `sistema`):

   | `sistema` | Como funciona |
   |---|---|
   | `grafo` | Sem LLM: os casos vizinhos votam nos seus diagnósticos, com peso pela similaridade |
   | `llm` | Sem busca: o LLM recebe só a consulta |
   | `rag_texto` | Busca por embeddings sobre o `case_text` dos vizinhos, com os diagnósticos dos vizinhos permitidos e o do caso testado excluído |
   | `rag_grafo` | A proposta principal |
   | `rag_grafo_p2` | `rag_grafo` usando o grafo do P2 no índice |

5. **Lote de avaliação:** comando que roda todos os sistemas nos casos de teste e escreve
   `predicoes.csv`, passando sempre o `article_id` do caso testado em `excluir_artigos`.

**Pronto quando:** `sugerir` funciona sobre os grafos do P2; o lote gera `predicoes.csv` para os cinco
sistemas; o teste de vazamento da frente C passa.

---

## Frente E — Interface e visualizador (João)

**Objetivo:** a aplicação que uma pessoa usa e os grafos do P3 no site.

**Entregas:**

1. **Aplicação** (`src/app/`):
   - O usuário digita sintomas e achados (texto livre ou lista) e marca os negados.
   - A aplicação chama `sugerir()` da frente D e mostra:
     - os 5 diagnósticos com pontuação;
     - para cada um, os casos de origem, com o subgrafo e o trecho de evidência (`evidence_text`)
       do texto original.
   - Botão "carregar caso de exemplo": preenche com a consulta de um caso de teste.
   - Sugestão: Streamlit, que é Python e conversa direto com a frente D. Como o RAG chama o LLM, a
     aplicação **não** roda no GitHub Pages. Documentar como rodar localmente e, se possível,
     publicar no Hugging Face Spaces ou equivalente, com a chave de API configurada como segredo.
2. **Visualizador:** acrescentar a aba "Projeto 3" no visualizador do P2 (GitHub Pages), com os grafos
   do aluno para os 56 casos da amostra, mantendo as abas P1 e P2.
3. **Demonstração:** notebook em `pipelines/notebooks/` que roda o caminho completo em poucos casos,
   com cache de LLM para não exigir chave.

**Pronto quando:** a aplicação roda localmente com um comando documentado; a aba P3 aparece no site;
o notebook roda do início ao fim.

---

## Documentação de cada módulo

Cada módulo tem um `README.md` que diz **como usar**, não por que foi feito assim. Justificativas
vão na descrição do PR ou na mensagem de commit.

### Modelo

Use exatamente estas seções, nesta ordem:

~~~markdown
# <Nome do módulo> — Etapa <n> (Frente <letra>, <responsável>)

<2–3 frases: o que o módulo faz e qual problema resolve no pipeline.>

## Como rodar
<comandos copiáveis, a partir da raiz do repositório, na ordem de execução>

## Entradas e saídas
| Arquivo | Entrada/Saída | Colunas | Versionado? |
|---|---|---|---|

## API
<assinaturas das funções que outras frentes chamam, uma linha de descrição cada>

## Resultados
<1–3 números principais e link para data/resultados/...>

## Limitações
<lista curta do que não funciona ou ficou de fora>
~~~

Regras:

- **Cabe numa tela.** Detalhe técnico fica no código e nos testes.
- **Comandos testados:** só entram comandos que foram rodados de verdade.
- **Números com fonte:** todo resultado vem de um arquivo em `data/resultados/`, com link.
- **Sem repetir este documento:** para os contratos, linke a seção daqui e liste só o que for
  específico do módulo.

### Prompt para gerar o README

Ao terminar o módulo, cole no assistente de código:

> Leia `project3/docs/tarefas.md` (a seção da minha frente e a seção "Documentação de cada módulo")
> e o código em `project3/src/<modulo>/`. Escreva `project3/src/<modulo>/README.md` seguindo
> exatamente o modelo. Rode cada comando da seção "Como rodar" e inclua só os que funcionaram. Não
> invente números: tire os resultados de `project3/data/resultados/`. Máximo de uma tela.

### Revisão

- O README entra **no mesmo PR** do código. PR sem README não é aprovado.
- O revisor é de **outra frente** e segue o "Como rodar" do zero. Se travar, o README volta.
- O README principal do `project3` só linka os READMEs dos módulos na metodologia, como o P2 fez com
  `src/README.md`.

## Ordem e dependências

| Quem espera | O quê | De quem | Enquanto isso, usa |
|---|---|---|---|
| B, C, D | `divisoes.csv` | A | os 8 casos gold como teste |
| C, D | cliente LLM | B | chamadas diretas só em protótipo descartável |
| A (Etapa 4) | menções do aluno | B | menções do professor ou do P2 |
| D | `normalizar()` | C | `mesh` já presente nos grafos do P2 |
| D | grafo do corpus | A | `project2/data/grafo/` |
| C (Etapa 8) | `predicoes.csv` | D | CSV escrito à mão no teste |
| E | `sugerir()` | D | função falsa com resposta fixa |

Primeira semana: A entrega `divisoes.csv` e B entrega o cliente LLM. Todos os outros começam com os
substitutos da última coluna.

## Decisões em aberto

Quem tomar a decisão atualiza esta seção.

- **Modelo do LLM** (professor e RAG): API ou local. O cliente comum permite trocar; o ideal é
  rodar os dois e reportar ambos. O professor usa `claude-sonnet-5-5` pelo provedor `claude_cli`
  (login do Claude Code, sem chave de API).
- **N de casos do professor:** na amostra, todos os 38 de `treino` (US$ 0,048 e 22,6 s por caso,
  [`custo_professor.csv`](../data/resultados/custo_professor.csv)). No corpus completo, o limite é
  tempo e cota (~6 h por 1000 casos): decidir quando a frente A informar o tamanho.
- **Arquitetura do aluno:** CRF retreinado, e BERT pequeno se houver tempo.
- **Hospedagem da aplicação:** definida pela frente E.
