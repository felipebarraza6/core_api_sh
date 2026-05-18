"""
Nuevo subsistema de alertas — Fase 2 del refactor de notificaciones.

Estos modelos corren en PARALELO al monolito NotificationsCatchment legacy.
No se toca el legacy hasta la Fase 4 (migración gradual).
"""

import re

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, EmailValidator
from django.db import models

from .catchment_points import CatchmentPoint, Variable
from .utils import ModelApi


class AlertRule(ModelApi):
    """
    Regla de alerta configurable por usuario o administrador.
    Puede ser umbral, ausencia de datos, tasa de cambio, desviación, o reporte programado.
    """

    TARGET_TYPE_CHOICES = [
        ("THRESHOLD_MAX", "Umbral máximo"),
        ("THRESHOLD_MIN", "Umbral mínimo"),
        ("NO_DATA", "Sin datos por X tiempo"),
        ("DISCONNECTION", "Punto desconectado"),
        ("RECONNECTION", "Punto reconectado"),
        ("PROCESSING_ERROR", "Error de procesamiento"),
        ("RATE_OF_CHANGE", "Tasa de cambio"),
        ("DEVIATION", "Desviación estadística"),
        ("SCHEDULED_REPORT", "Reporte programado"),
    ]

    SEVERITY_CHOICES = [
        ("INFO", "Informativo"),
        ("WARNING", "Advertencia"),
        ("ALERT", "Alerta"),
        ("CRITICAL", "Crítico"),
    ]

    name = models.CharField(max_length=300, verbose_name="Nombre de la regla")
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default="WARNING",
        verbose_name="Severidad",
        db_index=True,
        help_text="Determina la prioridad visual y la frecuencia sugerida.",
    )
    point_catchment = models.ForeignKey(
        CatchmentPoint,
        related_name="alert_rules",
        on_delete=models.CASCADE,
        verbose_name="Punto de captación",
        null=True,
        blank=True,
        db_index=True,
        help_text="Si se deja vacío, la regla aplica globalmente (ej. alerta de administrador).",
    )

    target_type = models.CharField(
        max_length=50,
        choices=TARGET_TYPE_CHOICES,
        verbose_name="Tipo de alerta",
    )

    variable_type = models.CharField(
        max_length=50,
        verbose_name="Variable a monitorear",
        blank=True,
        null=True,
        help_text="Requerido para THRESHOLD_MAX, THRESHOLD_MIN, RATE_OF_CHANGE, DEVIATION. "
                  "Valores conocidos: CAUDAL, NIVEL, TOTALIZADO, CAUDAL_PROMEDIO. "
                  "Ignorado para NO_DATA y SCHEDULED_REPORT.",
    )

    # Umbral numérico
    threshold_value = models.DecimalField(
        max_digits=15, decimal_places=4,
        blank=True, null=True,
        verbose_name="Valor umbral",
    )

    # Ausencia de datos
    no_data_minutes = models.IntegerField(
        blank=True, null=True,
        verbose_name="Minutos sin datos",
        help_text="Para alertas de tipo NO_DATA: tiempo máximo sin recibir datos.",
    )
    max_disconnection_days = models.IntegerField(
        blank=True, null=True,
        verbose_name="Máximo días desconectado",
        help_text="Para DISCONNECTION: ignorar puntos desconectados hace más de N días (evita spam). Por defecto 3.",
    )

    # Tasa de cambio
    rate_change_value = models.DecimalField(
        max_digits=15, decimal_places=4,
        blank=True, null=True,
        verbose_name="Valor de tasa de cambio",
    )
    rate_change_window = models.IntegerField(
        blank=True, null=True,
        verbose_name="Ventana de tiempo (minutos)",
        help_text="Para RATE_OF_CHANGE: intervalo en minutos para comparar.",
    )

    # Frecuencia de revisión y cooldown
    check_frequency_minutes = models.IntegerField(
        default=10,
        verbose_name="Revisar cada (minutos)",
        help_text="Cada cuántos minutos se evalúa esta regla. Ej: 1 para críticas, 60 para reportes.",
    )
    cooldown_minutes = models.IntegerField(
        default=60,
        verbose_name="Cooldown (minutos)",
        help_text="Tiempo mínimo entre disparos consecutivos de la misma regla.",
    )
    is_active = models.BooleanField(
        default=True, verbose_name="Activa", db_index=True,
    )
    start_date = models.DateField(
        blank=True, null=True, verbose_name="Fecha inicio vigencia",
    )
    end_date = models.DateField(
        blank=True, null=True, verbose_name="Fecha fin vigencia",
    )

    # Reportes programados (solo para SCHEDULED_REPORT)
    report_schedule = models.CharField(
        max_length=50,
        blank=True, null=True,
        choices=[
            ("DAILY", "Diario"),
            ("WEEKLY", "Semanal"),
            ("MONTHLY", "Mensual"),
        ],
        verbose_name="Periodicidad del reporte",
    )
    report_hour = models.IntegerField(
        blank=True, null=True,
        verbose_name="Hora de envío (0-23)",
    )

    # Lista de puntos específicos a los que aplica esta regla.
    # Si está vacía, la regla aplica globalmente (todos los puntos activos).
    points = models.ManyToManyField(
        CatchmentPoint,
        blank=True,
        related_name="alert_rules_m2m",
        verbose_name="Puntos aplicables",
        help_text="Si se deja vacío, la regla evalúa TODOS los puntos.",
    )

    description = models.TextField(
        blank=True, null=True,
        verbose_name="Descripción / Notas",
        help_text="Documenta el propósito de esta regla. Visible solo en admin.",
    )

    def clean(self):
        errors = {}

        # Frecuencias
        if self.check_frequency_minutes is not None and self.check_frequency_minutes <= 0:
            errors["check_frequency_minutes"] = "La frecuencia debe ser mayor a 0."
        if self.cooldown_minutes is not None and self.cooldown_minutes < 0:
            errors["cooldown_minutes"] = "El cooldown no puede ser negativo."

        # Vigencia
        if self.start_date and self.end_date and self.start_date > self.end_date:
            errors["end_date"] = "La fecha de fin no puede ser anterior a la de inicio."

        # Reporte programado
        if self.report_hour is not None and not (0 <= self.report_hour <= 23):
            errors["report_hour"] = "La hora debe estar entre 0 y 23."

        # Validaciones según target_type
        target = self.target_type

        if target in ("THRESHOLD_MAX", "THRESHOLD_MIN"):
            if not self.variable_type:
                errors["variable_type"] = "Requerido para alertas de umbral."
            if self.threshold_value is None:
                errors["threshold_value"] = "Requerido para alertas de umbral."

        elif target == "NO_DATA":
            if self.no_data_minutes is None or self.no_data_minutes <= 0:
                errors["no_data_minutes"] = "Debe especificar minutos sin datos (> 0)."

        elif target == "DISCONNECTION":
            # No requiere campos adicionales; evalúa days_not_conection del último InteractionDetail
            if self.max_disconnection_days is not None and self.max_disconnection_days <= 0:
                errors["max_disconnection_days"] = "Debe ser mayor a 0 o dejar en blanco."

        elif target == "RECONNECTION":
            # No requiere campos adicionales; evalúa transición de desconectado a conectado
            pass

        elif target == "PROCESSING_ERROR":
            # No requiere campos adicionales; evalúa InteractionDetail.is_error en ventana reciente
            pass

        elif target == "RATE_OF_CHANGE":
            if self.point_catchment_id is None:
                errors["point_catchment"] = "Requerido para alertas de tasa de cambio."
            if not self.variable_type:
                errors["variable_type"] = "Requerido para alertas de tasa de cambio."
            if self.rate_change_value is None:
                errors["rate_change_value"] = "Requerido para alertas de tasa de cambio."
            if self.rate_change_window is None or self.rate_change_window <= 0:
                errors["rate_change_window"] = "Debe especificar ventana de tiempo (> 0)."

        elif target == "DEVIATION":
            if self.point_catchment_id is None:
                errors["point_catchment"] = "Requerido para alertas de desviación."
            if not self.variable_type:
                errors["variable_type"] = "Requerido para alertas de desviación."

        elif target == "SCHEDULED_REPORT":
            if not self.report_schedule:
                errors["report_schedule"] = "Requerido para reportes programados."
            if self.report_hour is None:
                errors["report_hour"] = "Requerido para reportes programados."

        # Campos que no aplican según el tipo
        if target in ("NO_DATA", "DISCONNECTION", "SCHEDULED_REPORT") and self.variable_type:
            # No es error grave, pero podríamos advertir. Por ahora lo dejamos pasar.
            pass

        if errors:
            raise ValidationError(errors)

    class Meta:
        verbose_name = "Regla de alerta"
        verbose_name_plural = "Reglas de alerta"
        indexes = [
            models.Index(fields=["point_catchment", "is_active", "target_type"]),
            models.Index(fields=["is_active", "target_type"]),
        ]

    def __str__(self):
        scope = f"Punto {self.point_catchment_id}" if self.point_catchment else "GLOBAL"
        return f"[{scope}] {self.name} ({self.target_type})"


