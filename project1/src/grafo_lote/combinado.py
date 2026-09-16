from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import re
import sys
from collections import defaultdict
from pathlib import Path

import nltk
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
# normalizacao e stopwords são pacotes (importados a partir de src/); tokenizacao,
# sintagmas e dicionarios são pastas planas, das quais só importamos módulos com
# nome único (tokenizers, pos_bio, mesh_parser, normalization, matching).
for pasta in (SRC, SRC / "tokenizacao", SRC / "sintagmas", SRC / "dicionarios"):
    if str(pasta) not in sys.path:
        sys.path.append(str(pasta))

from normalizacao.case_reader import ClinicalCase
from normalizacao.core import models as nmodels
from normalizacao.core.graph import GraphBuilder
from normalizacao.extractors.common import ExtractedEntity
from normalizacao.extractors.diagnoses import extract_diagnoses
from normalizacao.extractors.exams import ExtractedExamResult, extract_exam_results, extract_exams
from normalizacao.extractors.findings import ExtractedFinding, extract_findings
from normalizacao.extractors.history import extract_history
from normalizacao.extractors.outcomes import extract_outcomes
from normalizacao.extractors.patient import extract_patient
from normalizacao.extractors.relations import ExtractedCaseEntities, _add_unique_edge, build_relations
from normalizacao.extractors.symptoms import extract_symptoms
from normalizacao.extractors.treatments import extract_medications, extract_treatments
from stopwords.extractors.common import detect_polarity, split_sentences
from stopwords.lexicon.label_cleaning import clean_label
from stopwords.lexicon.loader import load_list

import pos_bio
from matching import greedy_match, link_label_to_concept, match_text
from mesh_parser import load_gazetteer_rows, rows_to_raw_gazetteer
from normalization import build_normalized_gazetteer, normalize_token
from tokenizers import ClinicalRegexTokenizer


class GrafoRascunho(GraphBuilder):
    """GraphBuilder que lembra os rótulos brutos recebidos por cada nó."""

    def __init__(self, case_id, case_text):
        super().__init__(case_id, case_text)
        self.rotulos_brutos = defaultdict(list)

    def add_node(self, node_type, raw_label, attributes=None, *, deduplicate=True):
        node = super().add_node(node_type, raw_label, attributes, deduplicate=deduplicate)
        self.rotulos_brutos[node.node_id].append(raw_label)
        return node



def rotulo_final(node):
    if node.type == "ExamResult" and node.attributes.get("unit"):
        return f"{format(node.attributes['value'], 'f')} {node.attributes['unit']}"
    return node.label


DOMINIO = {
    "HAS_SYMPTOM": ({"Patient"}, {"Symptom"}),
    "HAS_HISTORY": ({"Patient"}, {"History"}),
    "UNDERWENT_EXAM": ({"Patient"}, {"Exam"}),
    "HAS_RESULT": ({"Exam"}, {"ExamResult"}),
    "REVEALS": ({"Exam", "Treatment"}, {"Finding"}),
    "HAS_FINDING": ({"Patient"}, {"Finding"}),
    "SUPPORTS": ({"Symptom", "Finding", "ExamResult", "History"}, {"Diagnosis"}),
    "DIAGNOSED_WITH": ({"Patient"}, {"Diagnosis"}),
    "TREATED_WITH": ({"Patient", "Diagnosis"}, {"Treatment", "Medication"}),
    "LOCATED_IN": ({"Symptom", "Finding", "Treatment"}, {"AnatomicalSite"}),
    "HAS_OUTCOME": ({"Patient"}, {"Outcome"}),
    "REVISES": ({"Diagnosis"}, {"Diagnosis"}),
    "SAME_AS": ({"Symptom", "Finding", "Exam", "Diagnosis", "Medication", "Treatment", "AnatomicalSite"}, {"Concept"}),
}


NODE_COLUMNS = ["case_id", "node_id", "type", "label", "attributes"]
EDGE_COLUMNS = ["case_id", "edge_id", "source_id", "target_id", "relation", "attributes"]


@dataclass(frozen=True)
class Recursos:
    tagger: Any
    gaz_anatomia: dict
    gaz_mesh: dict
    stopwords: frozenset[str]
    protegidas: frozenset[str]


