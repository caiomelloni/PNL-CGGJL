# Projeto 3

## Antes de tudo: o que é o nosso projeto?

Imagine uma biblioteca com milhares de histórias de pacientes reais escritas por médicos. É o **MultiCaRe**. Cada história conta o que o paciente sentia, que exames fez, o que os exames mostraram, qual doença ele tinha e como foi tratado.

O problema é que essas histórias são texto corrido, difícil de um computador entender. Nosso trabalho é transformar cada história num **mapa de bolinhas e setas**, que chamamos de **grafo**:

```
(Paciente) ──sentia──► (febre)
(Paciente) ──fez──► (exame de sangue) ──mostrou──► (infecção)
(infecção) ──indica──► (endocardite)
```

Cada bolinha é uma coisa importante (sintoma, exame, doença, remédio) e cada seta diz como as coisas se ligam.

## O que já fizemos

- **Projeto 1:** escrevemos **regras na mão**, do tipo "se aparecer a palavra *febre*, é um sintoma". Funcionou um pouco, mas regras não pensam em tudo.
- **Projeto 2:** deixamos o computador **aprender sozinho com exemplos** (aprendizado de máquina). Ele ficou bom em dizer *que tipo* de coisa uma palavra é e *como* as coisas se ligam. Mas ficou muito ruim em **achar** as coisas no texto: das 224 coisas importantes que marcamos à mão, ele achou só 28. É como um detetive ótimo em resolver o caso, mas que não acha as pistas.

## O que vamos fazer agora

No Projeto 3 vamos usar um **LLM**, um modelo de linguagem como o ChatGPT ou o Claude. Ele lê muito bem e quase sempre acha as pistas. Só que tem um porém: é **caro e lento** para usar em milhares de histórias.

Então o plano é:

1. O LLM vira o **professor**.
2. Ele ensina um **aluno**, um modelo pequeno, barato e rápido.
3. O aluno lê a biblioteca inteira e monta um mapa gigante.
4. Com esse mapa, construímos um **ajudante de diagnóstico**: você conta os sintomas e ele sugere quais doenças podem ser, mostrando de onde tirou cada ideia.

## As etapas, uma por uma

### Etapa 1: juntar os materiais

Reunimos três coisas:

- **O MultiCaRe completo:** todas as histórias, não só as 56 que usamos até agora.
- **O MACCROBAT:** uma segunda coleção de histórias de pacientes em que pessoas já marcaram à mão onde estão os sintomas, exames, doenças etc. Serve como **gabarito extra** e como **exemplos** para o LLM. (O professor exige pelo menos uma fonte além do MultiCaRe.)
- **Nosso gabarito:** 8 histórias que marcamos à mão no Projeto 2. É a "prova corrigida" que usamos para dar nota a cada versão.

📦 **Produz:** as tabelas com todas as histórias, prontas para usar, e os gabaritos no mesmo formato.

### Etapa 2: o professor trabalha (LLM extrai)

Mandamos para o LLM uma história e um pedido: *"Ache aqui todos os sintomas, exames, achados, doenças e remédios. Diga também se cada coisa está presente ou foi descartada."* Junto, vão alguns exemplos de como responder.

Ele devolve uma lista organizada. Depois, nosso programa **confere se cada palavra existe mesmo no texto**. Se o LLM inventou alguma coisa (isso se chama **alucinação**), jogamos fora e anotamos que ele errou.

Fazemos isso em alguns milhares de histórias, não em todas, porque custa dinheiro. Cada resposta fica salva para não pagarmos duas vezes.

📦 **Produz:** as coisas encontradas em milhares de histórias, já com tipo. Isso vira mapas e também **material de estudo para o aluno**.

### Etapa 3: o professor ensina o aluno (destilação)

Pegamos tudo o que o LLM respondeu e usamos como exercícios resolvidos para treinar um modelo pequeno. É como um aluno que estuda pelas provas corrigidas de um professor muito bom.

No Projeto 2, o nosso modelo aprendeu com as regras do Projeto 1, que eram um professor fraco. Por isso ele achava tão pouco. Agora ele aprende com um professor forte.