class AlertChannel(ModelApi):
    """
    Canal de notificación vinculado a una AlertRule.
    Una regla puede tener múltiples canales (email + chat + webhook).
    """

    CHANNEL_TYPE_CHOICES = [
        ("EMAIL", "Email"),
        ("GOOGLE_CHAT", "Google Chat"),
        ("WEBHOOK", "Webhook"),
        ("SMS", "SMS"),
    ]

    alert_rule = models.ForeignKey(
        AlertRule,
        related_name="channels",
        on_delete=models.CASCADE,
        verbose_name="Regla de alerta",
    )

    channel_type = models.CharField(
        max_length=50,
        choices=CHANNEL_TYPE_CHOICES,
        verbose_name="Tipo de canal",
    )
    destination = models.CharField(
        max_length=500,
        verbose_name="Destino",
        help_text="Email, URL de webhook, o número de teléfono según el canal.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Activo")

    # Plantilla personalizada (opcional, Jinja2)
    template_override = models.TextField(
        blank=True, null=True,
        verbose_name="Plantilla personalizada",
        help_text="Si se deja vacío, se usa la plantilla por defecto del canal.",
    )

    def clean(self):
        errors = {}

        if not self.destination or not self.destination.strip():
            errors["destination"] = "El destino no puede estar vacío."
        else:
            dest = self.destination.strip()
            if self.channel_type == "WEBHOOK":
                validator = URLValidator()
                try:
                    validator(dest)
                except ValidationError:
                    errors["destination"] = "Debe ser una URL válida."
            elif self.channel_type == "EMAIL":
                validator = EmailValidator()
                # Soportar múltiples emails separados por coma
                for email in dest.split(","):
                    try:
                        validator(email.strip())
                    except ValidationError:
                        errors["destination"] = f"Email inválido: {email.strip()}"
                        break
            elif self.channel_type == "SMS":
                # Validación básica: solo dígitos, +, espacios y guiones
                if not re.match(r"^[\d\+\-\s]+", dest):
                    errors["destination"] = "Número de teléfono inválido."

        if errors:
            raise ValidationError(errors)

    class Meta:
        verbose_name = "Canal de notificación"
        verbose_name_plural = "Canales de notificación"

    def __str__(self):
        return f"{self.channel_type} → {self.destination[:40]}"


