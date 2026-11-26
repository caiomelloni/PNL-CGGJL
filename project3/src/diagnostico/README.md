# Motor de diagnóstico diferencial — Etapa 7 (Frente D, Gabriel)

Recupera casos semelhantes a uma consulta de sintomas, achados e resultados de exames.
Sugere diagnósticos com votação entre casos ou com o cliente LLM do projeto e registra as fontes.

## Como rodar

Na raiz do repositório, com os grafos do P2:

```bash
python3 -m project3.src.diagnostico.lote \
  --sistemas grafo --aceitar-amostra --saida tmp/predicoes-grafo.csv
```

Se os grafos do P2 estiverem em outro diretório, passe `--grafos-p2 <pasta>`. O lote aceita
`--grafos`, `--corpus` e `--divisoes` para escolher as entradas. O corpus padrão é o MultiCaRe completo
quando existe, com o recorte do P1 como alternativa.

Para comparar os cinco sistemas após integrar as frentes A, B e C, instale as dependências dos
módulos e prepare o cliente LLM e o índice MeSH conforme os READMEs deles. A busca semântica recebe
um modelo SentenceTransformers ou o caminho de um modelo local.

```bash
python3 -m pip install -r project3/src/diagnostico/requirements.txt
python3 -m project3.src.diagnostico.lote --modelo-embeddings sentence-transformers/all-MiniLM-L6-v2
```

Sem modelo configurado a busca textual usa TF-IDF para desenvolvimento. Defina
`P3_DIAGNOSTICO_EMBEDDINGS` para usar o mesmo modelo na API e no lote. Os quatro sistemas que chamam
o LLM usam o mesmo cliente da Frente B. A CLI reporta a cobertura e a contagem de sugestões por sistema.

## Entradas e saídas

| Arquivo | Entrada/Saída | Colunas | Versionado? |
|---|---|---|---|
| `project3/data/processed/grafo/aluno/` | Entrada | Nós e arestas no contrato P2 | Não |
| `project2/data/grafo/` | Entrada | Nós e arestas no contrato P2 | Grafos da amostra |
| `project3/data/divisoes.csv` | Entrada | `fonte, case_id, article_id, particao` | Sim |
| MultiCaRe `cases.csv` ou recorte do P1 | Entrada | `case_id, case_text`, com `article_id` quando disponível | Corpus completo fora do Git |
| `project3/data/processed/diagnostico/predicoes.csv` | Saída | `sistema, case_id, rank, mesh, rotulo, score, casos_fonte` | Não |

## API

- `montar_consulta(nodes, edges)` devolve uma lista de itens com `type`, `label`, `mesh` e `polarity`.
- `sugerir(consulta, k=5, sistema="rag_grafo", excluir_artigos=None)` devolve sugestões ordenadas, com
  `rotulo`, `mesh`, `score` e `casos_fonte`. Para uma consulta de um caso conhecido, passe seu
  `article_id` em `excluir_artigos`.
- `Motor(...).analisar(...)` também expõe os casos recuperados e as parcelas de similaridade.

```python
from project3.src.diagnostico import sugerir

consulta = [{"type": "Symptom", "label": "chest pain", "polarity": "present", "mesh": "D002637"}]
sugestoes = sugerir(consulta, sistema="grafo")
```

Os modos `grafo`, `rag_grafo` e `rag_grafo_p2` buscam nos achados do grafo. O primeiro faz
votação ponderada pela similaridade. Os outros dois passam os achados e os diagnósticos dos
vizinhos ao LLM. O modo `rag_texto` busca pelos relatos integrais dos vizinhos e usa o mesmo
formato de contexto do RAG com grafo. O modo `llm` recebe só a consulta.

A busca no grafo combina similaridade MeSH (65%) e textual (35%) quando há correspondência de
códigos. Os códigos carregam a polaridade e a parte textual assume o peso inteiro quando não há
correspondência MeSH. O lote reserva os artigos do teste, tanto na busca quanto no ajuste do
TF-IDF. O prompt usa referências locais aos casos recuperados e a API as converte nos
`case_id` originais. O motor descarta citações fora dos casos recuperados.

## Resultados

As métricas dos cinco sistemas serão produzidas pela Frente C após a integração com os grafos
do aluno, as partições do MultiCaRe e o cliente LLM.

## Limitações

- A qualidade das sugestões depende dos achados e diagnósticos extraídos. Alguns grafos do P2
  produzem uma consulta vazia ou sem vizinhos úteis. A montagem também remove achados cujo
  rótulo ou código revela um diagnóstico do mesmo caso.
- O score do grafo representa voto relativo e o score do LLM ordena sugestões. O significado
  desses valores depende do método.
- O índice é montado em memória. O custo no corpus completo e a qualidade dos embeddings
  dependem do tamanho dos dados e do modelo configurado.
