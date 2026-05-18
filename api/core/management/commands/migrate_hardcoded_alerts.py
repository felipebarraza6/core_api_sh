"""
Migra las alertas hardcodeadas de google_chat.py al subsistema configurable.

Crea AlertRule + AlertChannel equivalentes a:
- check_and_notify_disconnection (desconexión de puntos)
- check_and_notify_reconnection (reconexión de puntos)

Uso:
    python manage.py migrate_hardcoded_alerts --dry-run
    python manage.py migrate_hardcoded_alerts
"""

from django.core.management.base import BaseCommand

from django.conf import settings

from api.core.models.alerts import AlertRule, AlertChannel


class Command(BaseCommand):
    help = "Migra alertas hardcodeadas de google_chat.py a AlertRule configurables"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simula sin crear nada en la BD",
        )

    def _create_rule(self, dry_run, name, description, target_type, extra_fields):
        verb = self.stdout.write if not dry_run else self.stdout.write
        existing = AlertRule.objects.filter(name=name).first()
        if existing:
            verb(self.style.WARNING(f"Regla '{name}' ya existe (id={existing.id}). Saltando."))
            return existing

        verb(self.style.SUCCESS(f"Creando regla: {name}"))
        if dry_run:
            return None

        rule = AlertRule.objects.create(
            name=name,
            description=description,
            severity="ALERT",
            target_type=target_type,
            check_frequency_minutes=10,
            cooldown_minutes=1440,
            is_active=True,
            **extra_fields,
        )
        channel = AlertChannel.objects.create(
            alert_rule=rule,
            channel_type="GOOGLE_CHAT",
            destination=settings.GOOGLE_CHAT_WEBHOOK_URL or "",
            is_active=True,
        )
        verb(self.style.SUCCESS(f"  → AlertRule creada: id={rule.id}"))
        verb(self.style.SUCCESS(f"  → AlertChannel GOOGLE_CHAT creado: id={channel.id}"))
        return rule

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        verb = self.stdout.write if not dry_run else self.stdout.write

        verb(self.style.NOTICE("=" * 60))
        verb(self.style.NOTICE("Migración de alertas hardcodeadas"))
        verb(self.style.NOTICE("=" * 60))

        if dry_run:
            verb(self.style.WARNING("[DRY-RUN] No se crearán objetos"))

        # 1. Desconexión
        self._create_rule(
            dry_run=dry_run,
            name="🔴 Desconexión de puntos",
            description=(
                "Evalúa todos los puntos activos cada 10 min. Cooldown 24h. "
                "Ignora puntos desconectados hace más de 3 días (anti-spam)."
            ),
            target_type="DISCONNECTION",
            extra_fields={"max_disconnection_days": 3},
        )

        # 2. Reconexión
        self._create_rule(
            dry_run=dry_run,
            name="🟢 Reconexión de puntos",
            description=(
                "Detecta cuando un punto pasa de desconectado a conectado. "
                "Cooldown 24h para evitar alertas repetidas."
            ),
            target_type="RECONNECTION",
            extra_fields={},
        )

        # 3. Error de procesamiento
        self._create_rule(
            dry_run=dry_run,
            name="⚠️ Error de procesamiento",
            description=(
                "Detecta errores de procesamiento en telemetría (is_error=True). "
                "Evalúa cada 10 min. Cooldown 24h."
            ),
            target_type="PROCESSING_ERROR",
            extra_fields={},
        )

        verb("")
        verb(self.style.NOTICE("Alertas identificadas pero NO migradas:"))
        verb(self.style.NOTICE("  • Reportes DGA horarios → Requiere SCHEDULED_REPORT + WEBHOOK_DGA"))
        verb("")
        verb(self.style.NOTICE("Próximos pasos:"))
        verb(self.style.NOTICE("  1. Validar reglas en paralelo al legacy."))
        verb(self.style.NOTICE("  2. Desactivar google_chat.py::check_and_notify_error."))

        verb("")
        if dry_run:
            verb(self.style.SUCCESS("Dry-run completado. Sin cambios en la BD."))
        else:
            verb(self.style.SUCCESS("Migración completada."))