class AlertTrigger(ModelApi):
    """
    Log de cada vez que una AlertRule se dispara.
    """

    alert_rule = models.ForeignKey(
        AlertRule,
        related_name="triggers",
        on_delete=models.CASCADE,
        verbose_name="Regla",
        db_index=True,
    )
    triggered_at = models.DateTimeField(
        verbose_name="Fecha/hora del disparo",
    )
    value_at_trigger = models.DecimalField(
        max_digits=15, decimal_places=4,
        blank=True, null=True,
        verbose_name="Valor en el momento del disparo",
    )
    threshold_breached = models.DecimalField(
        max_digits=15, decimal_places=4,
        blank=True, null=True,
        verbose_name="Umbral que se rompió",
    )
    interaction_detail = models.ForeignKey(
        "core.InteractionDetail",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Registro de telemetría relacionado",
    )
    point_catchment = models.ForeignKey(
        CatchmentPoint,
        on_delete=models.CASCADE,
        null=True, blank=True,
        verbose_name="Punto que disparó",
        help_text="Para reglas globales, indica qué punto específico causó el trigger.",
    )

    notification_sent = models.BooleanField(
        default=False, verbose_name="Notificación enviada",
    )
    notification_error = models.TextField(
        blank=True, null=True, verbose_name="Error de envío",
    )
    notification_sent_at = models.DateTimeField(
        blank=True, null=True, verbose_name="Fecha envío",
    )

    # Diagnóstico generado por IA
    ai_diagnosis = models.TextField(
        blank=True, null=True,
        verbose_name="Diagnóstico IA",
        help_text="Informe generado automáticamente por el modelo de IA.",
    )

    # Para silenciar/acknowledge
    is_acknowledged = models.BooleanField(
        default=False, verbose_name="Reconocida (ack)",
    )
    acknowledged_by = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="acknowledged_triggers",
        verbose_name="Reconocida por",
    )
    acknowledged_at = models.DateTimeField(
        blank=True, null=True, verbose_name="Fecha reconocimiento",
    )

    class Meta:
        verbose_name = "Disparo de alerta"
        verbose_name_plural = "Disparos de alerta"
        indexes = [
            models.Index(fields=["alert_rule", "triggered_at"]),
            models.Index(fields=["is_acknowledged", "notification_sent"]),
        ]

    def __str__(self):
        return f"Trigger #{self.id} de {self.alert_rule.name} @ {self.triggered_at}"


