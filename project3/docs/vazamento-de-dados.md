# Vazamento de dados: o que é e como evitar

## O que é vazamento de dados

É quando a resposta chega, sem querer, ao sistema que está sendo testado. Parece que ele acertou por ser bom, mas ele acertou porque viu a resposta. É como um aluno tirar 10 porque o gabarito estava grampeado na prova: a nota não mostra nada sobre o que ele sabe.

O perigo é que vazamento não dá erro nenhum. O resultado só fica bom demais, e a gente comemora uma coisa falsa.

## Onde pode vazar no nosso projeto

### No teste do ajudante de diagnóstico

**1. A doença dentro da consulta.** O texto do caso quase sempre fala o diagnóstico. Por isso a consulta é montada a partir do grafo, e não do texto. Mas não basta tirar só a bolinha `Diagnosis`, porque outras partes do grafo também entregam a resposta:

- **Tratamento:** "isoniazida + rifampicina" praticamente grita "tuberculose".
- **Arestas `SUPPORTS`:** elas apontam direto para o diagnóstico.
- **Desfecho e nós `Concept`** ligados ao diagnóstico.
- **Erros da extração:** o P2 às vezes classificava um diagnóstico como `Finding`. Se isso acontecer, a doença entra na consulta disfarçada de achado.

**Cuidado:** a consulta só pode ter o que se tem antes do diagnóstico: sintomas, achados e resultados de exame. Isso deve ser uma **lista do que pode entrar**, e não uma lista do que deve sair, para que um tipo novo nunca entre por acidente. Também precisamos de um teste automático que procure o nome e o código MeSH da doença dentro da consulta e falhe se encontrar.

**2. O próprio paciente na busca.** O RAG procura casos parecidos no grafo gigante. Se o paciente testado estiver lá, ele mesmo é o mais parecido, e o acerto vem de graça.

**Cuidado:** tirar o paciente da busca antes de cada teste. E não só ele: no MultiCaRe, um artigo pode ter vários casos (`PMC4782471_01`, `_02`…), muitas vezes da mesma doença. Então removemos **todos os casos do mesmo artigo** (mesmo PMCID).

**3. Os dados extras do artigo.** O título do artigo costuma dizer a doença ("A case of gastric duplication cyst"), e as palavras-chave e os termos MeSH do artigo também.

**Cuidado:** nada disso entra na consulta nem no prompt, nem o identificador do caso.

### Na extração

**4. O gabarito usado para treinar ou ajustar.** As 8 histórias do gabarito e a parte de teste do MACCROBAT são a prova. Elas nunca podem:

- estar nos dados de treino do aluno;
- aparecer como exemplo no prompt do LLM;
- ser usadas para ajustar o prompt. Se a gente mexe no prompt olhando a nota no gabarito até ela subir, o prompt fica decorado para aquela prova.

**Cuidado:**

- Separar o MACCROBAT em treino e teste **no começo**, salvar essa divisão num arquivo e nunca mais mudar.
- Ajustar prompt e modelo numa parte separada, de validação.
- Rodar no gabarito só no fim, como foi no P2 (`project2/data/gold/casos.txt`).

### No LLM

**5. O LLM pode já conhecer os casos.** Os relatos do MultiCaRe são públicos, então o LLM pode tê-los lido no treino dele e "lembrar" do diagnóstico. Isso não dá para impedir, mas dá para medir:

- a linha "só o LLM, sem consulta" mostra quanto ele acerta de memória;
- se os dados do MultiCaRe tiverem o ano de publicação, separamos um teste só com **casos publicados depois da data de corte do LLM**. Esses ele não pode ter visto. Se a nota cair muito nesse grupo, era memória.

## Regras do grupo

1. A consulta só leva sintomas, achados e resultados de exame, nunca diagnóstico, tratamento, desfecho ou título.
2. Antes de testar um caso, tiramos da busca todos os casos do mesmo artigo.
3. Gabarito e teste nunca entram em treino, exemplos do prompt ou ajuste.
4. A divisão treino/validação/teste é feita uma vez e salva.
5. Testamos separado os casos publicados depois da data de corte do LLM.
6. Um teste automático confere que a doença não aparece na consulta.
