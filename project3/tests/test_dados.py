"""Testes unitários do módulo project3.src.dados (divisões e MACCROBAT)."""
from __future__ import annotations

import csv
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from project3.src.dados import divisoes, maccrobat


class TestDivisoesCommitado(unittest.TestCase):
    """Valida o arquivo versionado project3/data/divisoes.csv contra vazamento."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.caminho = divisoes.SAIDA_PADRAO
        if not cls.caminho.is_file():
            raise unittest.SkipTest(f"{cls.caminho} ainda não existe")
        with cls.caminho.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            cls.colunas = tuple(reader.fieldnames or ())
            cls.linhas = list(reader)

    def test_colunas_e_valores_validos(self) -> None:
        self.assertEqual(self.colunas, divisoes.COLUNAS)
        self.assertGreater(len(self.linhas), 0)
        vistos: set[tuple[str, str]] = set()
        for linha in self.linhas:
            self.assertIn(linha["fonte"], divisoes.FONTES_VALIDAS)
            self.assertIn(linha["particao"], divisoes.PARTICOES_VALIDAS)
            self.assertTrue(linha["case_id"])
            self.assertTrue(linha["article_id"])
            chave = (linha["fonte"], linha["case_id"])
            self.assertNotIn(chave, vistos, f"case_id duplicado: {chave}")
            vistos.add(chave)

    def test_nenhum_article_id_em_duas_particoes(self) -> None:
        particoes_por_artigo: dict[tuple[str, str], set[str]] = defaultdict(set)
        for linha in self.linhas:
            particoes_por_artigo[(linha["fonte"], linha["article_id"])].add(linha["particao"])
        vazados = {k: v for k, v in particoes_por_artigo.items() if len(v) > 1}
        self.assertEqual(vazados, {}, f"article_ids em múltiplas partições: {vazados}")

    def test_oito_casos_gold_em_teste(self) -> None:
        gold_ids = divisoes.carregar_gold()
        self.assertEqual(len(gold_ids), 8)
        particao_por_caso = {
            linha["case_id"]: linha["particao"]
            for linha in self.linhas
            if linha["fonte"] == "multicare"
        }
        for cid in gold_ids:
            self.assertIn(cid, particao_por_caso, f"Caso gold ausente em divisoes.csv: {cid}")
            self.assertEqual(
                particao_por_caso[cid],
                "teste",
                f"Caso gold {cid} deveria estar em 'teste', mas está em {particao_por_caso[cid]!r}",
            )

    def test_tres_particoes_presentes_em_ambas_fontes(self) -> None:
        for fonte in divisoes.FONTES_VALIDAS:
            particoes = {r["particao"] for r in self.linhas if r["fonte"] == fonte}
            self.assertEqual(particoes, divisoes.PARTICOES_VALIDAS, f"Partições incompletas em {fonte}")


class TestGerarDivisoesIsolado(unittest.TestCase):
    """Testa a lógica de divisoes.gerar_divisoes em dados sintéticos."""

    def test_agrupamento_gold_e_sobreposicao_pmid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cases_mc = base / "cases.csv"
            meta_mc = base / "metadata.csv"
            casos_macc = base / "maccrobat_casos.csv"
            gold = base / "gold.txt"
            saida = base / "divisoes.csv"

            # 10 artigos no MultiCaRe (artigo PMC1 tem 2 casos e está no gold; PMC2 compartilha PMID 999)
            with cases_mc.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["article_id", "age", "case_id", "case_text", "gender"])
                w.writeheader()
                w.writerow({"article_id": "PMC1", "age": "", "case_id": "PMC1_01", "case_text": "t", "gender": ""})
                w.writerow({"article_id": "PMC1", "age": "", "case_id": "PMC1_02", "case_text": "t", "gender": ""})
                for i in range(2, 11):
                    w.writerow({"article_id": f"PMC{i}", "age": "", "case_id": f"PMC{i}_01", "case_text": "t", "gender": ""})

            with meta_mc.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["article_id", "pmid"])
                w.writeheader()
                w.writerow({"article_id": "PMC2", "pmid": "999"})

            with casos_macc.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["article_id", "case_id", "case_text"])
                w.writeheader()
                w.writerow({"article_id": "999", "case_id": "999", "case_text": "t"})
                for i in range(1, 10):
                    w.writerow({"article_id": str(100 + i), "case_id": str(100 + i), "case_text": "t"})

            gold.write_text("PMC1_01\n", encoding="utf-8")

            resumo = divisoes.gerar_divisoes(
                cases_multicare=cases_mc,
                metadata_multicare=meta_mc,
                casos_maccrobat=casos_macc,
                caminho_gold=gold,
                saida=saida,
                semente=42,
            )
            self.assertEqual(resumo["sobreposicao_pmid_multicare_maccrobat"], 1)

            linhas = divisoes.carregar_divisoes(saida)
            por_chave = {(r["fonte"], r["case_id"]): r["particao"] for r in linhas}
            # Gold e irmão do mesmo artigo devem ficar juntos em teste
            self.assertEqual(por_chave[("multicare", "PMC1_01")], "teste")
            self.assertEqual(por_chave[("multicare", "PMC1_02")], "teste")
            # Sobreposição de PMID deve herdar a mesma partição
            self.assertEqual(por_chave[("multicare", "PMC2_01")], por_chave[("maccrobat", "999")])


class TestConversorMaccrobat(unittest.TestCase):
    """Testa a conversão brat -> contrato P2/P3 em arquivos sintéticos."""

    def test_converte_e_filtra_tipos_e_descontinuas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            entrada = base / "brat"
            saida = base / "out"
            entrada.mkdir()

            texto = "A 30-year-old man presented with fever and chest pain."
            (entrada / "12345.txt").write_text(texto, encoding="utf-8")
            (entrada / "12345.ann").write_text(
                "\n".join([
                    "T1\tAge 2 13\t30-year-old",
                    "T2\tSign_symptom 33 38\tfever",
                    "T3\tSign_symptom 33 38;43 53\tfever chest pain",
                    "T4\tBiological_structure 43 48\tchest",
                    "R1\tMODIFY Arg1:T2 Arg2:T4",
                ]) + "\n",
                encoding="utf-8",
            )

            resumo = maccrobat.converter(entrada=entrada, saida=saida)
            self.assertEqual(resumo["casos"], 1)
            self.assertEqual(resumo["mencoes_convertidas"], 2)
            self.assertEqual(resumo["descartadas_sem_equivalente"], 1)
            self.assertEqual(resumo["descartadas_descontinuas"], 1)

            with (saida / "mencoes.csv").open(encoding="utf-8", newline="") as f:
                mencoes = list(csv.DictReader(f))
            self.assertEqual(len(mencoes), 2)
            for m in mencoes:
                self.assertEqual(m["texto"], texto[int(m["start"]) : int(m["end"])])
                self.assertEqual(m["polaridade"], "")
                self.assertEqual(m["fonte"], "maccrobat")
            self.assertEqual([m["tipo"] for m in mencoes], ["Symptom", "AnatomicalSite"])

    def test_falha_quando_offset_diverge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            entrada = base / "brat"
            saida = base / "out"
            entrada.mkdir()
            (entrada / "1.txt").write_text("Patient has fever.", encoding="utf-8")
            (entrada / "1.ann").write_text("T1\tSign_symptom 0 5\tfever\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                maccrobat.converter(entrada=entrada, saida=saida)


if __name__ == "__main__":
    unittest.main()