@dataclass(frozen=True)
class Validacao:
    evidencias_desalinhadas: tuple[str, ...]
    arestas_fora_do_dominio: tuple[str, ...]


@dataclass
class ResultadoCaso:
    nos: pd.DataFrame
    arestas: pd.DataFrame
    grafo: GraphBuilder
    inspecao: dict[str, Any] | None = None


def carregar_recursos() -> Recursos:
    """Carrega recursos uma vez; dados do NLTK devem estar instalados previamente."""
    nltk.data.find("tokenizers/punkt_tab/english/")
    if not Path(pos_bio.MODEL_PATH).is_file():
        raise FileNotFoundError(f"Modelo HMM ausente: {pos_bio.MODEL_PATH}")
    pasta = SRC / "dicionarios" / "gazetteer"
    anatomia = build_normalized_gazetteer(rows_to_raw_gazetteer(
        load_gazetteer_rows(pasta / "anatomical_site_gazetteer.csv"), "anatomical_site"
    ))
    linhas = load_gazetteer_rows(pasta / "mesh_gazetteer.csv")
    mesh = {
        categoria: build_normalized_gazetteer(rows_to_raw_gazetteer(linhas, categoria))
        for categoria in ("diseases", "mental_disorders", "drugs", "exams", "treatments")
    }
    return Recursos(pos_bio.HMMTagger(), anatomia, mesh,
                    load_list("nltk_stopwords"), load_list("protection_list"))


def validar_grafo(caso: ClinicalCase, resultado: ResultadoCaso) -> Validacao:
    """Conta inconsistências sem interromper o caso nem alterar suas tabelas."""
    tipos = {n.node_id: n.type for n in resultado.grafo.nodes}
    desalinhadas, fora = [], []
    for aresta in resultado.grafo.edges:
        dominio = DOMINIO.get(aresta.relation)
        if (dominio is None or tipos.get(aresta.source_id) not in dominio[0]
                or tipos.get(aresta.target_id) not in dominio[1]):
            fora.append(aresta.edge_id)
        attrs = aresta.attributes
        if any(k in attrs for k in ("char_start", "char_end", "evidence_text")):
            inicio, fim = attrs.get("char_start"), attrs.get("char_end")
            if (not isinstance(inicio, int) or not isinstance(fim, int)
                    or not 0 <= inicio <= fim <= len(caso.case_text)
                    or caso.case_text[inicio:fim] != attrs.get("evidence_text")):
                desalinhadas.append(aresta.edge_id)
    return Validacao(tuple(desalinhadas), tuple(fora))


