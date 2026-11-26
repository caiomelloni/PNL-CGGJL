"""Testes unitários do módulo project3.src.avaliacao.extracao."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from project3.src.avaliacao.extracao import COLUNAS_EXTRACAO, SistemaConfig, avaliar_extracao, sistemas_padrao


class TestAvaliacaoExtracao(unittest.TestCase):
    def test_gera_tabela_gold_e_maccrobat_com_telemetria(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            gold_m = base / "gold_mencoes.csv"
            gold_r = base / "gold_relacoes.csv"
            macc_m = base / "macc_mencoes.csv"
            divisoes = base / "divisoes.csv"
            prof_m = base / "prof_mencoes.csv"
            prof_r = base / "prof_relacoes.csv"
            prof_aluc = base / "alucinacoes.csv"
            execucao = base / "execucao.csv"
            aluno_m = base / "aluno_mencoes.csv"
            aluno_res = base / "aluno_resumo.json"
            saida = base / "extracao.csv"

            with gold_m.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["case_id", "id", "start", "end", "texto", "tipo", "mesh", "polaridade"])
                w.writeheader()
                w.writerow({"case_id": "PMC1_01", "id": "M1", "start": 0, "end": 5, "texto": "fever", "tipo": "Symptom", "mesh": "", "polaridade": "present"})
                w.writerow({"case_id": "PMC1_01", "id": "M2", "start": 10, "end": 16, "texto": "cough", "tipo": "Symptom", "mesh": "", "polaridade": "absent"})

            with gold_r.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["case_id", "origem", "destino", "relacao"])
                w.writeheader()
                w.writerow({"case_id": "PMC1_01", "origem": "P1", "destino": "M1", "relacao": "HAS_SYMPTOM"})

            with macc_m.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["case_id", "id", "start", "end", "texto", "tipo", "mesh", "polaridade", "confianca", "fonte"])
                w.writeheader()
                w.writerow({"case_id": "9001", "id": "M1", "start": 0, "end": 5, "texto": "fever", "tipo": "Symptom", "mesh": "", "polaridade": "present", "confianca": "1.0", "fonte": "maccrobat"})

            with divisoes.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["fonte", "case_id", "article_id", "particao"])
                w.writeheader()
                w.writerow({"fonte": "maccrobat", "case_id": "9001", "article_id": "9001", "particao": "teste"})

            with prof_m.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["case_id", "id", "start", "end", "texto", "tipo", "mesh", "polaridade", "confianca", "fonte"])
                w.writeheader()
                w.writerow({"case_id": "PMC1_01", "id": "M1", "start": 0, "end": 5, "texto": "fever", "tipo": "Symptom", "mesh": "", "polaridade": "present", "confianca": "0.9", "fonte": "llm:demo"})
                w.writerow({"case_id": "PMC1_01", "id": "M2", "start": 10, "end": 16, "texto": "cough", "tipo": "Symptom", "mesh": "", "polaridade": "absent", "confianca": "0.9", "fonte": "llm:demo"})
                w.writerow({"case_id": "9001", "id": "M1", "start": 0, "end": 5, "texto": "fever", "tipo": "Symptom", "mesh": "", "polaridade": "present", "confianca": "0.9", "fonte": "llm:demo"})

            with prof_r.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["case_id", "origem", "destino", "relacao", "confianca"])
                w.writeheader()
                w.writerow({"case_id": "PMC1_01", "origem": "P1", "destino": "M1", "relacao": "HAS_SYMPTOM", "confianca": "1.0"})

            with prof_aluc.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["case_id", "texto", "tipo", "motivo"])
                w.writeheader()
                w.writerow({"case_id": "PMC1_01", "texto": "inventado", "tipo": "Diagnosis", "motivo": "nao_encontrado"})
                w.writerow({"case_id": "9001", "texto": "inventado2", "tipo": "Symptom", "motivo": "nao_encontrado"})
                w.writerow({"case_id": "9001", "texto": "inventado3", "tipo": "Symptom", "motivo": "nao_encontrado"})
                # Descartado por outro motivo: não é alucinação e não pode ser contado.
                w.writerow({"case_id": "9001", "texto": "fever", "tipo": "Sintoma", "motivo": "tipo_invalido"})

            with execucao.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["case_id", "segundos", "custo_usd"])
                w.writeheader()
                w.writerow({"case_id": "PMC1_01", "segundos": "2.5", "custo_usd": "0.012"})
                w.writerow({"case_id": "9001", "segundos": "1.5", "custo_usd": "0.008"})

            with aluno_m.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["case_id", "id", "start", "end", "texto", "tipo", "mesh", "polaridade", "confianca", "fonte"])
                w.writeheader()
                w.writerow({"case_id": "9001", "id": "M1", "start": 0, "end": 5, "texto": "fever", "tipo": "Symptom", "mesh": "", "polaridade": "present", "confianca": "0.8", "fonte": "aluno:v1"})

            aluno_res.write_text(json.dumps({"segundos_por_caso": 0.05}), encoding="utf-8")

            sistemas = [
                SistemaConfig(
                    nome="professor",
                    mencoes=prof_m,
                    relacoes=prof_r,
                    alucinacoes=prof_aluc,
                    metricas_execucao=execucao,
                    custo_padrao=None,
                ),
                SistemaConfig(
                    nome="aluno",
                    mencoes=aluno_m,
                    metricas_execucao=aluno_res,
                    custo_padrao=0.0,
                ),
            ]

            linhas = avaliar_extracao(
                sistemas=sistemas,
                gold_mencoes=gold_m,
                gold_relacoes=gold_r,
                maccrobat_mencoes=macc_m,
                caminho_divisoes=divisoes,
                saida=saida,
            )

            with saida.open(encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                self.assertEqual(tuple(reader.fieldnames or ()), COLUNAS_EXTRACAO)
                lidas = list(reader)

            self.assertEqual(len(linhas), len(lidas))
            por_chave = {(r["conjunto"], r["sistema"], r["criterio"]): r for r in lidas}

            # Professor no gold_p2: F1 1.0 em menções, tipos, polaridade e relações + 1 alucinação
            pg = por_chave[("gold_p2", "professor", "exato")]
            self.assertEqual(pg["mencoes_f1"], "1.0000")
            self.assertEqual(pg["tipos_macro_f1"], "1.0000")
            self.assertEqual(pg["polaridade_f1_absent"], "1.0000")
            self.assertEqual(pg["relacoes_f1"], "1.0000")
            self.assertEqual(pg["alucinacoes"], "1")
            self.assertEqual(pg["segundos_por_caso"], "2.5000")
            self.assertEqual(pg["custo_usd_por_caso"], "0.012000")

            # Professor no maccrobat_teste: polaridade medida, sem relações, 2 alucinações (tipo_invalido não conta)
            pm = por_chave[("maccrobat_teste", "professor", "exato")]
            self.assertEqual(pm["mencoes_f1"], "1.0000")
            self.assertEqual(pm["polaridade_acuracia"], "1.0000")
            self.assertEqual(pm["relacoes_f1"], "")
            self.assertEqual(pm["alucinacoes"], "2")

            # Aluno no maccrobat_teste: telemetria via JSON e custo 0.0
            am = por_chave[("maccrobat_teste", "aluno", "exato")]
            self.assertEqual(am["segundos_por_caso"], "0.0500")
            self.assertEqual(am["custo_usd_por_caso"], "0.000000")


    def test_telemetria_do_professor_vem_do_execucao_por_caso(self) -> None:
        # uso_llm.csv não tem case_id; execucao.csv tem segundos e custo por caso.
        professor = next(s for s in sistemas_padrao(Path("/repo")) if s.nome == "professor")
        self.assertEqual(professor.metricas_execucao, Path("/repo/project3/data/interim/professor/execucao.csv"))


if __name__ == "__main__":
    unittest.main()
