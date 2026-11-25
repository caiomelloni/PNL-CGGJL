"""Índice MeSH: leitura dos gazetteers e busca do vizinho mais próximo (sem rede e sem modelo)."""
import csv
import json
import tempfile
import unittest
import unittest.mock
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


class CodificadorFalso:
    """Vetores fixos por texto, para testar sem baixar o SapBERT."""
    VETORES = {"fever": [1, 0, 0], "high fever": [0.9, 0.3, 0], "gastric": [0, 0.2, 1],
               "febrile drug": [0.6, 0.8, 0], "banana": [1, -1, -1]}

    def codificar(self, textos):
        v = np.array([self.VETORES[t] for t in textos], dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)


class NormalizarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)
        termos = [("fever", "D005334", "diseases"), ("antipyretic", "D018712", "drugs"),
                  ("stomach", "ANAT001", "anatomical_site")]
        indice_falso(self.pasta, termos, [[1, 0, 0], [0.5, 1, 0], [0, 0, 1]])
        norm.indice.cache_clear()
        self.patch = unittest.mock.patch.object(norm, "codificador", lambda modelo: CodificadorFalso())
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        norm.indice.cache_clear()
        self.tmp.cleanup()

    def test_codigo_e_score_com_limiar(self):
        saida = norm.normalizar(["Fever ", "high fever", "banana"], metodo="sapbert", limiar=0.8, pasta=self.pasta)
        self.assertEqual([c for c, _ in saida], ["D005334", "D005334", ""])
        self.assertAlmostEqual(saida[0][1], 1.0, places=2)
        self.assertGreater(saida[2][1], 0)  # o score volta mesmo sem código

    def test_filtro_por_tipo(self):
        # "febrile drug" fica mais perto de antipyretic, mas um Symptom só procura em diseases.
        (sem,) = norm.normalizar(["febrile drug"], ["Symptom"], metodo="sapbert", limiar=0, pasta=self.pasta)
        (com,) = norm.normalizar(["febrile drug"], ["Symptom"], metodo="sapbert", limiar=0, filtrar_tipo=True,
                                pasta=self.pasta)
        self.assertEqual((sem[0], com[0]), ("D018712", "D005334"))

    def test_lexico_primeiro_e_sapbert_no_que_sobra(self):
        lexico = {"fever": "D999999", "high fever": ""}
        with unittest.mock.patch.object(norm, "_lexico_p2", lambda textos, casos: [lexico[t] for t in textos]):
            saida = norm.normalizar(["fever", "high fever"], limiar=0.8, pasta=self.pasta)
        self.assertEqual(saida[0], ("D999999", 1.0))  # o léxico ganha mesmo discordando do SapBERT
        self.assertEqual(saida[1][0], "D005334")

    def test_metodo_desconhecido_falha(self):
        with self.assertRaises(ValueError):
            norm.normalizar(["fever"], metodo="outro", pasta=self.pasta)

    def test_tamanhos_diferentes_falham(self):
        with self.assertRaises(ValueError):
            norm.normalizar(["fever"], ["Symptom", "Finding"], pasta=self.pasta)

    def test_csv_mantem_colunas_e_preenche_mesh(self):
        entrada, saida = self.pasta / "mencoes.csv", self.pasta / "saida.csv"
        entrada.write_text("case_id,id,start,end,texto,tipo,mesh,polaridade,confianca,fonte\n"
                           "C1,m1,0,5,fever,Symptom,,present,1.0,llm:x\n"
                           "C1,m2,9,16,gastric,AnatomicalSite,X999,present,0.9,llm:x\n")
        self.assertEqual(norm.normalizar_csv(entrada, saida, metodo="sapbert", limiar=0.8, pasta=self.pasta), 2)
        with saida.open(encoding="utf-8", newline="") as f:
            leitor = csv.DictReader(f)
            linhas = list(leitor)
        self.assertEqual(leitor.fieldnames[:10], ["case_id", "id", "start", "end", "texto", "tipo", "mesh",
                                                  "polaridade", "confianca", "fonte"])
        self.assertEqual(leitor.fieldnames[-1], "mesh_score")
        self.assertEqual([l["mesh"] for l in linhas], ["D005334", "ANAT001"])  # o código antigo é trocado
        self.assertEqual(linhas[0]["fonte"], "llm:x")


if __name__ == "__main__":
    unittest.main()
