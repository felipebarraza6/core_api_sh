"""
Simula la ejecución de la regla de desconexión migrada (DISCONNECTION).
Muestra qué puntos dispararían y qué mensajes se enviarían.
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

rule = AlertRule.objects.get(id=9)
print(f"=== SIMULACION ALERTA: {rule.name} ===")
print(f"Target: {rule.target_type}")
print(f"Frecuencia: {rule.check_frequency_minutes} min")
print(f"Cooldown: {rule.cooldown_minutes} min")
print(f"Canales activos: {rule.channels.filter(is_active=True).count()}")
print()

# Verificar cooldown
cooldown_ok = _cooldown_passed(rule, now)
print(f"Cooldown pasado: {cooldown_ok}")
if not cooldown_ok:
    last = AlertTrigger.objects.filter(alert_rule=rule).order_by("-triggered_at").first()
    print(f"  Ultimo trigger: {last.triggered_at}")
    print()

results = _evaluate_rule(rule, now)
triggered = [r for r in results if r[0]]
print(f"Puntos evaluados: {len(results)} | Disparados: {len(triggered)}")
print()

# Simular mensajes
for i, (should_trigger, value, threshold, interaction, point_id) in enumerate(triggered[:5], 1):
    pt = CatchmentPoint.objects.get(id=point_id)
    print(f"--- Mensaje {i}/{len(triggered)} ---")
    print(f"Punto: {pt.title} (dias sin conexion: {value})")

    # Simular trigger temporal para construir mensaje
    trigger = AlertTrigger(
        alert_rule=rule,
        point_catchment=pt,
        triggered_at=now,
        value_at_trigger=value,
        threshold_breached=threshold,
    )
    msg = _build_message(trigger)
    print(msg)
    print()

if len(triggered) > 5:
    print(f"... y {len(triggered)-5} mensajes mas (total {len(triggered)})")
