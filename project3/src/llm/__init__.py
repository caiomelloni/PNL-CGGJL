"""Cliente LLM comum (Frente B): toda chamada de LLM do Projeto 3 passa por aqui."""
from .cliente import PRECOS, RecusaLLM, Resposta, chamar, ler_json

__all__ = ["PRECOS", "RecusaLLM", "Resposta", "chamar", "ler_json"]
