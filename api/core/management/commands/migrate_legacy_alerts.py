"""
Comando de management para migrar alertas legacy (NotificationsCatchment)
al nuevo subsistema de alertas (AlertRule + AlertChannel).

Uso:
    python manage.py migrate_legacy_alerts --dry-run
    python manage.py migrate_legacy_alerts --deactivate-legacy
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from api.core.models import NotificationsCatchment
from api.core.models.alerts import AlertRule, AlertChannel


class Command(BaseCommand):
    help = "Migra alertas umbral legacy al nuevo subsistema de alertas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Si se pasa, solo muestra qué haría sin guardar en BD.",
        )
        parser.add_argument(
            "--deactivate-legacy",
            action="store_true",
            help="Desactiva la notificación legacy tras migrarla.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        deactivate_legacy = options["deactivate_legacy"]

        legacies = (
            NotificationsCatchment.objects
            .filter(
                type_alert__in=["MAX", "MIN", "EQUALS"],
                point_catchment__isnull=False,
                is_active=True,
            )
            .exclude(type_variable="TODOS")
        )

        self.stdout.write(
            self.style.NOTICE(
                f"[migrate_legacy_alerts] Alertas legacy candidatas: {legacies.count()} | "
                f"dry_run={dry_run} | deactivate_legacy={deactivate_legacy}"
            )
        )

        created_rules = 0
        created_channels = 0
        skipped = 0

        for legacy in legacies:
            try:
                result = self._migrate_one(legacy, dry_run, deactivate_legacy)
                if result:
                    created_rules += 1
                else:
                    skipped += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  Error migrando notificación {legacy.id}: {e}")
                )
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"[migrate_legacy_alerts] Fin | Reglas creadas={created_rules} | "
                f"Canales creados={created_channels} | Saltadas={skipped}"
            )
        )

    def _migrate_one(self, legacy: NotificationsCatchment, dry_run: bool, deactivate_legacy: bool) -> bool:
        # Mapeo de tipo de alerta
        alert_type_map = {
            "MAX": "THRESHOLD_MAX",
            "MIN": "THRESHOLD_MIN",
            "EQUALS": "THRESHOLD_MAX",  # El nuevo sistema no tiene EQUALS; usamos MAX
        }
        target_type = alert_type_map.get(legacy.type_alert)
        if not target_type:
            self.stdout.write(f"  Saltando {legacy.id}: tipo_alert={legacy.type_alert} no soportado")
            return False

        # Variable
        variable_type = legacy.type_variable
        if not variable_type:
            self.stdout.write(f"  Saltando {legacy.id}: sin type_variable")
            return False

        # Umbral
        try:
            threshold = Decimal(str(legacy.value))
        except Exception:
            self.stdout.write(f"  Saltando {legacy.id}: value={legacy.value} no convertible a Decimal")
            return False

        # Frecuencia según severidad legacy
        freq_map = {
            "CRITICAL": 1,
            "ALERT": 5,
            "WARNING": 10,
            "INFO": 60,
        }
        frequency = freq_map.get(legacy.type_notification, 10)

        self.stdout.write(
            f"  Migrando notificación {legacy.id}: punto={legacy.point_catchment_id} "
            f"var={variable_type} tipo={target_type} umbral={threshold} freq={frequency}"
        )

        if dry_run:
            self.stdout.write(f"    DRY-RUN: No se crea nada.")
            return True

        # Crear AlertRule
        rule = AlertRule.objects.create(
            name=legacy.title or f"Regla migrada #{legacy.id}",
            point_catchment=legacy.point_catchment,
            target_type=target_type,
            variable_type=variable_type,
            threshold_value=threshold,
            check_frequency_minutes=frequency,
            cooldown_minutes=60,
            is_active=legacy.is_active,
            start_date=legacy.start_date,
            end_date=legacy.end_date,
        )

        # Crear AlertChannel por cada email
        emails = legacy.emails or []
        if isinstance(emails, str):
            emails = [emails]
        if emails:
            dest = ", ".join(str(e).strip() for e in emails if str(e).strip())
            if dest:
                AlertChannel.objects.create(
                    alert_rule=rule,
                    channel_type="EMAIL",
                    destination=dest,
                    is_active=True,
                )
                self.stdout.write(f"    Canal EMAIL creado: {dest}")

        if deactivate_legacy:
            legacy.is_active = False
            legacy.save(update_fields=["is_active"])
            self.stdout.write(f"    Legacy desactivada.")

        return True
