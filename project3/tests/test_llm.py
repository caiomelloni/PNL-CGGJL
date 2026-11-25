"""Cliente LLM com um provedor falso: nenhum teste acessa a rede."""
import csv
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


class TestAuxiliares(unittest.TestCase):
    def test_ler_json_aceita_cercas(self):
        self.assertEqual(cliente.ler_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(cliente.ler_json('{"a": 1}'), {"a": 1})

    def test_custo_usa_a_tabela_e_zero_fora_dela(self):
        self.assertAlmostEqual(cliente.custo("claude-haiku-5-5", 1_000_000, 1_000_000), 0.60)
        self.assertEqual(cliente.custo("modelo-local", 10**6, 10**6), 0.0)


if __name__ == "__main__":
    unittest.main()
