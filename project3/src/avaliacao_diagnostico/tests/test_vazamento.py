"""Testes de vazamento (regra 6 de docs/vazamento-de-dados.md).

Os de unidade usam dados escritos à mão. Os de integração rodam sobre o código e as saídas reais
da frente D e são pulados enquanto elas não existem.
"""
import importlib.util
import unittest
from pathlib import Path

from project3.src.avaliacao_diagnostico import avaliar as av
from project3.src.avaliacao_diagnostico import vazamento as vz

NODES = [
    {"type": "Patient", "label": "case A", "attributes": ""},
    {"type": "Diagnosis", "label": "tuberculosis", "attributes": "polarity=present; mesh=D014376"},
    {"type": "Diagnosis", "label": "lymphoma", "attributes": "polarity=absent; mesh=D008223"},
    {"type": "Symptom", "label": "fever", "attributes": "polarity=present; mesh=D005334"},
    {"type": "Treatment", "label": "rifampicin", "attributes": "polarity=present; mesh=D012293"},
]
TEM_MOTOR = importlib.util.find_spec("project3.src.diagnostico") is not None


class ConsultaTests(unittest.TestCase):
    def test_consulta_limpa_passa(self):
        consulta = [{"type": "Symptom", "label": "fever", "mesh": "D005334"},
                    {"type": "ExamResult", "label": "elevated CRP", "attributes": "polarity=present"}]
        self.assertEqual(vz.problemas_da_consulta(consulta, NODES), [])

    def test_tipo_fora_da_lista_falha(self):
        consulta = [{"type": "Treatment", "label": "rifampicin", "attributes": "mesh=D012293"}]
        self.assertTrue(any("tipo" in p for p in vz.problemas_da_consulta(consulta, NODES)))

    def test_diagnostico_disfarcado_de_achado_falha(self):
        # O P2 às vezes classifica o diagnóstico como Finding: o código e o nome denunciam.
        por_codigo = [{"type": "Finding", "label": "TB", "attributes": "polarity=present; mesh=D014376"}]
        por_nome = [{"type": "Finding", "label": "pulmonary tuberculosis", "attributes": ""}]
        self.assertTrue(vz.problemas_da_consulta(por_codigo, NODES))
        self.assertTrue(vz.problemas_da_consulta(por_nome, NODES))

    def test_diagnostico_negado_tambem_nao_pode(self):
        consulta = [{"type": "Finding", "label": "no lymphoma", "attributes": "polarity=absent"}]
        self.assertTrue(vz.problemas_da_consulta(consulta, NODES))

    def test_nome_so_casa_palavra_inteira(self):
        nodes = [{"type": "Diagnosis", "label": "flu", "attributes": ""}]
        self.assertEqual(vz.problemas_da_consulta([{"type": "Symptom", "label": "fluid loss"}], nodes), [])


class FontesTests(unittest.TestCase):
    def pred(self, fontes):
        return {"rag_grafo": {"PMC1_01": [av.Sugestao(1, "D1", "x", tuple(fontes))]}}

    def test_artigo_pelo_prefixo_e_pelas_divisoes(self):
        self.assertEqual(vz.article_id("PMC4782471_02"), "PMC4782471")
        self.assertEqual(vz.article_id("doc7", {"doc7": "M7"}), "M7")

    def test_fonte_de_outro_artigo_passa(self):
        self.assertEqual(vz.problemas_das_fontes(self.pred(["PMC2_01", "PMC3_04"])), [])

    def test_o_proprio_caso_ou_irmao_do_mesmo_artigo_falha(self):
        self.assertEqual(len(vz.problemas_das_fontes(self.pred(["PMC1_01"]))), 1)
        self.assertEqual(len(vz.problemas_das_fontes(self.pred(["PMC2_01", "PMC1_02"]))), 1)

    def test_comando_para_quando_ha_vazamento(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            pred = Path(tmp) / "predicoes.csv"
            pred.write_text("sistema,case_id,rank,mesh,rotulo,score,casos_fonte\n"
                            "rag_grafo,PMC9532611_01,1,D006973,hypertension,0.9,PMC9532611_02\n")
            with self.assertRaisesRegex(SystemExit, "vazamento"):
                av.main(["--predicoes", str(pred), "--grafos", str(av.GRAFOS_P2),
                         "--saida", str(Path(tmp) / "saida.csv")])


class IntegracaoTests(unittest.TestCase):
    """Rodam sobre o motor e as predições reais da frente D, quando existirem."""

    @unittest.skipUnless(TEM_MOTOR, "project3.src.diagnostico (frente D) ainda não existe")
    def test_montar_consulta_nao_vaza_em_nenhum_grafo(self):
        from project3.src.diagnostico import montar_consulta

        pasta = av.GRAFOS if av.GRAFOS.is_dir() else av.GRAFOS_P2
        problemas = []
        for arquivo in sorted(pasta.glob("*-nodes.csv")):
            nodes = av.ler_csv(arquivo)
            edges_arq = arquivo.with_name(arquivo.name.replace("-nodes", "-edges"))
            edges = av.ler_csv(edges_arq) if edges_arq.is_file() else []
            problemas += [f"{arquivo.name}: {p}" for p in vz.problemas_da_consulta(montar_consulta(nodes, edges), nodes)]
        self.assertEqual(problemas, [])

    @unittest.skipUnless(av.PREDICOES.is_file(), "predicoes.csv (frente D) ainda não existe")
    def test_predicoes_reais_nao_citam_o_mesmo_artigo(self):
        artigos = vz.ler_artigos(av.DIVISOES)
        self.assertEqual(vz.problemas_das_fontes(av.ler_predicoes(), artigos), [])


if __name__ == "__main__":
    unittest.main()
