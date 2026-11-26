import unittest

from project3.src.diagnostico import montar_consulta
from project3.src.diagnostico.busca import Indice
from project3.src.diagnostico.dados import Caso
from project3.src.diagnostico.motor import interpretar_resposta


class DiagnosticoTests(unittest.TestCase):
    def test_artigo_excluido_nao_altera_o_peso_do_texto(self):
        consulta = [{"type": "Finding", "label": "edema", "mesh": "D1", "polarity": "present"}]
        casos = [
            Caso("A_01", "A", tuple(consulta), (), ""),
            Caso("B_01", "B", ({**consulta[0], "mesh": ""},), (), ""),
        ]
        vizinho, = Indice(casos, None, texto_integral=False).buscar(consulta, {"A"}, 5)
        self.assertEqual(vizinho.caso.case_id, "B_01")
        self.assertAlmostEqual(vizinho.score, 1.0)

    def test_consulta_preserva_negacao_e_remove_diagnostico_disfarcado(self):
        nos = [
            {"type": "Diagnosis", "label": "example", "attributes": "mesh=D1"},
            {"type": "Finding", "label": "alias", "attributes": "mesh=D1"},
            {"type": "Symptom", "label": "cough", "attributes": "polarity=absent"},
        ]
        self.assertEqual(montar_consulta(nos, []), [
            {"type": "Symptom", "label": "cough", "mesh": "", "polarity": "absent"},
        ])

    def test_rank_respeita_score_e_citacoes(self):
        resposta = """{"sugestoes":[
            {"rotulo":"x","score":0.1,"casos_fonte":["f1"]},
            {"rotulo":"y","score":0.9,"casos_fonte":["f2","inventada"]},
            {"rotulo":"z","score":1,"casos_fonte":["inventada"]}]}"""
        self.assertEqual(interpretar_resposta(resposta, {"f1", "f2"}), [
            ("y", 0.9, ("f2",)), ("x", 0.1, ("f1",)),
        ])

    def test_busca_lexical_exige_termo_do_achado(self):
        for origem, destino in [
            ("cough", "fever"), ("glucose 12.5 mg/dL", "cholesterol 12.5 mg/dL"),
            ("in the arm", "in the leg"),
        ]:
            with self.subTest(origem=origem, destino=destino):
                consulta = [{"label": origem, "polarity": "absent", "mesh": ""}]
                referencia = ({**consulta[0], "label": destino},)
                indice = Indice([Caso("A", "A", referencia, (), "")], None, texto_integral=False)
                self.assertEqual(indice.buscar(consulta, set(), 1), [])

    def test_valor_decimal_distingue_resultados_do_mesmo_exame(self):
        consulta = [{"label": "sodium 120.5 mmol/L", "polarity": "present", "mesh": ""}]
        outro = ({**consulta[0], "label": "sodium 160.5 mmol/L"},)
        indice = Indice([Caso("A", "A", outro, (), ""), Caso("B", "B", tuple(consulta), (), "")],
                        None, texto_integral=False)
        primeiro, segundo = indice.buscar(consulta, set(), 2)
        self.assertEqual(primeiro.caso.case_id, "B")
        self.assertGreater(primeiro.score, segundo.score)
