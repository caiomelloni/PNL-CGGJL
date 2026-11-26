"""Motor de diagnóstico diferencial do Projeto 3."""
from .dados import montar_consulta
from .motor import Motor, Sugestao, sugerir

__all__ = ["Motor", "Sugestao", "montar_consulta", "sugerir"]
