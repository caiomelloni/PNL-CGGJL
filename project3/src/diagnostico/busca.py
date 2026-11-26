"""Índice de casos por MeSH e representação textual."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from .dados import Caso


PALAVRAS_COMUNS = frozenset(
    "a an and are as at be been by did for from had has have in into is it no not of on or "
    "that the their there to was were with without".split()
)
UNIDADES = frozenset("mg g kg ng pg mcg µg μg ug dl ml l u iu mmol mol meq mm cm mmhg bpm %".split())
TOKEN = re.compile(r"[0-9]+(?:[.,][0-9]+)?|[^\W\d_]+|%")


def termos(texto: str) -> list[str]:
    return [t for t in TOKEN.findall(texto.casefold())
            if t not in PALAVRAS_COMUNS and t not in UNIDADES and not t[0].isdigit()]


def termos_dos_achados(consulta) -> list[str]:
    resultado = []
    for achado in consulta:
        nome = achado["label"].casefold()
        conceitos = termos(nome)
        medidas = [t.replace(",", ".") for t in TOKEN.findall(nome)
                   if t[0].isdigit() or t in UNIDADES]
        for conceito in conceitos:
            chave = f"{achado['polarity']}:{conceito}"
            resultado.append(chave)
            if medidas:
                resultado.append(f"{chave}:{' '.join(medidas)}")
    return resultado


def texto_da_consulta(consulta: list[dict] | tuple[dict, ...]) -> str:
    return "; ".join(
        f"no {item['label']}" if item["polarity"] == "absent" else item["label"]
        for item in consulta
    )


def codigos_mesh(consulta: list[dict] | tuple[dict, ...]) -> list[str]:
    return [f"{item['polarity']}:{item['mesh']}" for item in consulta if item["mesh"]]


class VetoresTfidf:
    def __init__(self, documentos: list[list[str]]):
        frequencias = Counter(termo for doc in documentos for termo in set(doc))
        self.idf = {
            termo: 1 + math.log((1 + len(documentos)) / (1 + freq))
            for termo, freq in frequencias.items()
        }
        self.postagens = defaultdict(list)
        for i, doc in enumerate(documentos):
            for termo, valor in self.vetor(doc).items():
                self.postagens[termo].append((i, valor))

    def vetor(self, termos_doc: list[str]) -> dict[str, float]:
        pesos = {
            termo: (1 + math.log(freq)) * self.idf[termo]
            for termo, freq in Counter(termos_doc).items() if termo in self.idf
        }
        norma = math.sqrt(sum(peso**2 for peso in pesos.values()))
        return {termo: peso / norma for termo, peso in pesos.items()}

    def similaridades(self, consulta: list[str]) -> dict[int, float]:
        pontos = defaultdict(float)
        for termo, valor in self.vetor(consulta).items():
            for i, peso in self.postagens[termo]:
                pontos[i] += valor * peso
        return pontos


class Embeddings:
    """Carrega um SentenceTransformer por motor e codifica textos em blocos."""
    def __init__(self, nome: str):
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer
        except ImportError as erro:
            raise RuntimeError("Instale project3/src/diagnostico/requirements.txt para usar embeddings.") from erro
        self.np = np
        self.modelo = SentenceTransformer(nome)

    def codificar(self, textos: list[str]):
        blocos, limites = [], [0]
        for texto in textos:
            palavras = texto.split()
            blocos.extend(" ".join(palavras[i:i + 120]) for i in range(0, len(palavras), 120))
            limites.append(len(blocos))
        if not blocos:
            return self.np.zeros((len(textos), self.modelo.get_sentence_embedding_dimension()), dtype="float32")
        vetores = self.modelo.encode(blocos, normalize_embeddings=True, show_progress_bar=False)
        matriz = self.np.zeros((len(textos), vetores.shape[1]), dtype="float32")
        for i, (inicio, fim) in enumerate(zip(limites, limites[1:])):
            if inicio != fim:
                media = vetores[inicio:fim].mean(axis=0)
                norma = self.np.linalg.norm(media)
                if norma:
                    matriz[i] = media / norma
        return matriz


class VetoresTextuais:
    def __init__(self, textos: list[str], embeddings: Embeddings | None):
        self.embeddings = embeddings
        if embeddings is None:
            self.tfidf = VetoresTfidf([termos(texto) for texto in textos])
        else:
            # Limita a memória temporária usada para gerar blocos de relatos longos.
            self.matriz = embeddings.np.empty(
                (len(textos), embeddings.modelo.get_sentence_embedding_dimension()), dtype="float32",
            )
            for inicio in range(0, len(textos), 256):
                lote = textos[inicio:inicio + 256]
                self.matriz[inicio:inicio + len(lote)] = embeddings.codificar(lote)

    def similaridades(self, texto: str) -> dict[int, float]:
        if self.embeddings is None:
            return self.tfidf.similaridades(termos(texto))
        vetor = self.embeddings.codificar([texto])[0]
        return {i: float(ponto) for i, ponto in enumerate(self.matriz @ vetor) if ponto > 0}


@dataclass(frozen=True)
class Vizinho:
    caso: Caso
    score: float
    score_mesh: float
    score_texto: float


class Indice:
    def __init__(self, casos: list[Caso], embeddings: Embeddings | None, *, texto_integral: bool):
        self.casos = casos
        self.texto_integral = texto_integral
        if texto_integral:
            textos = [caso.texto for caso in casos]
            if not any(texto.strip() for texto in textos):
                raise RuntimeError("rag_texto precisa dos relatos do corpus correspondentes ao índice.")
        else:
            textos = [texto_da_consulta(caso.consulta) for caso in casos]
        self.mesh = None if texto_integral else VetoresTfidf([codigos_mesh(caso.consulta) for caso in casos])
        self.achados = None
        self.texto = None
        if embeddings is None and not texto_integral:
            self.achados = VetoresTfidf([termos_dos_achados(caso.consulta) for caso in casos])
        else:
            self.texto = VetoresTextuais(textos, embeddings)

    def buscar(
        self, consulta: list[dict], excluir_artigos: set[str], limite: int,
    ) -> list[Vizinho]:
        por_mesh = {} if self.mesh is None else self.mesh.similaridades(codigos_mesh(consulta))
        if self.achados is None:
            por_palavras = self.texto.similaridades(texto_da_consulta(consulta))
        else:
            por_palavras = self.achados.similaridades(termos_dos_achados(consulta))
        usar_mesh = any(self.casos[i].article_id not in excluir_artigos for i in por_mesh)
        vizinhos = []
        for i in por_mesh.keys() | por_palavras.keys():
            caso = self.casos[i]
            if caso.article_id in excluir_artigos or (self.texto_integral and not caso.texto.strip()):
                continue
            mesh, textual = por_mesh.get(i, 0.0), por_palavras.get(i, 0.0)
            score = 0.65 * mesh + 0.35 * textual if usar_mesh else textual
            vizinhos.append(Vizinho(caso, min(1.0, score), min(1.0, mesh), min(1.0, textual)))
        return sorted(vizinhos, key=lambda v: (-v.score, v.caso.case_id))[:limite]
