"""Métricas da comparação de normalização (sem modelo)."""
import unittest

from project3.src.normalizacao import comparar


class MedirTests(unittest.TestCase):
    def test_acuracia_precisao_cobertura(self):
        m = comparar.medir(["D1", "D2", "D3", "D4"], ["D1", "X", "", "D4"])
        self.assertEqual((m["acertos"], m["com_codigo_previsto"]), (2, 3))
        self.assertEqual((m["acuracia"], m["precisao"], m["cobertura"]), (0.5, 0.6667, 0.75))

    def test_vazio_no_gold_nunca_conta_acerto(self):
        self.assertEqual(comparar.medir(["", ""], ["", ""])["acertos"], 0)

    def test_grupos(self):
        mencoes = [{"mesh": "D1"}, {"mesh": "ANAT001"}, {"mesh": ""}]
        linhas = comparar.comparar(mencoes, {"s": ["D1", "", "D9"]})
        por_grupo = {l["grupo"]: l for l in linhas}
        self.assertEqual(por_grupo["com_codigo"]["acertos"], 1)
        self.assertEqual(por_grupo["com_codigo_anat"]["cobertura"], 0.0)
        self.assertEqual(por_grupo["sem_codigo"]["com_codigo_previsto"], 1)


if __name__ == "__main__":
    unittest.main()