def processar_caso(caso: ClinicalCase, recursos: Recursos, *,
                   inspecionar: bool = False) -> ResultadoCaso:
    """Executa as regras do notebook na mesma ordem, preservando IDs e offsets."""
    # SAME_AS consta do contrato comum, mas não do parser original de normalização.
    nmodels.ALLOWED_RELATIONS.add("SAME_AS")
    texto = caso.case_text
    if not texto.strip():
        raise ValueError("case_text vazio")
    tagger = recursos.tagger
    gaz_anatomia, gaz_mesh = recursos.gaz_anatomia, recursos.gaz_mesh
    STOP_NLTK, PROTEGIDAS = recursos.stopwords, recursos.protegidas

    def curto(texto, n=90):
        texto = " ".join(str(texto).split())
        return texto if len(texto) <= n else texto[:n - 1] + "…"

    sentencas = [s for s in split_sentences(texto) if s.text.strip()]


    def sentenca_de(posicao):
        return max((s for s in sentencas if s.start <= posicao), key=lambda s: s.start, default=sentencas[0])



    tokens = ClinicalRegexTokenizer().tokenize(texto)

    ptokens = []
    for t in tokens:
        pt = pos_bio.Token(t.text, t.start, t.end, t.index)
        if t.kind == "UNIT":
            pt.role = "UNIT"
        ptokens.append(pt)

    restricoes = pos_bio.build_constraints(ptokens, tagger, pos_bio.HEAD_NOUNS)
    for i, t in enumerate(tokens):
        if t.kind == "FIGURE_REF":
            restricoes[i] = {"."}
    tagger.tag(ptokens, restricoes)
    reparos = pos_bio.repair_tags(ptokens)
    chunks = pos_bio.chunk_nps(ptokens)
    tipo_lexico = {(sp.i0, sp.i1): sp.type for sp in pos_bio.find_spans(chunks) if sp.layer == 0}
    np_por_token = {t.index: ch for ch in chunks for t in ch}


    rascunho = GrafoRascunho(caso.case_id, texto)
    brutas = ExtractedCaseEntities(
        patient=extract_patient(caso, rascunho),
        symptoms=tuple(extract_symptoms(texto, rascunho)),
        histories=tuple(extract_history(texto, rascunho)),
        exams=tuple(extract_exams(texto, rascunho)),
        exam_results=tuple(extract_exam_results(texto, rascunho)),
        findings=tuple(extract_findings(texto, rascunho)),
        diagnoses=tuple(extract_diagnoses(texto, rascunho)),
        medications=tuple(extract_medications(texto, rascunho)),
        treatments=tuple(extract_treatments(texto, rascunho)),
        outcomes=tuple(extract_outcomes(texto, rascunho)),
    )

    CAMPOS = ("symptoms", "histories", "exams", "findings", "diagnoses", "medications", "treatments", "outcomes")


    def entidade(item):
        return item.entity if isinstance(item, ExtractedFinding) else item


    LIVRES = {"Symptom", "History", "Diagnosis", "Finding"}
    COM_POLARIDADE = {"Symptom", "Finding", "History", "Outcome"}
    figuras = [t for t in tokens if t.kind == "FIGURE_REF"]
    CORTE_ORACAO = re.compile(r"[,;]|\bbut\b", re.I)


    def localizar(inicio, fim, candidatos, nucleo=False):
        """Span da menção dentro da evidência [inicio, fim).

        Procura cada candidato literalmente; com `nucleo`, recorre à última palavra do rótulo
        (`and bleeding` não aparece contíguo em "no evidence of bleeding").
        """
        trecho = texto[inicio:fim].lower()
        for candidato in candidatos:
            alvo = candidato.strip().lower()
            if alvo and (i := trecho.find(alvo)) >= 0:
                return inicio + i, inicio + i + len(alvo)
        if nucleo:
            for candidato in candidatos:
                palavras = re.findall(r"[A-Za-z][\w-]*", candidato)
                if palavras and (m := re.search(rf"\b{re.escape(palavras[-1])}\b", texto[inicio:fim], re.I)):
                    return inicio + m.start(), inicio + m.end()
        return None


    def aparar(inicio, fim):
        trecho = texto[inicio:fim]
        esquerda = len(trecho) - len(trecho.lstrip(" \t\n,;:("))
        direita = len(trecho.rstrip(" \t\n,;:("))
        return inicio + esquerda, inicio + direita


    def ptokens_em(inicio, fim):
        return [t for t in ptokens if inicio <= t.start and t.end <= fim and t.text[:1].isalnum()]


    def miolo_do_np(chunk):
        miolo = [t for t in chunk if t.tag not in ("DET", "NUM") and t.role != "UNIT"]
        return (miolo[0].start, miolo[-1].end) if miolo else None


    def medidas(inicio, fim):
        """Dimensões `N UNIT (x N UNIT)*` formadas por tokens dentro de [inicio, fim)."""
        seq = [t for t in tokens if inicio <= t.start and t.end <= fim]
        achadas, i = [], 0
        while i < len(seq) - 1:
            if seq[i].kind == "NUMBER" and seq[i + 1].kind == "UNIT":
                valores, unidade, j = [seq[i].text], seq[i + 1].text, i + 2
                while j + 2 < len(seq) and seq[j].text.lower() == "x" and seq[j + 1].kind == "NUMBER" and seq[j + 2].kind == "UNIT":
                    valores.append(seq[j + 1].text)
                    unidade = seq[j + 2].text
                    j += 3
                achadas.append((seq[i].start, seq[j - 1].end, " x ".join(valores) + " " + unidade.lower()))
                i = j
            else:
                i += 1
        return achadas


    def juntar(toks):
        """Texto dos tokens, preservando o espaçamento original entre vizinhos."""
        partes = [toks[0].text]
        for anterior, atual in zip(toks, toks[1:]):
            partes.append(texto[anterior.end:atual.start] if atual.index == anterior.index + 1 else " ")
            partes.append(atual.text)
        return "".join(partes)


    def nome_do_analito(toks):
        """Nome do exame dentro dos tokens: sem parentéticos, cortado em `)`/`,` soltos e em `(` sem fechamento."""
        segmentos, atual, abertos = [], [], []
        for t in toks:
            if t.text == "(":
                abertos.append(len(atual))
                atual.append(t)
            elif t.text == ")" and abertos:
                del atual[abertos.pop():]
            elif t.text in {")", ","}:
                segmentos.append(atual)
                atual, abertos = [], []
            else:
                atual.append(t)
        if abertos:
            atual = atual[:abertos[0]]
        segmentos.append(atual)
        conteudo = [s for s in segmentos if any(t.kind == "WORD" and t.text.lower() not in STOP_NLTK for t in s)]
        return conteudo[-1] if conteudo else []


    def janela_da_oracao(span):
        sentenca = sentenca_de(span[0])
        cortes = list(CORTE_ORACAO.finditer(texto, sentenca.start, span[0]))
        inicio = cortes[-1].end() if cortes else sentenca.start
        return texto[inicio:span[1]]


    def refinar(node, inicio, fim, trigger):
        tipo, attrs, notas = node.type, dict(node.attributes), []
        rotulo = node.label
        brutos = rascunho.rotulos_brutos[node.node_id]
        if tipo == "Medication":
            candidatos = (trigger,)
        elif tipo in LIVRES:
            candidatos = (*brutos, node.label)
        else:
            candidatos = (*brutos, node.label, trigger)
        span = localizar(inicio, fim, candidatos, nucleo=tipo in LIVRES)

        if tipo == "Medication" and span is not None:
            pos_unidade = span[1] - len(str(attrs["dose_unit"]))
            token_unidade = next((t for t in tokens if t.start <= pos_unidade < t.end), None)
            if token_unidade is not None and token_unidade.text.lower() != str(attrs["dose_unit"]).lower():
                notas.append(("tokenizacao", f"descartada: '{attrs['dose_unit']}' faz parte do token de unidade '{token_unidade.text}'"))
                return {"tipo": tipo, "rotulo": rotulo, "attrs": attrs, "span": span, "notas": notas, "descartar": True}

        if tipo == "Exam" and attrs.get("modality") == "laboratory" and span is not None:
            mantidos = nome_do_analito([t for t in tokens if span[0] <= t.start and t.end <= span[1]])
            if mantidos and juntar(mantidos) != texto[span[0]:span[1]]:
                notas.append(("tokenizacao", f"corta na pontuação: '{texto[span[0]:span[1]]}'"))
                span = (mantidos[0].start, mantidos[-1].end)
                rotulo = juntar(mantidos)

        if tipo in LIVRES and span is not None:
            for figura in figuras:
                if span[0] < figura.start < span[1]:
                    span = aparar(span[0], figura.start)
                    notas.append(("tokenizacao", f"remove {figura.text!r}"))

            palavras = ptokens_em(*span)
            chunk = None
            if tipo == "Finding" and palavras:
                chunk = np_por_token.get(palavras[-1].index)
            elif palavras and palavras[0].index not in np_por_token:
                chunk = next((np_por_token[t.index] for t in palavras if t.index in np_por_token), None)
            novo = miolo_do_np(chunk) if chunk else None
            if novo and novo != span and (tipo != "Finding" or novo[0] <= palavras[-1].start < novo[1]):
                span = novo
                notas.append(("sintagmas", f"sintagma '{pos_bio.surface(chunk)}'"))

            if tipo == "Finding":
                sentenca = sentenca_de(span[0])
                inicio_np = chunk[0].start if chunk else span[0]
                tamanho = next(
                    (
                        m[2]
                        for m in reversed(medidas(sentenca.start, sentenca.end))
                        if inicio_np < m[1] <= span[1] or re.fullmatch(r"\s*measuring\s*", texto[span[1]:m[0]], re.I)
                    ),
                    None,
                )
                if tamanho != attrs.get("size"):
                    notas.append(("tokenizacao", f"size {attrs.get('size')!r} → {tamanho!r}"))
                    attrs["size"] = tamanho

            rotulo = texto[span[0]:span[1]]

        if tipo in COM_POLARIDADE and span is not None and attrs.get("polarity") == "present":
            if detect_polarity(janela_da_oracao(span)) == "absent":
                attrs["polarity"] = "absent"
                notas.append(("stopwords", f"negação em '{curto(janela_da_oracao(span), 60)}'"))

        limpo = clean_label(rotulo, STOP_NLTK, PROTEGIDAS)
        if limpo != rotulo:
            notas.append(("stopwords", f"clean_label '{rotulo}' → '{limpo}'"))
            rotulo = limpo

        return {"tipo": tipo, "rotulo": rotulo, "attrs": attrs, "span": span, "notas": notas, "descartar": False}


    registros = []
    for campo in CAMPOS:
        for item in getattr(brutas, campo):
            ent = entidade(item)
            registros.append({"campo": campo, "bruta": ent, **refinar(ent.node, ent.char_start, ent.char_end, ent.trigger)})
    exames_de_resultado = []
    for r in brutas.exam_results:
        exames_de_resultado.append((r, refinar(r.exam_node, r.char_start, r.char_end, "")))

    def ancorar(inicio, fim):
        inicio, fim = aparar(inicio, fim)
        return texto[inicio:fim], inicio, fim


    final = GraphBuilder(caso.case_id, texto)
    paciente = extract_patient(caso, final)
    por_campo = defaultdict(list)
    for reg in registros:
        if reg["descartar"]:
            continue
        bruta = reg["bruta"]
        # Achados com tamanhos diferentes são observações distintas (ex.: cisto de 6 x 9 cm na EUS e de 9.5 x 4.5 x 2.0 cm na patologia).
        rotulo_normalizado = final.normalizer.normalize_entity_label(reg["rotulo"])
        tamanho = reg["attrs"].get("size")
        conflito_de_tamanho = tamanho is not None and any(
            n.type == reg["tipo"] and n.label == rotulo_normalizado and n.attributes.get("size") not in (None, tamanho)
            for n in final.nodes
        )
        node = final.add_node(reg["tipo"], reg["rotulo"], reg["attrs"], deduplicate=not conflito_de_tamanho)
        evidencia, inicio, fim = ancorar(bruta.char_start, bruta.char_end)
        reg["final"] = ExtractedEntity(node, evidencia, bruta.trigger, inicio, fim)
        por_campo[reg["campo"]].append(reg["final"])

    resultados = []
    for r, ref in exames_de_resultado:
        exame = final.add_node("Exam", ref["rotulo"], ref["attrs"])
        resultado = final.add_node("ExamResult", rascunho.rotulos_brutos[r.node.node_id][0], dict(r.node.attributes), deduplicate=False)
        evidencia, inicio, fim = ancorar(r.char_start, r.char_end)
        resultados.append(ExtractedExamResult(resultado, exame, evidencia, inicio, fim))

    entidades = ExtractedCaseEntities(
        patient=paciente,
        symptoms=tuple(por_campo["symptoms"]),
        histories=tuple(por_campo["histories"]),
        exams=tuple(por_campo["exams"]),
        exam_results=tuple(resultados),
        findings=tuple(ExtractedFinding(ent, ()) for ent in por_campo["findings"]),
        diagnoses=tuple(por_campo["diagnoses"]),
        medications=tuple(por_campo["medications"]),
        treatments=tuple(por_campo["treatments"]),
        outcomes=tuple(por_campo["outcomes"]),
    )
    build_relations(final, entidades)

    EMBUTE_ORGAO = {"Diagnosis", "Finding"}
    ANCORAS = {"Symptom", "Finding", "Treatment"}
    LATERALIDADE = re.compile(r"\b(left|right|bilateral)\b", re.I)
    REGIAO = re.compile(r"\b(upper|lower|proximal|distal|anterior|posterior|body/tail|tail)\b", re.I)

    ocupados = [reg["span"] for reg in registros if not reg["descartar"] and reg["tipo"] in EMBUTE_ORGAO and reg["span"]]
    ancoras = [reg for reg in registros if not reg["descartar"] and reg["tipo"] in ANCORAS and reg["span"]]

    linhas = []
    for m in match_text([t.text for t in tokens], gaz_anatomia):
        inicio, fim = tokens[m.start].start, tokens[m.end - 1].end
        superficie = texto[inicio:fim]
        if any(s[0] <= inicio and fim <= s[1] for s in ocupados):
            linhas.append({"sítio": superficie, "código": m.code, "estratégia": m.strategy, "resultado": "descartado: dentro de diagnóstico/achado"})
            continue
        sentenca = sentenca_de(inicio)
        candidatas = [reg for reg in ancoras if sentenca.start <= reg["span"][0] < sentenca.end]
        if not candidatas:
            linhas.append({"sítio": superficie, "código": m.code, "estratégia": m.strategy, "resultado": "descartado: sem âncora na sentença"})
            continue
        ancora = min(candidatas, key=lambda reg: min(abs(reg["span"][0] - fim), abs(inicio - reg["span"][1])))
        vizinhanca = texto[max(sentenca.start, inicio - 30):fim + 30]
        lateral, regiao = LATERALIDADE.search(vizinhanca), REGIAO.search(vizinhanca)
        sitio = final.add_node(
            "AnatomicalSite",
            m.preferred_term,
            {"laterality": lateral.group(1).lower() if lateral else None, "region_qualifier": regiao.group(1).lower() if regiao else None},
        )
        evidencia, s_ini, s_fim = ancorar(sentenca.start, sentenca.end)
        _add_unique_edge(final, ancora["final"].node, sitio, "LOCATED_IN",
                         {"evidence_text": evidencia, "trigger": superficie, "certainty": "asserted", "char_start": s_ini, "char_end": s_fim})
        conceito = final.add_node("Concept", m.preferred_term, {"vocabulary": "local", "code": m.code, "preferred_term": m.preferred_term})
        _add_unique_edge(final, sitio, conceito, "SAME_AS", {"strategy": m.strategy, "score": m.score})
        linhas.append({"sítio": superficie, "código": m.code, "estratégia": m.strategy,
                       "resultado": f"{sitio.node_id} ← LOCATED_IN ← {ancora['final'].node.node_id} ({ancora['final'].node.label})"})

    sitios = linhas

    ROTA_MESH = {
        "Symptom": ("diseases",),
        "Finding": ("diseases",),
        "Diagnosis": ("diseases", "mental_disorders"),
        "Exam": ("exams",),
        "Treatment": ("treatments",),
        "Medication": ("drugs",),
    }


    def ligar(rotulo, gazetteer):
        toks = nltk.word_tokenize(rotulo)
        validos = [i for i, tok in enumerate(toks) if normalize_token(tok)]
        if not validos:
            return None
        casamentos, _ = greedy_match(toks, gazetteer)
        if casamentos:
            no_nucleo = [m for m in casamentos if m.end == validos[-1] + 1]
            return max(no_nucleo, key=lambda m: m.end - m.start) if no_nucleo else None
        return link_label_to_concept(rotulo, gazetteer)


    linhas = []
    for node in [n for n in final.nodes if n.type in ROTA_MESH]:
        for categoria in ROTA_MESH[node.type]:
            m = ligar(node.label, gaz_mesh[categoria])
            if m is None:
                continue
            conceito = final.add_node("Concept", m.preferred_term, {"vocabulary": "MeSH", "code": m.code, "preferred_term": m.preferred_term})
            _add_unique_edge(final, node, conceito, "SAME_AS", {"strategy": m.strategy, "score": m.score})
            linhas.append({"node_id": node.node_id, "type": node.type, "label": node.label, "categoria": categoria,
                           "code": m.code, "preferred_term": m.preferred_term, "estratégia": m.strategy,
                           "score": None if m.score is None else round(m.score, 1)})
            break
        else:
            linhas.append({"node_id": node.node_id, "type": node.type, "label": node.label, "categoria": "—",
                           "code": "", "preferred_term": "", "estratégia": "sem casamento", "score": None})

    mesh = linhas

    nos = pd.DataFrame([{**n.to_row(), "label": rotulo_final(n)} for n in final.nodes], columns=NODE_COLUMNS)
    arestas = pd.DataFrame(final.edge_rows(), columns=EDGE_COLUMNS)
    inspecao = None
    if inspecionar:
        inspecao = dict(sentencas=sentencas, tokens=tokens, ptokens=ptokens,
                        chunks=chunks, tipo_lexico=tipo_lexico, reparos=reparos,
                        brutas=brutas, registros=registros,
                        exames_de_resultado=exames_de_resultado, sitios=sitios, mesh=mesh)
    return ResultadoCaso(nos, arestas, final, inspecao)
