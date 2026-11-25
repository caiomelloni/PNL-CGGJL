"""Top-k, MRR e acerto hierárquico com predições escritas à mão."""
import tempfile
import unittest
from pathlib import Path

from project3.src.avaliacao_diagnostico import avaliar as av
from project3.src.avaliacao_diagnostico.arvore import Arvore

# Árvore pequena: Hypertension (C14.907.489) é pai de Hypertension, Pregnancy-Induced (C14.907.489.480).
ARVORE = Arvore({"D006973": ("C14.907.489",), "D046110": ("C14.907.489.480", "C13.703.395"),
                 "D014652": ("C14.907",), "D001145": ("C14.280.067",)})

PREDICOES = """sistema,case_id,rank,mesh,rotulo,score,casos_fonte
rag_grafo,A,1,D006973,hypertension,0.9,X_01;Y_01
rag_grafo,A,2,D001145,arrhythmia,0.5,Y_01
rag_grafo,B,2,D000001,outro,0.4,
rag_grafo,B,1,D046110,gestational hypertension,0.8,Z_01
grafo,A,1,,sem codigo,0.9,X_01
grafo,A,3,D006973,hypertension,0.3,X_01
"""


def escrever(pasta: Path, nome: str, texto: str) -> Path:
    caminho = pasta / nome
    caminho.write_text(texto, encoding="utf-8")
    return caminho


class AvaliarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)
        self.pred = av.ler_predicoes(escrever(self.pasta, "predicoes.csv", PREDICOES))
        # A: hipertensão; B: hipertensão também, mas o sistema sugeriu a gestacional (filho).
        # C: ninguém previu nada, e conta como erro para todos.
        self.certos = {"A": {"D006973"}, "B": {"D006973"}, "C": {"D001145"}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_ordena_por_rank_e_le_fontes(self):
        b = self.pred["rag_grafo"]["B"]
        self.assertEqual([s.rank for s in b], [1, 2])
        self.assertEqual(self.pred["rag_grafo"]["A"][0].casos_fonte, ("X_01", "Y_01"))

    def test_topk_e_mrr_exatos(self):
        linhas = {l["sistema"]: l for l in av.avaliar(self.pred, self.certos)}
        rag, grafo = linhas["rag_grafo"], linhas["grafo"]
        self.assertEqual((rag["top1"], rag["top5"], rag["mrr"]), (0.3333, 0.3333, 0.3333))
        # "grafo" acerta A só no rank 3: entra no top-3 e no top-5, não no top-1.
        self.assertEqual((grafo["top1"], grafo["top3"], grafo["mrr"]), (0.0, 0.3333, 0.1111))
        self.assertEqual((rag["casos"], rag["casos_sem_predicao"], grafo["casos_sem_predicao"]), (3, 1, 2))
        self.assertNotIn("top1_hier", rag)

    def test_hierarquico_fica_separado(self):
        rag = {l["sistema"]: l for l in av.avaliar(self.pred, self.certos, ARVORE)}["rag_grafo"]
        self.assertEqual(rag["top1"], 0.3333)       # o exato não muda
        self.assertEqual(rag["top1_hier"], 0.6667)  # B conta: gestacional é filho de hipertensão

    def test_arvore_pai_e_filho_um_nivel(self):
        self.assertTrue(ARVORE.parentes("D046110", "D006973"))
        self.assertTrue(ARVORE.parentes("D006973", "D046110"))
        self.assertFalse(ARVORE.parentes("D046110", "D014652"))  # avô não conta
        self.assertFalse(ARVORE.parentes("D006973", "D001145"))
        self.assertFalse(ARVORE.parentes("D999999", "D006973"))  # código fora da árvore

    def test_respostas_ignora_diagnostico_negado_e_sem_codigo(self):
        grafo = self.pasta / "grafo"
        grafo.mkdir()
        escrever(grafo, "A-nodes.csv", "case_id,node_id,type,label,attributes\n"
                 "A,P1,Patient,case A,\n"
                 "A,D1,Diagnosis,hypertension,polarity=present; mesh=D006973\n"
                 "A,D2,Diagnosis,lupus,polarity=absent; mesh=D008180\n"
                 "A,D3,Diagnosis,kjd,polarity=present\n"
                 "A,S1,Symptom,headache,polarity=present; mesh=D006261\n")
        escrever(grafo, "B-nodes.csv", "case_id,node_id,type,label,attributes\nB,D1,Diagnosis,x,polarity=present\n")
        self.assertEqual(av.respostas({"A", "B", "sem_grafo"}, grafo), {"A": {"D006973"}})

    def test_casos_de_teste_pelas_divisoes(self):
        divisoes = escrever(self.pasta, "divisoes.csv", "fonte,case_id,article_id,particao\n"
                            "multicare,A,PMC1,teste\nmulticare,B,PMC2,treino\nmaccrobat,M,doc1,teste\n")
        self.assertEqual(av.casos_de_teste(divisoes), {"A"})

    def test_sem_divisoes_usa_gold_do_p2(self):
        self.assertEqual(len(av.casos_de_teste(self.pasta / "nao_existe.csv")), 8)

    def test_coluna_faltando_falha(self):
        with self.assertRaisesRegex(ValueError, "casos_fonte"):
            av.ler_predicoes(escrever(self.pasta, "ruim.csv", "sistema,case_id,rank,mesh,rotulo,score\nx,A,1,D1,a,1\n"))

    def test_escreve_tabela(self):
        saida = self.pasta / "diagnostico.csv"
        av.escrever(av.avaliar(self.pred, self.certos, ARVORE), saida)
        self.assertTrue(saida.read_text().startswith("sistema,casos,casos_sem_predicao,top1,top3,top5,mrr,top1_hier"))


if __name__ == "__main__":
    unittest.main()
