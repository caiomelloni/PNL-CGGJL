"""Índice MeSH: leitura dos gazetteers e busca do vizinho mais próximo (sem rede e sem modelo)."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from project3.src.normalizacao import normalizacao as norm


def indice_falso(pasta: Path, termos: list[tuple[str, str, str]], vetores: list[list[float]]) -> Path:
    """Escreve um índice pequeno com vetores escolhidos à mão."""
    v = np.array(vetores, dtype=np.float32)
    np.save(pasta / "vetores.npy", (v / np.linalg.norm(v, axis=1, keepdims=True)).astype(np.float16))
    with (pasta / "termos.csv").open("w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(norm.COLUNAS_TERMOS)
        for termo, codigo, categoria in termos:
            escritor.writerow([termo, codigo, termo, categoria])
    (pasta / "info.json").write_text(json.dumps({"modelo": "falso", "termos": len(termos), "dimensao": v.shape[1]}))
    return pasta


class LerTermosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.termos = norm.ler_termos()

    def test_inclui_mesh_e_anatomia(self):
        codigos = {t["code"] for t in self.termos}
        self.assertIn("D005334", codigos)  # Fever
        self.assertIn("ANAT001", codigos)  # Stomach

    def test_sem_par_termo_codigo_repetido(self):
        pares = [(t["term"].lower(), t["code"]) for t in self.termos]
        self.assertEqual(len(pares), len(set(pares)))


class BuscaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        termos = [("fever", "D005334", "diseases"), ("pyrexia", "D005334", "diseases"),
                  ("stomach", "ANAT001", "anatomical_site")]
        self.indice = norm.Indice(indice_falso(Path(self.tmp.name), termos, [[1, 0, 0], [0.9, 0.1, 0], [0, 0, 1]]))

    def tearDown(self):
        self.tmp.cleanup()

    def test_vizinho_mais_proximo_e_ordem(self):
        (viz,) = self.indice.buscar(np.array([[1, 0, 0]], dtype=np.float32), k=2)
        self.assertEqual([v.termo for v in viz], ["fever", "pyrexia"])
        self.assertAlmostEqual(viz[0].score, 1.0, places=2)
        self.assertGreater(viz[0].score, viz[1].score)

    def test_mascara_restringe_os_termos(self):
        mascara = np.array([False, False, True])
        (viz,) = self.indice.buscar(np.array([[1, 0, 0]], dtype=np.float32), k=2, mascara=mascara)
        self.assertEqual([v.codigo for v in viz], ["ANAT001"])

    def test_indice_ausente_explica_como_gerar(self):
        with self.assertRaisesRegex(FileNotFoundError, "normalizacao indice"):
            norm.Indice(Path(self.tmp.name) / "nao_existe")


if __name__ == "__main__":
    unittest.main()
