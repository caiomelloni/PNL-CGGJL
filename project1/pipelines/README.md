# Grafo combinado em lote

A pipeline é o notebook [grafo_combinado_lote.ipynb](notebooks/grafo_combinado_lote.ipynb).
Ele configura a entrada e a seleção de casos, executa o processamento, gera os
CSVs e apresenta o relatório e uma prévia dos resultados.

## Preparação

Execute os comandos a partir da raiz do repositório. No Windows/PowerShell:

```powershell
py -3 -m venv .venv
.venv/Scripts/python.exe -m pip install -r project1/src/grafo_lote/requirements.txt
.venv/Scripts/python.exe -m nltk.downloader -d .venv/nltk_data punkt_tab
```

Em Linux/macOS, use `python3 -m venv .venv` e `.venv/bin/python` nos demais comandos.
Abra o notebook no VS Code/Jupyter e selecione o Python do ambiente `.venv` como
kernel, com essas dependências e acesso ao `punkt_tab`.
A pipeline não baixa recursos durante o processamento. Os gazetteers e o modelo
HMM são lidos de `project1/src/`, independentemente do diretório de execução.

Salve o [CSV da disciplina](https://raw.githubusercontent.com/santanche/nlp2learn/main/projects/2026/project1/sample/cases.csv)
em `project1/sample/cases.csv`. A pasta `sample/` é ignorada pelo Git. A entrada
precisa das colunas `article_id`, `age`, `case_id`, `case_text` e `gender`.

## Execução

No novo notebook, ajuste a célula de configuração:

```python
CASOS = ROOT / "sample" / "cases.csv"
SAIDA = ROOT / "data" / "processed"
CASE_IDS = None  # todos os casos
# CASE_IDS = ["PMC5137649_01", "PMC3437073_01"]  # subconjunto
```

Execute todas as células em ordem. Os arquivos são gravados pela célula de
processamento; as células seguintes mostram o resumo, as pendências e uma prévia
dos CSVs. Não é necessário executar um script separado.

O lote lê o CSV uma vez, carrega MeSH, anatomia, HMM e stopwords uma vez e
processa sequencialmente na ordem da entrada. Cada caso usa um novo grafo e
normalizador, de modo que IDs, siglas e menções não vazem entre casos.
IDs solicitados que não existam aparecem como erro no relatório. IDs duplicados
na entrada são rejeitados para evitar sobrescrever um caso com outro.

Cada caso exportado gera `<case_id>-nodes.csv` e `<case_id>-edges.csv`, com as
mesmas colunas, ordem, IDs e serialização do notebook original. As duas tabelas
são serializadas em arquivos temporários antes da publicação. A substituição
é atômica por arquivo, não pelo par: uma falha de disco entre as substituições
pode deixar um par incompleto, identificado como erro no resumo.

## Relatório e falhas

`_resumo.csv` contém:

| Coluna | Conteúdo |
|---|---|
| `case_id` | Identificador do caso |
| `status` | `ok`, `com_inconsistencias` ou `erro` |
| `nos`, `arestas` | Quantidades no grafo produzido |
| `evidencias_desalinhadas` | Evidências cujo texto não corresponde aos offsets, ou cujos offsets estão incompletos/fora do texto |
| `arestas_fora_do_dominio` | Relações desconhecidas, com tipos incompatíveis ou extremidades ausentes |
| `tempo_s` | Tempo do caso em segundos, incluindo validação e exportação; exclui a carga inicial de recursos |
| `erro` | Tipo e mensagem da exceção, quando houver |

As inconsistências não impedem a exportação e não são tratadas com `assert`.
O status `ok` indica que essas verificações passaram, não uma avaliação da
qualidade clínica da extração. As relações conceituais `SAME_AS`, sem evidência
textual, não entram na contagem de offsets.

Uma falha de conversão, processamento ou exportação fica no resumo e no log,
e o próximo caso continua. Contadores ainda não calculados ficam vazios.
O resumo é atualizado após cada caso; não é necessário esperar o lote terminar.
Erros globais (CSV/cabeçalho inválido, recursos ausentes ou impossibilidade de
gravar o resumo) encerram a execução.

Cada execução substitui `_resumo.csv`, que descreve apenas os casos selecionados.
CSVs fora da seleção e saídas antigas de casos que falharam permanecem no disco;
consulte o status do resumo antes de consumir esses arquivos. Use outra `SAIDA`
para preservar resultados de uma execução anterior.

No notebook, consulte a coluna `status` para verificar a conclusão de cada caso.

## API e testes

O módulo oferece `carregar_recursos()`, `processar_caso(caso, recursos,
inspecionar=False)` e `validar_grafo(caso, resultado)`. `ResultadoCaso` contém
`nos`, `arestas`, `grafo` e, quando solicitado, `inspecao` com os dados
intermediários. A função de processamento não imprime nem grava arquivos.

```powershell
.venv/Scripts/python.exe -m unittest discover -s project1/src/grafo_lote/tests -v
.venv/Scripts/python.exe -m unittest discover -s project1/src/normalizacao/tests -t project1/src -v
```
