"""
DATA INTEGRITY CHECK
====================
Cronjob que verifica la integridad de los datos cada hora.
Detecta si hubo pérdida significativa de datos y envía alertas.

Funcionamiento:
1. Guarda un checkpoint del conteo de registros cada hora
2. Compara con el checkpoint anterior
3. Si hay una disminución > 10%, envía alerta por email
4. Si la DB tiene menos de un umbral mínimo esperado, alerta crítica

Configuración en settings.py CRONJOBS:
    ("0 * * * *", "api.cronjobs.data_integrity_check.run", ">> /tmp/smarthydro/integrity.log 2>&1"),
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Setup logging
logger = logging.getLogger(__name__)

# Archivo de checkpoint
CHECKPOINT_FILE = "/tmp/smarthydro/data_integrity_checkpoint.json"
LOG_FILE = "/tmp/smarthydro/integrity.log"

# Umbral mínimo de registros esperados (ajustar según histórico)
MIN_EXPECTED_RECORDS = 1_500_000  # 1.5 millones mínimo
ALERT_THRESHOLD_PERCENT = 10  # Alertar si hay disminución > 10%


def log(msg):
    """Log con timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def get_current_stats():
    """Obtener estadísticas actuales de la DB"""
    import django
    django.setup()

    from api.core.models import InteractionDetail, CatchmentPoint
    from django.db import connection
    from django.db.models import Min, Max

    try:
        total_records = InteractionDetail.objects.count()
        total_points = CatchmentPoint.objects.count()

        # Rango de fechas
        date_range = InteractionDetail.objects.aggregate(
            min_date=Min('created'),
            max_date=Max('created')
        )

        # Última hora de datos
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_records = InteractionDetail.objects.filter(
            created__gte=one_hour_ago
        ).count()

        return {
            "timestamp": datetime.now().isoformat(),
            "total_records": total_records,
            "total_points": total_points,
            "min_date": str(date_range['min_date']) if date_range['min_date'] else None,
            "max_date": str(date_range['max_date']) if date_range['max_date'] else None,
            "records_last_hour": recent_records,
        }
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {e}")
        return None


def load_checkpoint():
    """Cargar checkpoint anterior"""
    try:
        if Path(CHECKPOINT_FILE).exists():
            with open(CHECKPOINT_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error cargando checkpoint: {e}")
    return None


def save_checkpoint(stats):
    """Guardar checkpoint actual"""
    try:
        # Asegurar directorio existe
        Path(CHECKPOINT_FILE).parent.mkdir(parents=True, exist_ok=True)

        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump(stats, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error guardando checkpoint: {e}")
        return False


def send_alert(subject, message):
    """Enviar alerta por email"""
    try:
        import django
        django.setup()

        from django.core.mail import send_mail
        from django.conf import settings

        send_mail(
            subject=f"[ALERTA SmartHydro] {subject}",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.CONTACT_EMAIL],
            fail_silently=True,
        )
        log(f"📧 Alerta enviada: {subject}")
        return True
    except Exception as e:
        logger.error(f"Error enviando alerta: {e}")
        return False


def check_integrity():
    """Verificar integridad de datos"""
    log("=" * 50)
    log("VERIFICACIÓN DE INTEGRIDAD DE DATOS")
    log("=" * 50)

    # Obtener estadísticas actuales
    current = get_current_stats()
    if not current:
        log("❌ No se pudieron obtener estadísticas actuales")
        return False

    log(f"📊 Registros actuales: {current['total_records']:,}")
    log(f"📊 Puntos: {current['total_points']}")
    log(f"📊 Última fecha: {current['max_date']}")
    log(f"📊 Registros última hora: {current['records_last_hour']}")

    # Cargar checkpoint anterior
    previous = load_checkpoint()

    alerts = []

    # Verificar umbral mínimo
    if current['total_records'] < MIN_EXPECTED_RECORDS:
        alert_msg = (
            f"ALERTA CRÍTICA: La base de datos tiene menos registros de lo esperado.\n\n"
            f"Registros actuales: {current['total_records']:,}\n"
            f"Mínimo esperado: {MIN_EXPECTED_RECORDS:,}\n\n"
            f"Esto puede indicar pérdida de datos. Por favor verificar inmediatamente."
        )
        alerts.append(("DB con pocos registros", alert_msg))
        log(f"⚠️ ALERTA: {current['total_records']:,} < {MIN_EXPECTED_RECORDS:,} mínimo")

    # Comparar con checkpoint anterior
    if previous:
        prev_records = previous.get('total_records', 0)
        diff = current['total_records'] - prev_records
        diff_percent = (diff / prev_records * 100) if prev_records > 0 else 0

        log(f"📈 Diferencia vs checkpoint: {diff:+,} ({diff_percent:+.1f}%)")

        # Si hay disminución significativa
        if diff_percent < -ALERT_THRESHOLD_PERCENT:
            alert_msg = (
                f"ALERTA: Disminución significativa de registros detectada.\n\n"
                f"Registros anterior: {prev_records:,}\n"
                f"Registros actual: {current['total_records']:,}\n"
                f"Diferencia: {diff:,} ({diff_percent:.1f}%)\n\n"
                f"Timestamp anterior: {previous.get('timestamp')}\n"
                f"Timestamp actual: {current['timestamp']}\n\n"
                f"Esto puede indicar pérdida de datos o restauración de backup antiguo."
            )
            alerts.append(("Disminución de registros", alert_msg))
            log(f"⚠️ ALERTA: Disminución de {abs(diff_percent):.1f}%")
    else:
        log("ℹ️ Sin checkpoint anterior (primera ejecución)")

    # Enviar alertas
    for subject, message in alerts:
        send_alert(subject, message)

    # Guardar nuevo checkpoint
    if save_checkpoint(current):
        log("✅ Checkpoint guardado")

    if alerts:
        log(f"⚠️ {len(alerts)} alertas generadas")
        return False
    else:
        log("✅ Integridad OK")
        return True


def run():
    """Punto de entrada para cronjob"""
    try:
        check_integrity()
    except Exception as e:
        log(f"❌ Error en verificación de integridad: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Para testing manual
    import sys
    sys.path.insert(0, '/app')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
    run()
