"""
Simula la ejecución de la regla de reconexión migrada (RECONNECTION).
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
django.setup()

from api.core.models.alerts import AlertRule, AlertTrigger
from api.core.models.catchment_points import CatchmentPoint
from api.cronjobs.alerts.alert_engine import _evaluate_rule, _cooldown_passed
from api.cronjobs.alerts.alert_dispatcher import _build_message
from datetime import datetime
import pytz

chile = pytz.timezone("America/Santiago")
now = datetime.now(chile)

rule = AlertRule.objects.get(id=10)
print(f"=== SIMULACION ALERTA: {rule.name} ===")
print(f"Target: {rule.target_type}")
print(f"Cooldown: {rule.cooldown_minutes} min")
print()

cooldown_ok = _cooldown_passed(rule, now)
print(f"Cooldown pasado: {cooldown_ok}")
print()

results = _evaluate_rule(rule, now)
triggered = [r for r in results if r[0]]
print(f"Puntos evaluados: {len(results)} | Disparados: {len(triggered)}")
print()

for i, (should_trigger, current_days, previous_days, interaction, point_id) in enumerate(triggered[:10], 1):
    pt = CatchmentPoint.objects.get(id=point_id)
    print(f"--- Mensaje {i}/{len(triggered)} ---")
    print(f"Punto: {pt.title}")
    print(f"Estado anterior: {previous_days} dias desconectado → Actual: {current_days} dias")
    trigger = AlertTrigger(
        alert_rule=rule,
        point_catchment=pt,
        triggered_at=now,
        value_at_trigger=current_days,
        threshold_breached=previous_days,
    )
    msg = _build_message(trigger)
    print(msg)
    print()

if len(triggered) > 10:
    print(f"... y {len(triggered)-10} mensajes mas (total {len(triggered)})")
