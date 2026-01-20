import unittest
from datetime import datetime
from api.telemetry.ingestion.controllers.processing.utils import evaluate_dynamic_formula

class TestDynamicEvaluator(unittest.TestCase):
    def test_basic_math(self):
        formula = "10 + 5 * 2"
        context = {}
        self.assertEqual(evaluate_dynamic_formula(formula, context), 20.0)

    def test_variable_replacement(self):
        formula = "{v1} + {v2}"
        context = {"v1": 100, "v2": 50}
        self.assertEqual(evaluate_dynamic_formula(formula, context), 150.0)

    def test_complex_formula(self):
        formula = "({nivel_raw} - {offset}) * {factor}"
        context = {
            "nivel_raw": 10.5,
            "offset": 0.5,
            "factor": 2
        }
        self.assertEqual(evaluate_dynamic_formula(formula, context), 20.0)

    def test_missing_variable(self):
        # Missing variables should fallback to 0
        formula = "{existent} + {missing}"
        context = {"existent": 10}
        self.assertEqual(evaluate_dynamic_formula(formula, context), 10.0)

    def test_division_by_zero(self):
        formula = "10 / 0"
        context = {}
        self.assertEqual(evaluate_dynamic_formula(formula, context), 0.0)

    def test_invalid_syntax(self):
        formula = "10 ++ 5"
        context = {}
        self.assertEqual(evaluate_dynamic_formula(formula, context), 0.0)

    def test_insecure_formula(self):
        # Should be caught by regex and return 0
        formula = "__import__('os').system('ls')"
        context = {}
        self.assertEqual(evaluate_dynamic_formula(formula, context), 0.0)

    def test_nested_replacement(self):
        # tokens are sorted by length descending so {v11} is replaced before {v1}
        formula = "{v11} + {v1}"
        context = {"v1": 1, "v11": 11}
        self.assertEqual(evaluate_dynamic_formula(formula, context), 12.0)

if __name__ == "__main__":
    unittest.main()
