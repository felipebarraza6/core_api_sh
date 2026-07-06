"""Subscription, contract and billing models for void."""
from django.db import models

from void.models.base import VoidModel


class Contract(VoidModel):
    """Contrato de servicio con un cliente."""

    BILLING_CYCLE_CHOICES = [
        ("monthly", "Mensual"),
        ("quarterly", "Trimestral"),
        ("semiannual", "Semestral"),
        ("yearly", "Anual"),
    ]

    STATUS_CHOICES = [
        ("active", "Activo"),
        ("pending", "Pendiente"),
        ("suspended", "Suspendido"),
        ("cancelled", "Cancelado"),
        ("expired", "Vencido"),
    ]

    REMINDER_FREQUENCY_CHOICES = [
        ("once", "Una vez"),
        ("daily", "Diaria"),
        ("every_3_days", "Cada 3 días"),
        ("weekly", "Semanal"),
    ]

    client = models.ForeignKey(
        "Client",
        on_delete=models.CASCADE,
        related_name="contracts",
        verbose_name="Cliente",
    )
    name = models.CharField(
        max_length=300,
        verbose_name="Nombre del contrato",
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="Descripción",
    )

    start_date = models.DateField(
        verbose_name="Fecha de inicio",
        db_index=True,
    )
    end_date = models.DateField(
        verbose_name="Fecha de término",
        db_index=True,
    )

    billing_cycle = models.CharField(
        max_length=20,
        choices=BILLING_CYCLE_CHOICES,
        default="monthly",
        verbose_name="Ciclo de facturación",
    )
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Monto base",
    )
    currency = models.CharField(
        max_length=3,
        default="CLP",
        verbose_name="Moneda",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        verbose_name="Estado",
        db_index=True,
    )
    auto_renew = models.BooleanField(
        default=False,
        verbose_name="Renovación automática",
    )

    reminder_frequency = models.CharField(
        max_length=20,
        choices=REMINDER_FREQUENCY_CHOICES,
        default="once",
        verbose_name="Frecuencia de recordatorio",
        help_text="Con qué frecuencia se repite el aviso de vencimiento antes de la fecha de término.",
    )
    last_reminder_sent_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Último recordatorio enviado",
    )

    payment_method = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Método de pago",
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metadatos",
    )

    class Meta:
        verbose_name = "Contrato"
        verbose_name_plural = "Contratos"
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["client", "status", "end_date"]),
            models.Index(fields=["status", "end_date"]),
        ]

    def __str__(self):
        return f"{self.client} | {self.name} ({self.get_billing_cycle_display()})"


class Subscription(VoidModel):
    """Suscripción de un punto a un contrato."""

    STATUS_CHOICES = [
        ("active", "Activa"),
        ("pending", "Pendiente"),
        ("suspended", "Suspendida"),
        ("cancelled", "Cancelada"),
    ]

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="subscriptions",
        verbose_name="Contrato",
    )
    point = models.ForeignKey(
        "Point",
        on_delete=models.CASCADE,
        related_name="subscriptions",
        verbose_name="Punto",
    )
    start_date = models.DateField(
        verbose_name="Fecha de inicio",
    )
    end_date = models.DateField(
        verbose_name="Fecha de término",
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
        verbose_name="Estado",
        db_index=True,
    )
    amount_override = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Monto específico (opcional)",
        help_text="Si está vacío, usa el monto del contrato.",
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas",
    )

    class Meta:
        verbose_name = "Suscripción"
        verbose_name_plural = "Suscripciones"
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["contract", "status", "end_date"]),
            models.Index(fields=["point", "status"]),
        ]

    def __str__(self):
        return f"{self.contract} → {self.point}"


class Invoice(VoidModel):
    """Factura de un período de contrato."""

    STATUS_CHOICES = [
        ("draft", "Borrador"),
        ("sent", "Enviada"),
        ("paid", "Pagada"),
        ("overdue", "Vencida"),
        ("cancelled", "Anulada"),
    ]

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="invoices",
        verbose_name="Contrato",
    )
    invoice_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Número de factura",
    )
    period_start = models.DateField(
        verbose_name="Inicio período",
    )
    period_end = models.DateField(
        verbose_name="Término período",
    )
    due_date = models.DateField(
        verbose_name="Fecha de vencimiento",
        db_index=True,
    )
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Monto neto",
    )
    tax_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Impuestos",
    )
    total_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Total",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
        verbose_name="Estado",
        db_index=True,
    )
    sent_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Enviada el",
    )
    paid_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Pagada el",
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name="Notas",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Metadatos",
    )

    class Meta:
        verbose_name = "Factura"
        verbose_name_plural = "Facturas"
        ordering = ["-due_date"]
        indexes = [
            models.Index(fields=["contract", "status", "due_date"]),
            models.Index(fields=["status", "due_date"]),
        ]

    def __str__(self):
        return f"{self.contract} | {self.period_start} - {self.period_end} | {self.status}"
