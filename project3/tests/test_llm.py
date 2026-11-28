"""Cliente LLM com um provedor falso: nenhum teste acessa a rede."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from project3.src.llm import cliente


class ProvedorFalso:
    __name__ = "falso"

    def __init__(self, texto='{"ok": true}'):
        self.texto, self.chamadas = texto, []

    def __call__(self, prompt, sistema, modelo, temperatura, json_):
        self.chamadas.append((prompt, sistema, modelo, temperatura, json_))
        return {"texto": self.texto, "tokens_entrada": 100, "tokens_saida": 20, "custo_usd": 0.5}


class TestChamar(unittest.TestCase):
    def setUp(self):
        pasta = Path(tempfile.mkdtemp())
        self.uso = pasta / "uso.csv"
        for alvo, valor in (("CACHE", pasta / "cache"), ("USO", self.uso)):
            patcher = mock.patch.object(cliente, alvo, valor)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_segunda_chamada_igual_vem_do_cache(self):
        falso = ProvedorFalso()
        primeira = cliente.chamar("oi", modelo="m", provedor=falso)
        segunda = cliente.chamar("oi", modelo="m", provedor=falso)
        self.assertEqual(len(falso.chamadas), 1)
        self.assertFalse(primeira.do_cache)
        self.assertTrue(segunda.do_cache)
        self.assertEqual((segunda.texto, segunda.tokens_entrada, segunda.custo_usd), ('{"ok": true}', 100, 0.5))

    def test_mudar_modelo_sistema_ou_temperatura_muda_a_chave(self):
        falso = ProvedorFalso()
        cliente.chamar("oi", modelo="m", provedor=falso)
        cliente.chamar("oi", modelo="outro", provedor=falso)
        cliente.chamar("oi", modelo="m", sistema="s", provedor=falso)
        cliente.chamar("oi", modelo="m", temperatura=0.7, provedor=falso)
        self.assertEqual(len(falso.chamadas), 4)

    def test_json_acrescenta_a_instrucao_ao_sistema(self):
        falso = ProvedorFalso()
        cliente.chamar("oi", sistema="s", modelo="m", json=True, provedor=falso)
        _, sistema, _, _, json_ = falso.chamadas[0]
        self.assertTrue(sistema.startswith("s") and sistema.endswith(cliente.INSTRUCAO_JSON))
        self.assertTrue(json_)

    def test_registra_cada_chamada_no_uso(self):
        falso = ProvedorFalso()
        cliente.chamar("oi", modelo="m", provedor=falso)
        cliente.chamar("oi", modelo="m", provedor=falso)
        with self.uso.open(encoding="utf-8") as handle:
            linhas = list(csv.DictReader(handle))
        self.assertEqual([l["do_cache"] for l in linhas], ["0", "1"])
        self.assertEqual(linhas[0]["provedor"], "falso")

    def test_modelo_padrao_vem_do_ambiente(self):
        falso = ProvedorFalso()
        with mock.patch.dict("os.environ", {"P3_LLM_MODELO": "do-ambiente"}):
            self.assertEqual(cliente.chamar("oi", provedor=falso).modelo, "do-ambiente")

    def test_provedor_desconhecido_falha(self):
        with self.assertRaises(ValueError):
            cliente.chamar("oi", modelo="m", provedor="inexistente")


class TestClaudeCli(unittest.TestCase):
    """`claude -p` simulado: nenhum teste executa a CLI de verdade."""

    def rodar(self, saida: dict, returncode=0):
        processo = mock.Mock(stdout=json.dumps(saida), stderr="", returncode=returncode)
        with mock.patch("subprocess.run", return_value=processo) as run, \
                mock.patch.dict("os.environ", {"P3_LLM_CLI": "/bin/claude"}):
            gerado = cliente.claude_cli("trecho", "sistema", "claude-sonnet-5-5", 0.0, True)
        return gerado, run.call_args

    def test_monta_o_comando_e_le_tokens_e_custo(self):
        gerado, chamada = self.rodar({"subtype": "success", "is_error": False, "result": '{"mencoes": []}',
                                      "total_cost_usd": 0.02, "usage": {"input_tokens": 2, "output_tokens": 9,
                                      "cache_creation_input_tokens": 4000, "cache_read_input_tokens": 300}})
        self.assertEqual(gerado, {"texto": '{"mencoes": []}', "tokens_entrada": 4302, "tokens_saida": 9,
                                  "custo_usd": 0.02})
        comando = chamada.args[0]
        self.assertEqual(comando[:2], ["/bin/claude", "-p"])
        self.assertEqual(comando[comando.index("--model") + 1], "claude-sonnet-5-5")
        self.assertEqual(comando[comando.index("--tools") + 1], "")
        self.assertEqual(comando[comando.index("--system-prompt") + 1], "sistema")
        self.assertEqual(chamada.kwargs["input"], "trecho")
        self.assertNotEqual(Path(chamada.kwargs["cwd"]).resolve(), Path.cwd().resolve())

    def test_erro_da_cli_para_a_execucao(self):
        with self.assertRaises(RuntimeError) as erro:
            self.rodar({"subtype": "error_during_execution", "is_error": True, "result": "limite"})
        self.assertNotIsInstance(erro.exception, cliente.RecusaLLM)

    def test_falha_de_rede_tenta_de_novo_e_depois_desiste(self):
        erro = mock.Mock(stdout=json.dumps({"subtype": "success", "is_error": False,
                                            "result": "API Error: Can't reach the API server"}), stderr="", returncode=0)
        ok = mock.Mock(stdout=json.dumps({"subtype": "success", "is_error": False, "result": "{}",
                                          "usage": {}, "total_cost_usd": 0}), stderr="", returncode=0)
        with mock.patch.object(cliente, "ESPERAS_CLI", (0, 0)), mock.patch.dict("os.environ", {"P3_LLM_CLI": "/bin/claude"}):
            with mock.patch("subprocess.run", side_effect=[erro, ok]) as run:
                self.assertEqual(cliente.claude_cli("t", "", "m", 0.0, True)["texto"], "{}")
            self.assertEqual(run.call_count, 2)
            with mock.patch("subprocess.run", return_value=erro) as run, self.assertRaises(RuntimeError):
                cliente.claude_cli("t", "", "m", 0.0, True)
            self.assertEqual(run.call_count, 3)

    def test_recusa_vira_recusa_llm(self):
        with self.assertRaises(cliente.RecusaLLM):
            self.rodar({"subtype": "success", "is_error": False, "stop_reason": "refusal", "result": ""})

    def test_modelo_padrao_e_o_sonnet(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(cliente.modelo_padrao("claude_cli"), "claude-sonnet-5-5")


class TestAuxiliares(unittest.TestCase):
    def test_ler_json_aceita_cercas(self):
        self.assertEqual(cliente.ler_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(cliente.ler_json('{"a": 1}'), {"a": 1})

    def test_ler_json_fica_com_a_ultima_versao(self):
        texto = '{"a": 1}\n\nWait, corrected version:\n\n{"a": 2, "b": {"c": 3}}'
        self.assertEqual(cliente.ler_json(texto), {"a": 2, "b": {"c": 3}})
        with self.assertRaises(ValueError):
            cliente.ler_json("não sei")

    def test_custo_usa_a_tabela_e_zero_fora_dela(self):
        self.assertAlmostEqual(cliente.custo("claude-haiku-5-5", 1_000_000, 1_000_000), 0.60)
        self.assertEqual(cliente.custo("modelo-local", 10**6, 10**6), 0.0)


if __name__ == "__main__":
    unittest.main()
