"""
Tests para helpers de audit_dga_global (scripts/).

Cubre los falsos positivos detectados el 2026-10-07:
- Hora inexistente por cambio de horario (6-sep 00:00 CLT): no debe contar como laguna.
- Voucher SMA (UUID de IdVerificacion) no es comprobante DGA.
"""
import importlib.util
import os
import unittest
from datetime import datetime

_AUDIT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts", "audit_dga_global.py"
)


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("audit_dga_global_under_test", _AUDIT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


audit = _load_audit_module()


class DstSlotTests(unittest.TestCase):
    def test_spring_forward_hour_is_not_valid(self):
        """6-sep-2026 00:00 CLT no existe (salto de horario)."""
        self.assertFalse(audit.is_local_time_valid(datetime(2026, 9, 6, 0, 0, 0)))

    def test_hours_around_jump_are_valid(self):
        self.assertTrue(audit.is_local_time_valid(datetime(2026, 9, 5, 23, 0, 0)))
        self.assertTrue(audit.is_local_time_valid(datetime(2026, 9, 6, 1, 0, 0)))

    def test_slot_keys_skips_nonexistent_local_time(self):
        start = datetime(2026, 9, 5, 0, 0, 0)
        end = datetime(2026, 9, 7, 0, 0, 0)
        slots = audit.slot_keys("MEDIO", start, end, 60)
        self.assertIn(datetime(2026, 9, 5, 0, 0, 0), slots)
        self.assertNotIn(datetime(2026, 9, 6, 0, 0, 0), slots)

    def test_slot_keys_ignores_current_in_progress_is_handled_by_audit(self):
        """slot_keys solo genera horas < fin de ventana (recorte por ventana)."""
        start = datetime(2026, 10, 7, 0, 0, 0)
        end = datetime(2026, 10, 7, 13, 30, 0)
        slots = audit.slot_keys("MEDIO", start, end, 60)
        self.assertEqual(slots, {datetime(2026, 10, 7, 0, 0, 0)})


class VoucherClassificationTests(unittest.TestCase):
    def test_real_dga_voucher(self):
        self.assertTrue(audit.has_dga_voucher("KNQPVMkTYkbqScx1VtYijwSpmafFFM0G"))

    def test_sma_uuid_is_not_dga_voucher(self):
        self.assertFalse(
            audit.has_dga_voucher("123e4567-e89b-12d3-a456-426614174000")
        )

    def test_placeholders_and_empty(self):
        self.assertFalse(audit.has_dga_voucher(None))
        self.assertFalse(audit.has_dga_voucher(""))
        self.assertFalse(audit.has_dga_voucher("None"))
        self.assertFalse(audit.has_dga_voucher("No se pudo obtener el comprobante"))


if __name__ == "__main__":
    unittest.main()
