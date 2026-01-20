"""
Motor de Procesamiento Dinámico de Telemetría

Reemplaza los procesadores específicos (flow.py, total.py, nivel.py)
con un sistema unificado basado en fórmulas configurables.
"""

from .formula_engine import FormulaEngine

__all__ = ['FormulaEngine']
