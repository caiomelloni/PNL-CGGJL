"""Professor com um LLM falso: ancoragem, alucinações, contrato da montagem e partições."""
import json
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

from project2.src.comum import casos_gold
from project3.src.llm import cliente
from project3.src.professor import professor
from project3.src.professor.ancoragem import ancorar
from project3.src.professor.divisoes import artigo, garantir_fora_do_teste, ler_divisoes

TEXTO = ("A 45-year-old man presented with fever and abdominal pain. He denied chest pain. "
         "Computed tomography showed a cystic lesion in the pancreas. Fever resolved after drainage.")


def item(texto, tipo, polaridade="present"):
    return {"texto": texto, "tipo": tipo, "polaridade": polaridade}


class LLMFalso:
    """Responde com as menções de RESPOSTAS que aparecem no trecho, mais uma inventada."""
    __name__ = "falso"
    RESPOSTAS = [item("fever", "Symptom"), item("abdominal pain", "Symptom"),
                 item("chest pain", "Symptom", "absent"), item("Computed  tomography", "Exam"),
                 item("cystic lesion", "Finding"), item("pancreas", "AnatomicalSite"),
                 item("Fever", "Symptom"), item("drainage", "Treatment"), item("vomiting", "Symptom")]

    def __init__(self):
        self.chamadas = 0

    def __call__(self, prompt, sistema, modelo, temperatura, json_):
        self.chamadas += 1
        if "propositions" in sistema and "## Types" not in sistema:
            return {"texto": '{"proposicoes": ["The man had fever."]}', "tokens_entrada": 10, "tokens_saida": 5}
        trecho = prompt.split("<<<\n", 1)[1].split("\n>>>", 1)[0].lower()
        itens = [i for i in self.RESPOSTAS if " ".join(i["texto"].lower().split()) in trecho]
        if "fever" in trecho:
            itens.append(item("vomiting", "Symptom"))  # alucinação: não está no texto
        return {"texto": json.dumps({"mencoes": itens}), "tokens_entrada": 100, "tokens_saida": 50,
                "custo_usd": 0.01}


class TestAncoragem(unittest.TestCase):
    def test_acha_offsets_e_grava_o_texto_original(self):
        achadas, perdidas = ancorar(TEXTO, 0, len(TEXTO), [item("ABDOMINAL   pain", "Symptom")])
        self.assertEqual(perdidas, [])
        m = achadas[0]
        self.assertEqual(TEXTO[m["start"]:m["end"]], m["texto"])
        self.assertEqual(m["texto"], "abdominal pain")

    def test_repeticao_usa_a_ocorrencia_seguinte(self):
        achadas, _ = ancorar(TEXTO, 0, len(TEXTO), [item("fever", "Symptom"), item("fever", "Symptom")])
        self.assertEqual(len({m["start"] for m in achadas}), 2)

    def test_fronteira_de_palavra(self):
        _, perdidas = ancorar("Painful swelling.", 0, 17, [item("pain", "Symptom")])
        self.assertEqual(perdidas[0]["motivo"], "nao_encontrado")

    def test_so_procura_dentro_do_trecho(self):
        fim = TEXTO.index("He denied")
        _, perdidas = ancorar(TEXTO, 0, fim, [item("chest pain", "Symptom")])
        self.assertEqual(perdidas[0]["motivo"], "nao_encontrado")

    def test_descarta_e_registra_o_que_nao_serve(self):
        achadas, perdidas = ancorar(TEXTO, 0, len(TEXTO), [
            item("vomiting", "Symptom"), item("fever", "Sintoma"), item("", "Symptom"), "lixo"])
        self.assertEqual(achadas, [])
        self.assertEqual([p["motivo"] for p in perdidas],
                         ["nao_encontrado", "tipo_invalido", "texto_vazio", "item_invalido"])

    def test_polaridade_fora_do_contrato_vira_present(self):
        achadas, _ = ancorar(TEXTO, 0, len(TEXTO), [item("fever", "Symptom", "maybe"),
                                                     item("chest pain", "Symptom", "ABSENT")])
        self.assertEqual([m["polaridade"] for m in achadas], ["present", "absent"])


