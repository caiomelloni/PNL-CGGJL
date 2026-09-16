"""Regressão do notebook e comportamento do lote em falhas reais de entrada."""
import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

MODULO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULO))
import combinado
import lote
from normalizacao.case_reader import ClinicalCase, read_case


class NotebookTests(unittest.TestCase):
    def test_notebook_executa_lote_e_exibe_relatorio_vazio(self):
        path = combinado.ROOT / "pipelines/notebooks/grafo_combinado_lote.ipynb"
        notebook = json.loads(path.read_text(encoding="utf-8"))
        scope = {"ROOT": combinado.ROOT, "pd": pd, "COLUNAS_RESUMO": lote.COLUNAS_RESUMO,
                 "display": lambda *args: None}
        with patch.object(lote, "executar_lote", return_value=[]) as run:
            scope["executar_lote"] = run
            with contextlib.redirect_stdout(io.StringIO()):
                for cell in notebook["cells"]:
                    source = "".join(cell["source"])
                    if cell["cell_type"] == "code" and "import logging" not in source:
                        exec(compile(source, "notebook-lote", "exec"), scope)
            run.assert_called_once_with(cases_csv=combinado.ROOT / "sample/cases.csv",
                                        output=combinado.ROOT / "data/processed", case_ids=None)
        self.assertTrue(scope["resumo"].empty)


class ValidacaoTests(unittest.TestCase):
    def test_relacoes_offsets_e_referencias_invalidas(self):
        nodes = [SimpleNamespace(node_id="P1", type="Patient"),
                 SimpleNamespace(node_id="S1", type="Symptom")]
        def edge(eid, source="P1", target="S1", relation="HAS_SYMPTOM", **attrs):
            return SimpleNamespace(edge_id=eid, source_id=source, target_id=target,
                                   relation=relation, attributes=attrs)
        edges = [
            edge("e1", char_start=0, char_end=4, evidence_text="pain"),
            edge("e2", char_start=0, char_end=4, evidence_text="wrong"),
            edge("e3", source="S1", target="P1"),
            edge("e4", relation="UNKNOWN"),
            edge("e5", target="missing"),
            edge("e6", char_start=-4, char_end=4, evidence_text="pain"),
            edge("e7", evidence_text="pain"),
        ]
        case = ClinicalCase("PMC1", None, "PMC1_01", "pain", "")
        result = SimpleNamespace(grafo=SimpleNamespace(nodes=nodes, edges=edges))
        validation = combinado.validar_grafo(case, result)
        self.assertEqual(validation.evidencias_desalinhadas, ("e2", "e6", "e7"))
        self.assertEqual(validation.arestas_fora_do_dominio, ("e3", "e4", "e5"))


class LoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.csv = self.path / "cases.csv"
        self.output = self.path / "output"
        self.rows = [dict(article_id="PMC1", age="44", case_id=f"PMC1_{i:02}",
                          case_text="pain", gender="Female") for i in range(1, 4)]
        self.loader = patch.object(lote, "carregar_recursos", return_value=object()).start()
        self.processor = patch.object(lote, "processar_caso", side_effect=self.process).start()
        self.addCleanup(patch.stopall)

    @staticmethod
    def process(case, resources):
        nodes = pd.DataFrame([dict(case_id=case.case_id, node_id="P1", type="Patient",
                                   label="patient", attributes="")], columns=combinado.NODE_COLUMNS)
        return combinado.ResultadoCaso(nodes, pd.DataFrame(columns=combinado.EDGE_COLUMNS),
                                        SimpleNamespace(nodes=[], edges=[]))

    def run_batch(self, ids=None):
        with self.csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.rows[0]))
            writer.writeheader()
            writer.writerows(self.rows)
        return lote.executar_lote(self.csv, self.output, ids)

    def test_idade_invalida_nao_interrompe_e_carrega_recursos_uma_vez(self):
        self.rows[1]["age"] = "invalid"
        with self.assertLogs(lote.LOGGER, level="ERROR"):
            summary = self.run_batch()
        self.assertEqual([r["status"] for r in summary], ["ok", "erro", "ok"])
        self.assertIn("invalid age", summary[1]["erro"])
        self.assertEqual(summary[1]["evidencias_desalinhadas"], "")
        self.assertTrue((self.output / "PMC1_03-edges.csv").exists())
        self.assertFalse((self.output / "PMC1_02-nodes.csv").exists())
        self.loader.assert_called_once()
        self.assertTrue(all(call.args[1] is self.loader.return_value
                            for call in self.processor.call_args_list))
        with (self.output / "_resumo.csv").open(encoding="utf-8", newline="") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 3)

    def test_excecao_no_processamento_nao_interrompe(self):
        def fail_middle(case, resources):
            if case.case_id == "PMC1_02":
                raise RuntimeError("falha simulada")
            return self.process(case, resources)
        self.processor.side_effect = fail_middle
        with self.assertLogs(lote.LOGGER, level="ERROR"):
            summary = self.run_batch()
        self.assertEqual([r["status"] for r in summary], ["ok", "erro", "ok"])

    def test_subconjunto_e_id_ausente(self):
        summary = self.run_batch(["PMC1_03", "PMC999_01"])
        self.assertEqual([r["case_id"] for r in summary], ["PMC1_03", "PMC999_01"])
        self.assertEqual([r["status"] for r in summary], ["ok", "erro"])
        self.assertFalse((self.output / "PMC1_01-nodes.csv").exists())

    def test_id_duplicado_nao_sobrescreve_saida(self):
        self.rows[1]["case_id"] = "PMC1_01"
        with self.assertLogs(lote.LOGGER, level="ERROR"):
            summary = self.run_batch()
        self.assertEqual([r["status"] for r in summary], ["erro", "erro", "ok"])
        self.assertFalse((self.output / "PMC1_01-nodes.csv").exists())

    def test_inconsistencias_sao_exportadas_e_contadas(self):
        with patch.object(lote, "validar_grafo", return_value=combinado.Validacao(("e1",), ("e2",))):
            summary = self.run_batch(["PMC1_01"])
        self.assertEqual(summary[0]["status"], "com_inconsistencias")
        self.assertEqual(summary[0]["evidencias_desalinhadas"], 1)
        self.assertEqual(summary[0]["arestas_fora_do_dominio"], 1)
        self.assertTrue((self.output / "PMC1_01-nodes.csv").exists())

    def test_csv_vazio_grava_cabecalho_sem_carregar_recursos(self):
        with self.csv.open("w", encoding="utf-8") as handle:
            handle.write(",".join(self.rows[0]) + "\n")
        self.assertEqual(lote.executar_lote(self.csv, self.output), [])
        self.loader.assert_not_called()
        self.assertEqual((self.output / "_resumo.csv").read_text().strip(),
                         ",".join(lote.COLUNAS_RESUMO))

    def test_falha_de_exportacao_e_registrada_e_lote_continua(self):
        export = lote.exportar_caso
        def fail_middle(result, cid, output):
            if cid == "PMC1_02":
                raise OSError("sem permissão")
            export(result, cid, output)
        with patch.object(lote, "exportar_caso", side_effect=fail_middle):
            with self.assertLogs(lote.LOGGER, level="ERROR"):
                summary = self.run_batch()
        self.assertEqual([r["status"] for r in summary], ["ok", "erro", "ok"])
        self.assertIn("OSError", summary[1]["erro"])


class RegressaoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cases = combinado.ROOT / "sample" / "cases.csv"
        if not cases.exists():
            raise unittest.SkipTest("Amostra não versionada ausente: project1/sample/cases.csv")
        cls.case = read_case(cases, "PMC5137649_01")
        cls.recursos = combinado.carregar_recursos()

    def test_csvs_iguais_ao_notebook_original_e_estado_isolado(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            before = combinado.processar_caso(self.case, self.recursos, inspecionar=True)
            other = ClinicalCase("PMC123", None, "PMC123_01", "The patient recovered.", "")
            empty = combinado.processar_caso(other, self.recursos)
            after = combinado.processar_caso(self.case, self.recursos)
        self.assertEqual(buffer.getvalue(), "")
        self.assertIsNotNone(before.inspecao)
        self.assertIsNone(after.inspecao)
        self.assertEqual(list(empty.arestas.columns), combinado.EDGE_COLUMNS)
        for suffix, frame in (("nodes", before.nos), ("edges", before.arestas)):
            reference = MODULO / "tests" / "fixtures" / f"PMC5137649_01-{suffix}.csv"
            self.assertEqual(frame.to_csv(index=False, lineterminator="\n"),
                             reference.read_text(encoding="utf-8"))
        pd.testing.assert_frame_equal(before.nos, after.nos)
        pd.testing.assert_frame_equal(before.arestas, after.arestas)
        self.assertEqual(combinado.validar_grafo(self.case, before), combinado.Validacao((), ()))


if __name__ == "__main__":
    unittest.main()
