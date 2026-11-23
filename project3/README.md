# Projeto `Extração de Grafos de Conhecimento Clínico com Modelos de Linguagem e Destilação para Apoio ao Diagnóstico Diferencial`
# Project `Clinical Knowledge Graph Extraction with Language Models and Distillation for Differential Diagnosis Support`

Equipe `CGGJL`: Caio Melloni (167974), Gabriel Lorhan Rodrigues Dourado (197496), George Henrique de Lima Sá (231529), João Vitor Gonçalves Oliveira (237871) e Lucas Guarnieri (119756).

## Slides

> Coloque aqui o link para o PDF da apresentação da parte 3.

## Demonstração Executável

> Coloque aqui um link para uma demonstração executável do seu código. Pode ser um Jupyter notebook (rodando no Binder ou no Colab) e/ou uma página Web que apresente visualmente seus resultados.
> Aqui deve constar também um link para a aplicação que usará a árvore de conhecimento.

## Metodologia

O Projeto 3 estende o pipeline do [Projeto 2](../project2/README.md) com modelos de linguagem. Um LLM ("professor") extrai menções clínicas de parte do MultiCaRe. Um modelo pequeno ("aluno") é treinado com essas extrações (destilação) e extrai o corpus completo. As etapas de relações e montagem do P2 geram os grafos. Uma aplicação de diagnóstico diferencial com RAG busca casos parecidos nesse grafo.

~~~mermaid
flowchart LR
    C["MultiCaRe completo"] --> L["Etapa 2: LLM professor<br/>menções tipadas"]
    M["MACCROBAT"] --> L
    L --> A["Etapa 3: aluno<br/>destilação"]
    A --> G["Etapa 4: corpus inteiro<br/>relações + montagem do P2"]
    G --> N["Etapa 5: normalização<br/>embeddings → MeSH"]
    N --> R["Etapa 7: diagnóstico<br/>diferencial com RAG"]
    L --> V1["Etapa 6: avaliação<br/>P1 × P2 × P3"]
    A --> V1
    R --> V2["Etapa 8: avaliação<br/>top-k"]
~~~

O plano detalhado está em [`docs/visao-geral.md`](docs/visao-geral.md), as tarefas e contratos entre módulos em [`docs/tarefas.md`](docs/tarefas.md) e os cuidados de avaliação em [`docs/vazamento-de-dados.md`](docs/vazamento-de-dados.md).

> Nesta seção podem aparecer destaques de código como indicado a seguir. Note que foi usada uma técnica de highlight de código, que envolve colocar o nome da linguagem na abertura de um trecho com `~~~`, tal como `~~~python`.
>
> Os destaques de código devem ser trechos pequenos de poucas linhas, que estejam diretamente ligados a alguma explicação. Não utilize trechos extensos de código. Se algum código funcionar online (tal como um Jupyter Notebook), aqui pode haver links. No caso do Jupyter, preferencialmente para o Binder abrindo diretamente o notebook em questão.

### Confronto com Trabalho Anterior

> Apresente dentro desta subseção um texto confrontando esta versão com a anterior. O confronto pode ser qualitativo ou baseado em comparações experimentais.

## Trabalhos Estudados

> Se foram feitas pesquisas de outros trabalhos, debata brevemente as referências.

## Fonte de Dados Adicionais

* **MACCROBAT** ([figshare](https://figshare.com/articles/dataset/MACCROBAT2018/9764942)): relatos de caso clínico anotados à mão com entidades. Serve de exemplos para o LLM, de dados de treino e de gabarito extra para avaliar a extração fora do MultiCaRe.
* **MeSH** (NLM): vocabulário controlado usado para normalizar as menções. Os códigos permitem comparar casos diferentes na aplicação de diagnóstico.

## Modelo Lógico

O modelo de grafo de propriedades é o mesmo do [Projeto 2](../project2/README.md#modelo-lógico).

![Modelo lógico do grafo de conhecimento clínico](../project2/assets/images/modelo-logico.svg)

## Análises que podem ser realizadas

> Apresente aqui uma análise  uma discussão de análises que podem ser realizadas com o seu grafo.

## Ferramentas

> Panorama das ferramentas utilizadas incluindo discussão sobre o uso das mesmas.

## Resultados

> Descrição e discussão dos resultados mais importantes obtidos.
>
> Você pode apresentar imagens apresentando o grafo e discutir o que obteve.

### Aplicação

> Como parte dos resultados, descreva a aplicação desenvolvida. Coloque capturas de tela de seu funcionamento.

## Como Modelos de Linguagem foram Usados

* **Extração (professor):** um LLM extrai menções, tipo e polaridade dos casos. Cada menção é ancorada no texto original e as que não existem no texto são descartadas e contadas como alucinação.
* **Destilação:** as extrações do LLM servem de dados de treino para um modelo pequeno, que extrai o corpus completo.
* **Normalização:** embeddings ligam cada menção ao código MeSH mais próximo.
* **Aplicação:** no RAG, o LLM recebe os casos mais parecidos recuperados do grafo e produz uma lista ordenada de diagnósticos, citando os casos de origem.

## Referências Bibliográficas

> Lista de artigos, links e referências bibliográficas.
>
> Fiquem à vontade para escolher o padrão de referenciamento preferido pelo grupo.