class SystemEvent(ModelApi):
    """
    Eventos automáticos del sistema: reinicios de contador, desconexiones,
    reconexiones, errores de medición, saltos masivos bloqueados, etc.
    """

    EVENT_TYPE_CHOICES = [
        ("COUNTER_RESET", "Reinicio de contador"),
        ("DISCONNECTION", "Desconexión"),
        ("RECONNECTION", "Reconexión"),
        ("MEASUREMENT_ERROR", "Error de medición"),
        ("MASSIVE_JUMP_BLOCKED", "Salto masivo bloqueado"),
        ("TOKEN_REFRESH", "Token refrescado"),
        ("API_ERROR", "Error de API externa"),
    ]

    SEVERITY_CHOICES = [
        ("INFO", "Informativo"),
        ("WARNING", "Advertencia"),
        ("CRITICAL", "Crítico"),
    ]

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_TYPE_CHOICES,
        verbose_name="Tipo de evento",
        db_index=True,
    )
    point_catchment = models.ForeignKey(
        CatchmentPoint,
        related_name="system_events",
        on_delete=models.CASCADE,
        verbose_name="Punto de captación",
        null=True, blank=True,
        db_index=True,
    )
    title = models.CharField(max_length=300, verbose_name="Título")
    message = models.TextField(verbose_name="Mensaje")
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        default="INFO",
        verbose_name="Severidad",
        db_index=True,
    )

    # Metadatos opcionales
    extra_data = models.JSONField(
        blank=True, null=True,
        verbose_name="Datos extra",
        help_text="JSON con información adicional del evento.",
    )

    class Meta:
        verbose_name = "Evento del sistema"
        verbose_name_plural = "Eventos del sistema"
        indexes = [
            models.Index(fields=["event_type", "created"]),
            models.Index(fields=["point_catchment", "created"]),
            models.Index(fields=["severity", "created"]),
        ]

    def __str__(self):
        scope = f"Punto {self.point_catchment_id}" if self.point_catchment else "Sistema"
        return f"[{scope}] {self.title} ({self.severity})"