class TestExtracao(unittest.TestCase):
    def setUp(self):
        pasta = Path(tempfile.mkdtemp())
        for alvo, valor in (("CACHE", pasta / "cache"), ("USO", pasta / "uso.csv")):
            patcher = mock.patch.object(cliente, alvo, valor)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.sistema = professor.montar_sistema([])

    def extrair(self, variante="direta", maximo=80):
        llm = LLMFalso()
        with mock.patch.object(professor, "MAX_TRECHO", maximo):
            saida = professor.extrair_caso("PMC1_01", TEXTO, self.sistema, variante, "falso-1", llm)
        return (*saida, llm)

    def test_trechos_sao_frases_inteiras(self):
        blocos = professor.trechos(TEXTO, 60)
        self.assertGreater(len(blocos), 1)
        self.assertEqual(TEXTO[blocos[0][0]:blocos[0][1]], "A 45-year-old man presented with fever and abdominal pain")

    def test_mencoes_passam_no_contrato_da_montagem(self):
        linhas, _, _, _ = self.extrair()
        professor.validar_contrato("PMC1_01", TEXTO, linhas)
        self.assertEqual(list(linhas[0]), professor.COLUNAS)
        self.assertTrue(all(l["fonte"] == "llm:falso-1" for l in linhas))
        self.assertIn(("chest pain", "absent"), {(l["texto"], l["polaridade"]) for l in linhas})
        self.assertEqual(len(linhas), 8)

    def test_alucinacao_registrada_e_contada(self):
        _, alucinacoes, stats, _ = self.extrair()
        self.assertEqual({(a["texto"], a["motivo"]) for a in alucinacoes}, {("vomiting", "nao_encontrado")})
        self.assertEqual(stats["alucinacoes"], len(alucinacoes))

    def test_variante_proposicoes_faz_duas_chamadas_por_trecho(self):
        _, _, stats, llm = self.extrair("proposicoes")
        self.assertEqual(stats["chamadas"], 2 * len(professor.trechos(TEXTO, 80)))
        self.assertEqual(llm.chamadas, stats["chamadas"])

    def test_resposta_que_nao_e_json_nao_derruba_o_caso(self):
        ruim = lambda *a: {"texto": "não sei", "tokens_entrada": 1, "tokens_saida": 1}  # noqa: E731
        ruim.__name__ = "ruim"
        linhas, _, stats = professor.extrair_caso("PMC1_01", TEXTO, self.sistema, provedor=ruim, modelo="x")
        self.assertEqual(linhas, [])
        self.assertEqual(stats["respostas_invalidas"], len(professor.trechos(TEXTO)))


class TestParticoes(unittest.TestCase):
    def provisorias(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return ler_divisoes(Path("/nao/existe.csv"))

    def test_provisoria_poe_o_gold_em_teste_e_respeita_o_artigo(self):
        particoes = self.provisorias()
        self.assertTrue(all(particoes[c] == "teste" for c in casos_gold()))
        por_artigo = {}
        for case_id, particao in particoes.items():
            if case_id not in casos_gold():
                self.assertEqual(por_artigo.setdefault(artigo(case_id), particao), particao)

    def test_divisoes_com_gold_fora_de_teste_falha(self):
        caminho = Path(tempfile.mkdtemp()) / "divisoes.csv"
        gold = sorted(casos_gold())[0]
        caminho.write_text(f"fonte,case_id,article_id,particao\nmulticare,{gold},{artigo(gold)},treino\n")
        with self.assertRaises(ValueError):
            ler_divisoes(caminho)

    def test_exemplos_nunca_saem_do_teste(self):
        particoes = self.provisorias()
        with self.assertRaises(ValueError):
            garantir_fora_do_teste([sorted(casos_gold())[0]], particoes)
        # Mesmo que o arquivo de menções traga um caso de teste, ele não vira exemplo.
        gold = sorted(casos_gold())[0]
        mencoes = Path(tempfile.mkdtemp()) / "m.csv"
        linhas = ["case_id,id,start,end,texto,tipo,mesh,polaridade"] + [
            f"{gold},g{k},0,1,x,Symptom,,present" for k in range(5)]
        mencoes.write_text("\n".join(linhas) + "\n")
        self.assertEqual(professor.escolher_exemplos(mencoes, professor.CASOS_PADRAO, particoes), [])

    def test_selecao_so_com_casos_disponiveis_e_limite_por_particao(self):
        particoes = {**self.provisorias(), "MAC1": "validacao", "MAC2": "validacao", "MAC3": "teste"}
        disponiveis = {"MAC1", "MAC2", "MAC3", *sorted(casos_gold())[:2]}
        escolhidos = professor.selecionar(particoes, ["teste", "validacao"], 0, disponiveis, {"validacao": 1})
        self.assertTrue(set(escolhidos) <= disponiveis)
        self.assertEqual(sum(particoes[c] == "validacao" for c in escolhidos), 1)
        self.assertEqual(sum(particoes[c] == "teste" for c in escolhidos), 3)

    def test_nenhum_e_zero_shot(self):
        with mock.patch.object(professor, "escolher_exemplos") as escolher:
            sistema = professor.sistema_padrao(self.provisorias(), "nenhum")
        escolher.assert_not_called()
        self.assertNotIn("## Examples", sistema)

    def test_padrao_sem_maccrobat_falha_em_vez_de_mudar_o_prompt(self):
        with mock.patch.object(professor, "MACCROBAT", Path("/nao/existe")):
            with self.assertRaises(FileNotFoundError):
                professor.sistema_padrao(self.provisorias(), None)

    def test_selecao_e_estavel_e_nao_repete(self):
        particoes = self.provisorias()
        a = professor.selecionar(particoes, ["teste"], 5)
        self.assertEqual(a, professor.selecionar(particoes, ["teste"], 5))
        self.assertEqual(len(a), len(set(a)))
        self.assertEqual(sum(particoes[c] == "treino" for c in a), 5)


if __name__ == "__main__":
    unittest.main()
