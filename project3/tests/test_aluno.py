"""Aluno: rótulos com tipo e polaridade, treino só com `treino` e saída no contrato."""
import importlib.util
import tempfile
import unittest
import warnings
from pathlib import Path

from project2.src.comum import casos_gold
from project3.src.aluno import aluno
from project3.src.professor import professor
from project3.src.professor.divisoes import ler_divisoes

TEXTOS = [
    ("PMC1_01", "The patient had fever and cough. She denied chest pain. Biopsy showed adenocarcinoma."),
    ("PMC2_01", "He reported fever and headache. No chest pain was noted. Biopsy revealed lymphoma."),
    ("PMC3_01", "Fever and cough persisted. The patient denied chest pain. Biopsy confirmed sarcoma."),
]
ROTULOS = {"fever": ("Symptom", "present"), "Fever": ("Symptom", "present"), "cough": ("Symptom", "present"),
           "headache": ("Symptom", "present"), "chest pain": ("Symptom", "absent"), "Biopsy": ("Exam", "present"),
           "adenocarcinoma": ("Diagnosis", "present"), "lymphoma": ("Diagnosis", "present"),
           "sarcoma": ("Diagnosis", "present")}


def mencoes_do_professor():
    por_caso = {}
    for case_id, texto in TEXTOS:
        por_caso[case_id] = [{"case_id": case_id, "start": texto.index(t), "end": texto.index(t) + len(t),
                              "texto": t, "tipo": tipo, "polaridade": pol}
                             for t, (tipo, pol) in ROTULOS.items() if t in texto]
    return por_caso


class TestRotulos(unittest.TestCase):
    def test_ida_e_volta_preserva_tipo_e_polaridade(self):
        case_id, texto = TEXTOS[0]
        mencoes = mencoes_do_professor()[case_id]
        for frase in aluno.frases_do_caso(texto):
            rotulos = aluno.rotular(frase, mencoes)
            esperadas = {(m["start"], m["end"], m["tipo"], m["polaridade"]) for m in mencoes
                         if frase[0]["start"] <= m["start"] < frase[-1]["end"]}
            obtidas = {(s["start"], s["end"], s["tipo"], s["polaridade"]) for s in aluno.spans(frase, rotulos)}
            self.assertEqual(obtidas, esperadas)
        self.assertIn("B-Symptom-absent", aluno.rotular(aluno.frases_do_caso(texto)[1], mencoes))

    def test_i_de_outro_tipo_abre_mencao_nova(self):
        frase = [{"start": 0, "end": 3}, {"start": 4, "end": 7}]
        achadas = aluno.spans(frase, ["B-Symptom-present", "I-Exam-present"])
        self.assertEqual([(s["start"], s["tipo"]) for s in achadas], [(0, "Symptom"), (4, "Exam")])


class TestTreino(unittest.TestCase):
    def test_treino_nunca_usa_teste_e_fracoes_sao_aninhadas(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            particoes = ler_divisoes(Path("/nao/existe.csv"))
        mencoes = {c: [] for c in particoes}
        anteriores = set()
        for fracao in aluno.FRACOES:
            ids = set(aluno.casos_de_treino(particoes, mencoes, fracao))
            self.assertFalse(ids & casos_gold())
            self.assertTrue(all(particoes[c] == "treino" for c in ids))
            self.assertLessEqual(anteriores, ids)
            anteriores = ids

    def test_predicao_passa_no_contrato_da_montagem(self):
        crf = aluno.treinar(TEXTOS, mencoes_do_professor())
        case_id, texto = "PMC9_01", "The patient had fever and cough. Biopsy showed lymphoma."
        linhas = aluno.prever_caso(crf, case_id, texto)
        professor.validar_contrato(case_id, texto, linhas)
        self.assertTrue(linhas)
        self.assertEqual(list(linhas[0]), professor.COLUNAS)
        self.assertTrue(all(0 <= l["confianca"] <= 1 and l["fonte"].startswith("aluno:") for l in linhas))
        self.assertIn(("fever", "Symptom"), {(l["texto"], l["tipo"]) for l in linhas})


def bert_minusculo(pasta: Path) -> Path:
    """BERT aleatório de 1 camada com vocabulário das palavras do teste: sem download, sem rede."""
    from transformers import BertConfig, BertModel, BertTokenizerFast

    palavras = {t["texto"] for _, texto in TEXTOS for f in aluno.frases_do_caso(texto) for t in f}
    pasta.mkdir(parents=True, exist_ok=True)
    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", *sorted(palavras)]
    (pasta / "vocab.txt").write_text("\n".join(vocab) + "\n", encoding="utf-8")
    BertTokenizerFast(vocab_file=str(pasta / "vocab.txt"), do_lower_case=False).save_pretrained(pasta)
    BertModel(BertConfig(vocab_size=len(vocab), hidden_size=32, num_hidden_layers=1, num_attention_heads=2,
                         intermediate_size=64)).save_pretrained(pasta)
    return pasta


@unittest.skipUnless(importlib.util.find_spec("torch") and importlib.util.find_spec("transformers"),
                     "torch/transformers não instalados")
class TestBert(unittest.TestCase):
    def test_treina_salva_carrega_e_preve_no_contrato(self):
        from project3.src.aluno import bert

        pasta = Path(tempfile.mkdtemp())
        modelo = bert.treinar(TEXTOS, mencoes_do_professor(), nome=str(bert_minusculo(pasta / "base")), epocas=2)
        bert.salvar(modelo, pasta / "treinado")
        modelo = bert.carregar(pasta / "treinado")
        case_id, texto = TEXTOS[1]
        linhas = bert.prever_caso(modelo, case_id, texto)
        professor.validar_contrato(case_id, texto, linhas)
        self.assertTrue(all(l["fonte"] == "aluno:bert-v1" and 0 <= l["confianca"] <= 1 for l in linhas))
        self.assertIn("B-Symptom-absent", modelo.rotulos)

    def test_janelas_cortam_frases_longas(self):
        from project3.src.aluno import bert

        frase = [{"texto": "x", "start": i, "end": i + 1} for i in range(250)]
        self.assertEqual([len(j) for j in bert.janelas(frase)], [120, 120, 10])


if __name__ == "__main__":
    unittest.main()
