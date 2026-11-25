"""Aluno BERT: o mesmo problema do CRF (um rótulo por palavra), resolvido por um BERT biomédico.

As frases, as palavras e os rótulos (`B-Symptom-absent`…) são os mesmos de `aluno.py`; só muda o
modelo. O BERT quebra cada palavra em sub-tokens ("hepatomegaly" -> he ##pa ##tom ##eg ##aly);
a palavra é rotulada pelo seu primeiro sub-token, e os demais ficam fora da perda (-100).
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

from project3.src.aluno.aluno import REPO, frases_do_caso, linhas_do_caso, rotular, spans


def _importar_transformers():
    """Importa o `transformers` sem esbarrar no `tokenizers.py` do P1.

    Ao ser importado, o P2 põe `project1/src/tokenizacao` no sys.path, e lá há um `tokenizers.py`
    que esconde o pacote `tokenizers` da Hugging Face. Os módulos do P1 que usam esse nome já foram
    carregados (pelo import acima) e guardaram o que precisavam; então tiramos o arquivo do P1 do
    cache de módulos e escondemos as pastas do P1 só enquanto o `transformers` é importado.
    """
    p1 = str(REPO / "project1")
    if p1 in str(getattr(sys.modules.get("tokenizers"), "__file__", "")):
        del sys.modules["tokenizers"]
    caminho = sys.path[:]
    sys.path[:] = [p for p in caminho if not p.startswith(p1)]
    try:
        import tokenizers  # noqa: F401  (o da Hugging Face fica registrado de vez)
        import torch
        import transformers
    finally:
        sys.path[:] = caminho
    return torch, transformers


torch, _tf = _importar_transformers()
AutoModelForTokenClassification, AutoTokenizer = _tf.AutoModelForTokenClassification, _tf.AutoTokenizer
get_linear_schedule_with_warmup = _tf.get_linear_schedule_with_warmup

NOME = "dmis-lab/biobert-base-cased-v1.2"  # BioBERT (PubMed), 108M parâmetros, preserva maiúsculas
VERSAO = "bert-v1"
# Fixos, como no CRF: ajustá-los na validação inflaria a curva medida nela mesma.
EPOCAS, TAXA, LOTE, MAX_PALAVRAS, SEMENTE = 8, 5e-5, 16, 120, 13
IGNORAR = -100  # rótulo que a perda ignora (sub-tokens que não são o primeiro da palavra)


class AlunoBert:
    def __init__(self, tokenizador, modelo, rotulos: list[str]):
        self.tokenizador, self.modelo, self.rotulos = tokenizador, modelo, rotulos


def dispositivo() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def janelas(frase: list[dict]) -> list[list[dict]]:
    """Frases muito longas viram pedaços de até MAX_PALAVRAS palavras (o BERT aceita 512 sub-tokens)."""
    return [frase[i:i + MAX_PALAVRAS] for i in range(0, len(frase), MAX_PALAVRAS)]


def _codificar(tokenizador, lote: list[list[dict]]):
    return tokenizador([[t["texto"] for t in palavras] for palavras in lote], is_split_into_words=True,
                       truncation=True, max_length=512, padding=True, return_tensors="pt")


def treinar(casos: list[tuple[str, str]], mencoes: dict[str, list[dict]], nome: str = NOME,
            epocas: int = EPOCAS) -> AlunoBert:
    random.seed(SEMENTE)
    torch.manual_seed(SEMENTE)
    exemplos = []
    for case_id, texto in casos:
        for frase in frases_do_caso(texto):
            rotulos = rotular(frase, mencoes.get(case_id, []))
            for i in range(0, len(frase), MAX_PALAVRAS):
                exemplos.append((frase[i:i + MAX_PALAVRAS], rotulos[i:i + MAX_PALAVRAS]))
    nomes = sorted({r for _, rs in exemplos for r in rs} | {"O"})
    indice = {r: k for k, r in enumerate(nomes)}

    tokenizador = AutoTokenizer.from_pretrained(nome, do_lower_case=False)
    modelo = AutoModelForTokenClassification.from_pretrained(
        nome, num_labels=len(nomes), id2label=dict(enumerate(nomes)), label2id=indice)
    disp = dispositivo()
    modelo.to(disp).train()
    otimizador = torch.optim.AdamW(modelo.parameters(), lr=TAXA)
    passos = epocas * ((len(exemplos) + LOTE - 1) // LOTE)
    agenda = get_linear_schedule_with_warmup(otimizador, int(0.1 * passos), passos)

    for _ in range(epocas):
        random.shuffle(exemplos)
        for k in range(0, len(exemplos), LOTE):
            lote = exemplos[k:k + LOTE]
            entrada = _codificar(tokenizador, [p for p, _ in lote])
            alvos = []
            for b, (_, rotulos) in enumerate(lote):
                anterior, linha = None, []
                for palavra in entrada.word_ids(b):
                    primeiro = palavra is not None and palavra != anterior
                    linha.append(indice[rotulos[palavra]] if primeiro else IGNORAR)
                    anterior = palavra
                alvos.append(linha)
            entrada["labels"] = torch.tensor(alvos)
            perda = modelo(**{c: v.to(disp) for c, v in entrada.items()}).loss
            perda.backward()
            torch.nn.utils.clip_grad_norm_(modelo.parameters(), 1.0)
            otimizador.step()
            agenda.step()
            otimizador.zero_grad()
    modelo.eval()
    return AlunoBert(tokenizador, modelo, nomes)


@torch.no_grad()
def prever_caso(aluno: AlunoBert, case_id: str, texto: str) -> list[dict]:
    pedacos = [j for frase in frases_do_caso(texto) for j in janelas(frase)]
    disp = next(aluno.modelo.parameters()).device
    achadas = []
    for k in range(0, len(pedacos), LOTE):
        lote = pedacos[k:k + LOTE]
        entrada = _codificar(aluno.tokenizador, lote)
        probs = aluno.modelo(**{c: v.to(disp) for c, v in entrada.items()}).logits.softmax(-1).cpu()
        for b, palavras in enumerate(lote):
            rotulos, confiancas, vistas = ["O"] * len(palavras), [1.0] * len(palavras), set()
            for posicao, palavra in enumerate(entrada.word_ids(b)):
                if palavra is None or palavra in vistas:
                    continue
                vistas.add(palavra)
                melhor = int(probs[b, posicao].argmax())
                rotulos[palavra], confiancas[palavra] = aluno.rotulos[melhor], float(probs[b, posicao, melhor])
            achadas += spans(palavras, rotulos, confiancas)
    return linhas_do_caso(case_id, texto, achadas, VERSAO)


def descrever(aluno: AlunoBert) -> dict:
    return {"versao": VERSAO, "base": NOME, "epocas": EPOCAS, "taxa": TAXA, "lote": LOTE,
            "rotulos": len(aluno.rotulos), "dispositivo": str(dispositivo())}


def salvar(aluno: AlunoBert, pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    aluno.modelo.save_pretrained(pasta)
    aluno.tokenizador.save_pretrained(pasta)


def carregar(pasta: Path) -> AlunoBert:
    if not (Path(pasta) / "config.json").is_file():
        raise FileNotFoundError(f"{pasta} não tem modelo: rode `--modelo bert treinar` antes")
    tokenizador = AutoTokenizer.from_pretrained(pasta, do_lower_case=False)
    modelo = AutoModelForTokenClassification.from_pretrained(pasta).to(dispositivo()).eval()
    rotulos = [modelo.config.id2label[k] for k in range(len(modelo.config.id2label))]
    return AlunoBert(tokenizador, modelo, rotulos)