📦 **Produz:** o **modelo aluno treinado**, que acha as coisas no texto sem precisar do LLM.

### Etapa 4: o aluno lê a biblioteca inteira

O aluno é rápido e de graça, então ele lê **todas** as histórias do MultiCaRe. Depois, as partes do Projeto 2 que já funcionavam bem entram em ação: elas desenham as setas entre as bolinhas e montam o mapa de cada paciente.

📦 **Produz:** um **grafo gigante**, com o mapa de cada um dos milhares de pacientes.

### Etapa 5: dar o mesmo nome para a mesma coisa (normalização)

Médicos escrevem a mesma coisa de jeitos diferentes: "infarto", "MI", "myocardial infarction", "ataque cardíaco". Para o computador, parecem quatro coisas diferentes.

Para resolver, usamos **embeddings**. Eles transformam cada palavra num ponto num mapa, onde palavras com significado parecido ficam pertinho. Assim ligamos cada termo ao "nome oficial" num dicionário médico chamado **MeSH**. Agora "MI" e "infarto" viram a mesma bolinha.

📦 **Produz:** cada bolinha ligada ao seu código oficial no MeSH. É isso que permite comparar pacientes diferentes.

### Etapa 6: dar nota para a extração

Usamos a "prova corrigida" (as 8 histórias + o MACCROBAT) para dar nota a cada versão:

| Versão | Como funciona |
|---|---|
| Projeto 1 | Regras na mão |
| Projeto 2 | Aprendizado de máquina |
| Projeto 3: professor | LLM direto |
| Projeto 3: aluno | Modelo pequeno treinado pelo LLM |

Medimos quantas coisas cada um acertou, quantas deixou passar, quantas inventou, e quanto tempo e dinheiro cada um gasta.

📦 **Produz:** a **tabela de comparação**, que responde se o aluno consegue chegar perto do professor gastando quase nada.

### Etapa 7: o ajudante de diagnóstico (a aplicação)

É a parte que uma pessoa usa de verdade. Funciona assim:

1. Você digita os sintomas e achados, por exemplo: *febre alta, sopro no coração, PCR elevada*.
2. O sistema procura no grafo gigante **os pacientes mais parecidos** com esses sintomas.
3. O LLM recebe esses pacientes e monta uma **lista de doenças possíveis**, da mais provável para a menos provável, dizendo de qual paciente veio cada ideia.

Esse jeito de consultar antes de responder se chama **RAG**. É como uma **prova com consulta**: em vez de responder só de memória (e talvez inventar), o LLM olha casos reais antes, e você consegue conferir de onde veio cada resposta.

📦 **Produz:** a **aplicação funcionando**, uma página onde se digitam sintomas e se recebem sugestões com as fontes.

### Etapa 8: dar nota para o ajudante

Para saber se o ajudante é bom, fazemos um teste:

1. Pegamos um paciente cuja doença sabemos.
2. **Escondemos a doença** e entregamos só os sintomas e achados.
3. Vemos se a doença certa aparece entre as 5 primeiras sugestões.

Há um cuidado aqui: o texto original muitas vezes **já fala o nome da doença**, e aí seria como colar na prova. O grafo resolve isso, porque basta não entregar a bolinha "doença". Esse é um ótimo argumento a favor de usar o grafo.

Comparamos várias versões do ajudante:

| Versão | O que descobrimos |
|---|---|
| Só o grafo, sem LLM | Pacientes parecidos "votam" na doença |
| Só o LLM, sem consulta | Quanto ele acerta de memória |
| LLM consultando os textos | Se a consulta ajuda |
| **LLM consultando o grafo** | **Nossa proposta** |
| Mesma coisa com o grafo do P2 × do P3 | Se um mapa melhor gera um ajudante melhor |

Outro cuidado: essas histórias são públicas, então o LLM pode já tê-las lido durante o treino dele. A linha "só o LLM" serve para medir o quanto ele está lembrando em vez de raciocinar.

📦 **Produz:** a **tabela de notas do ajudante**.
