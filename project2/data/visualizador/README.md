# Visualizador Interativo de Grafos — Projeto 2

Aplicação web estática (HTML5, CSS3, JavaScript ES6 puro e [Cytoscape.js](https://js.cytoscape.org/)) para exploração, inspeção e auditoria visual dos grafos de conhecimento clínico gerados pelo pipeline do Projeto 2.

A biblioteca Cytoscape.js está vendorizada localmente em `vendor/cytoscape.min.js`, permitindo execução 100% *offline*, sem necessidade de Node.js, `npm`, CDNs ou ferramentas de *bundling*.

---

## 1. Como Executar Localmente

A partir da raiz do repositório, inicie um servidor HTTP local apontando para o diretório do visualizador:

```bash
# Na raiz do repositório
python -m http.server 8000 --directory project2/data/visualizador
```

Em seguida, abra o navegador em:
👉 **`http://localhost:8000`**

---

## 2. Como os Dados são Gerados

Os dados de nós, arestas, evidências e textos dos casos são compilados a partir das saídas do pipeline pelo módulo de montagem ([`project2/src/montagem/montagem.py`](../../src/montagem/montagem.py)):

```bash
python -m project2.src.montagem.montagem --visualizador project2/data/visualizador
```

Este comando:
1. Lê as menções tipadas ([`data/mencoes_tipadas.csv`](../mencoes_tipadas.csv)) e relações com confiança ([`data/relacoes.csv`](../relacoes.csv)) do Projeto 2;
2. Lê os grafos processados da linha de base do Projeto 1 (`project1/data/processed/`, customizável via `--p1-grafos`);
3. Funde menções equivalentes, ancora nós ontológicos `Concept` (MeSH) via arestas `SAME_AS` e formata atributos;
4. Empacota ambos os grafos (`projeto1` e `projeto2`) em cada arquivo `data/<case_id>.json` e atualiza o manifesto `data/manifest.json`.

---

## 3. Funcionalidades do Visualizador

* **Abas Comparativas (Projeto 1 vs. Projeto 2):**
  - Barra de abas superior para alternar instantaneamente entre o grafo do **Projeto 1** (regras/heurísticas) e o do **Projeto 2** (modelos de ML e supervisão fraca) para o mesmo caso clínico;
  - Preserva a aba ativa ao navegar entre diferentes casos clínicos no seletor;
  - Permite auditoria visual direta da evolução: nós refinados, entidades desduplicadas, escores de confiança nas relações e redução de falsos positivos/negativos.
* **Seleção de Casos:** Menu superior para alternar dinamicamente entre os casos clínicos processados da amostra MultiCaRe.
* **Layout Interativo de Grafo:**
  - Nós codificados por cor de acordo com o tipo semântico (`Diagnosis`, `Symptom`, `Exam`, `Finding`, `AnatomicalSite`, etc.);
  - Nó especial do paciente (`P1`) e nós ontológicos MeSH (`Concept`);
  - Arestas direcionadas exibindo o tipo da relação e a **confiança estatística** predita pelo classificador (ex: `REVEALS 0.97`, `LOCATED_IN 0.99`).
* **Painel Lateral de Auditoria e Evidência:**
  - Ao clicar em um nó ou aresta, o painel lateral exibe seus atributos (`type`, `polarity`, `size`, `mesh`, `confidence`);
  - O texto clínico completo (`case_text`) é apresentado com o trecho exato de evidência (`evidence_text`) destacado em tempo real.
* **Filtros e Visualização de Polaridade:**
  - Identificação visual imediata de achados negados (`polarity=absent`) vs. confirmados (`polarity=present`).

---

## 4. Estrutura de Arquivos

```text
project2/data/visualizador/
├── index.html                        <- Estrutura da interface do visualizador
├── app.js                            <- Lógica de inicialização do Cytoscape.js e renderização
├── style.css                         <- Estilização visual e esquema de cores por tipo
├── vendor/
│   └── cytoscape.min.js              <- Biblioteca Cytoscape.js v3.x vendorizada
└── data/
    ├── manifest.json                 <- Lista dos casos clínicos disponíveis
    ├── PMC5137649_01.json            <- Dados do grafo e texto para o caso PMC5137649_01
    └── ...                           <- JSONs individuais dos demais casos
```
