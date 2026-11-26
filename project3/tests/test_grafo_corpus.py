"""Testes unitários do pipeline de geração de grafos em lotes com retomada."""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from project2.src.montagem.montagem import EDGE_COLUMNS, NODE_COLUMNS
from project3.src.dados import grafo_corpus


def _preditor_falso(mencoes: list[dict], textos: dict[str, str]) -> list[dict]:
    """Preditor determinístico sem modelo para testar loteamento e retomada."""
    rels = []
    for m in mencoes:
        if m["tipo"] == "Symptom":
            rels.append({
                "case_id": m["case_id"],
                "origem": "P1",
                "destino": m["id"],
                "relacao": "HAS_SYMPTOM",
                "confianca": "1.0",
            })
    return rels


class TestGrafoCorpus(unittest.TestCase):
    def _criar_fixture(self, base: Path) -> tuple[Path, Path]:
        corpus = base / "cases.csv"
        mencoes = base / "mencoes_tipadas.csv"

        with corpus.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["article_id", "age", "case_id", "case_text", "gender"])
            w.writeheader()
            for i in (1, 2, 3):
                w.writerow({
                    "article_id": f"PMC{i}",
                    "age": "40",
                    "case_id": f"PMC{i}_01",
                    "case_text": "Patient presented with fever.",
                    "gender": "M",
                })

        with mencoes.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["case_id", "id", "start", "end", "texto", "tipo", "mesh", "polaridade", "confianca", "fonte"],
            )
            w.writeheader()
            for i in (1, 2, 3):
                w.writerow({
                    "case_id": f"PMC{i}_01",
                    "id": "M1",
                    "start": 23,
                    "end": 28,
                    "texto": "fever",
                    "tipo": "Symptom",
                    "mesh": "",
                    "polaridade": "present",
                    "confianca": "0.95",
                    "fonte": "aluno:teste",
                })
        return corpus, mencoes

    def test_processamento_em_lotes_e_retomada(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            corpus, mencoes = self._criar_fixture(base)
            saida = base / "grafos"
            rels_out = base / "relacoes.csv"

            # 1ª execução: 3 casos com tamanho_lote=2 -> 2 lotes
            res1 = grafo_corpus.gerar_grafos(
                mencoes=mencoes,
                corpus=corpus,
                saida=saida,
                tamanho_lote=2,
                relacoes_saida=rels_out,
                preditor_relacoes=_preditor_falso,
            )
            self.assertEqual(res1["casos_processados"], 3)
            self.assertEqual(res1["casos_pulados_retomada"], 0)
            self.assertEqual(res1["lotes_executados"], 2)

            # Conferir contrato CSV de nós e arestas
            with (saida / "PMC1_01-nodes.csv").open(encoding="utf-8", newline="") as f:
                r = csv.DictReader(f)
                self.assertEqual(r.fieldnames, NODE_COLUMNS)
                nos = list(r)
                self.assertEqual(len(nos), 2)  # P1 + Symptom
            with (saida / "PMC1_01-edges.csv").open(encoding="utf-8", newline="") as f:
                r = csv.DictReader(f)
                self.assertEqual(r.fieldnames, EDGE_COLUMNS)
                arestas = list(r)
                self.assertEqual(len(arestas), 1)
                self.assertEqual(arestas[0]["relation"], "HAS_SYMPTOM")

            # 2ª execução (retomada): todos os 3 casos já existem e são pulados
            chamadas = []
            res2 = grafo_corpus.gerar_grafos(
                mencoes=mencoes,
                corpus=corpus,
                saida=saida,
                tamanho_lote=2,
                preditor_relacoes=lambda m, t: chamadas.append(len(m)) or _preditor_falso(m, t),
            )
            self.assertEqual(res2["casos_processados"], 0)
            self.assertEqual(res2["casos_pulados_retomada"], 3)
            self.assertEqual(chamadas, [])

            # 3ª execução: remove 1 caso para simular interrupção -> retoma só o faltante
            (saida / "PMC2_01-nodes.csv").unlink()
            res3 = grafo_corpus.gerar_grafos(
                mencoes=mencoes,
                corpus=corpus,
                saida=saida,
                tamanho_lote=2,
                preditor_relacoes=_preditor_falso,
            )
            self.assertEqual(res3["casos_processados"], 1)
            self.assertEqual(res3["casos_pulados_retomada"], 2)
            self.assertTrue((saida / "PMC2_01-nodes.csv").is_file())


if __name__ == "__main__":
    unittest.main()
