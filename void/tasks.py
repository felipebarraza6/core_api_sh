"""Celery tasks for void."""
from datetime import timedelta
from typing import List

from celery import shared_task
from django.utils import timezone

from void.models import (
    ComplianceSubmission,
    Device,
    Point,
    PointComplianceProfile,
    ProcessedReading,
    RawReading,
)
from void.services import (
    ComplianceService,
    IngestService,
    PipelineService,
    ShadowService,
    SubscriptionService,
)
from void.services.notifications import AlertDispatcher


def _void_automation_enabled() -> bool:
    """Feature flag que evita que void ejecute automatización en producción."""
    from django.conf import settings

    return getattr(settings, "VOID_AUTOMATION_ENABLED", False)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def void_health_check(self) -> bool:
    """Tarea de prueba para validar que Celery ve a void."""
    return True


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def void_collect_device_variable(
    self,
    device_id: int,
    variable: str,
    lookback_minutes: int = 70,
) -> int:
    """Ingesta una variable para un dispositivo.

    Retorna la cantidad de lecturas crudas creadas.
    """
    if not _void_automation_enabled():
        return {"skipped": True, "reason": "VOID_AUTOMATION_ENABLED is false"}

    try:
        device = Device.objects.select_related("point", "provider").get(pk=device_id)
    except Device.DoesNotExist:
        return 0

    until = timezone.now()
    since = until - timedelta(minutes=lookback_minutes)

    service = IngestService()
    created = service.ingest_device_variable(
        device=device,
        variable=variable,
        since=since,
        until=until,
        task_id=self.request.id,
    )
    return len(created)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def void_collect_frequency(self, frequency_minutes: int) -> dict:
    """Recorre dispositivos activos con una frecuencia dada y los ingiere.

    Retorna resumen por variable.
    """
    if not _void_automation_enabled():
        return {"skipped": True, "reason": "VOID_AUTOMATION_ENABLED is false"}

    points = Point.objects.filter(
        is_active=True,
        frequency_minutes=frequency_minutes,
    )
    summary = {}

    for point in points.prefetch_related("device"):
        try:
            device = point.device
        except Device.DoesNotExist:
            continue

        variables = device.configuration.get("variables", [])
        for variable in variables:
            void_collect_device_variable.delay(
                device_id=device.id,
                variable=variable,
            )
            summary.setdefault(variable, 0)

    return {"frequency": frequency_minutes, "devices_enqueued": points.count(), "summary": summary}


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def void_process_reading(self, reading_id: int) -> int:
    """Procesa una lectura cruda aplicando el esquema de procesamiento."""
    if not _void_automation_enabled():
        return {"skipped": True, "reason": "VOID_AUTOMATION_ENABLED is false"}

    try:
        reading = RawReading.objects.select_related("device").get(pk=reading_id)
    except RawReading.DoesNotExist:
        return 0

    service = PipelineService()
    processed = service.process_reading(reading)
    return processed.id


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def void_process_device_variable(
    self,
    device_id: int,
    variable: str,
    since_iso: str = None,
    until_iso: str = None,
) -> int:
    """Procesa lecturas crudas pendientes de una variable."""
    if not _void_automation_enabled():
        return {"skipped": True, "reason": "VOID_AUTOMATION_ENABLED is false"}

    try:
        device = Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return 0

    since = timezone.datetime.fromisoformat(since_iso) if since_iso else None
    until = timezone.datetime.fromisoformat(until_iso) if until_iso else None

    service = PipelineService()
    results = service.process_device_variable(device, variable, since=since, until=until)
    return len(results)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def void_replicate_missing(
    self,
    point_id: int,
    variable: str = "",
    until_iso: str = "",
) -> dict:
    """Replica lecturas faltantes para un punto con ``replicate_on_missing=True``.

    No ejecuta envíos a DGA; solo crea ``ProcessedReading`` sintéticos.
    """
    if not _void_automation_enabled():
        return {"skipped": True, "reason": "VOID_AUTOMATION_ENABLED is false"}

    try:
        point = Point.objects.select_related("device").get(pk=point_id)
    except Point.DoesNotExist:
        return {"error": "point_not_found"}

    until = None
    if until_iso:
        until = timezone.datetime.fromisoformat(until_iso)

    service = ReplicationService()

    if variable:
        created = service.replicate_missing_for_point(point, variable, until=until)
        return {"point_id": point_id, "variable": variable, "created": len(created)}

    device = point.device
    result = service.replicate_missing_for_device(device, until=until)
    return {"point_id": point_id, "replicated": result["replicated"], "variables": result["variables"]}


@shared_task
def void_run_sla_checks() -> int:
    """Evalúa políticas SLA. Placeholder para fase 2.2."""
    return 0


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def void_backfill_device(
    self,
    device_id: int,
    since_iso: str,
    until_iso: str,
    variables: List[str] = None,
) -> dict:
    """Backfill controlado para un dispositivo.

    Placeholder con estructura lista; la lógica de backfill real se implementa
    cuando existan los proveedores concretos.
    """
    return {"device_id": device_id, "since": since_iso, "until": until_iso, "status": "not_implemented"}


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def void_check_subscriptions(self) -> dict:
    """Revisa contratos próximos a vencer y facturas vencidas.

    Se ejecuta diariamente vía Celery beat.
    """
    if not _void_automation_enabled():
        return {"skipped": True, "reason": "VOID_AUTOMATION_ENABLED is false"}

    service = SubscriptionService()
    contract_notifications = service.check_contracts()
    invoice_notifications = service.check_invoices()

    # Enviar notificaciones pendientes (solo email por ahora).
    sent = 0
    failed = 0
    for notification in contract_notifications + invoice_notifications:
        try:
            _send_notification_email(notification)
            notification.status = "sent"
            notification.sent_at = timezone.now()
            if notification.contract and notification.category == "subscription_reminder":
                service.mark_contract_reminder_sent(notification.contract)
            sent += 1
        except Exception as exc:
            notification.status = "failed"
            notification.error_message = str(exc)
            failed += 1
        notification.save(update_fields=["status", "sent_at", "error_message"])

    return {
        "contract_reminders": len(contract_notifications),
        "invoice_overdue": len(invoice_notifications),
        "sent": sent,
        "failed": failed,
    }


def _send_notification_email(notification) -> None:
    """Envía un email de notificación. Placeholder para integración real."""
    from django.core.mail import send_mail
    from django.conf import settings

    send_mail(
        subject=notification.subject,
        message=notification.body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@smarthydro.cl"),
        recipient_list=[notification.recipient_email],
        fail_silently=False,
    )


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def void_shadow_run(
    self,
    device_id: int,
    variable: str,
    window_minutes: int = 70,
    ingest: bool = True,
    process: bool = False,
) -> dict:
    """Ejecuta shadow mode para un device/variable y retorna resumen."""
    try:
        device = Device.objects.select_related("point", "provider").get(pk=device_id)
    except Device.DoesNotExist:
        return {"error": "device_not_found"}

    service = ShadowService()
    run = service.run(
        device=device,
        variable=variable,
        window_minutes=window_minutes,
        ingest=ingest,
        process=process,
    )

    return {
        "run_id": run.id,
        "status": run.status,
        "legacy_count": run.legacy_count,
        "void_count": run.void_count,
        "matched_count": run.matched_count,
        "mismatched_count": run.mismatched_count,
        "legacy_only_count": run.legacy_only_count,
        "void_only_count": run.void_only_count,
        "error_message": run.error_message,
    }


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def void_shadow_sample(
    self,
    max_devices: int = 5,
    window_minutes: int = 70,
) -> dict:
    """Ejecuta shadow mode sobre una muestra de dispositivos activos.

    Útil para validación continua sin saturar workers ni APIs externas.
    """
    if not _void_automation_enabled():
        return {"skipped": True, "reason": "VOID_AUTOMATION_ENABLED is false"}

    devices = Device.objects.filter(
        is_active=True,
        provider__is_active=True,
    ).exclude(
        point__legacy_point__isnull=True,
    )[:max_devices]

    enqueued = 0
    for device in devices:
        variables = device.configuration.get("variables", ["pulses"])
        for variable in variables[:3]:  # máx 3 variables por device
            void_shadow_run.delay(
                device_id=device.id,
                variable=variable,
                window_minutes=window_minutes,
            )
            enqueued += 1

    return {"enqueued": enqueued, "devices": devices.count()}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def void_submit_compliance(
    self,
    profile_id: int,
    reading_id: int,
) -> dict:
    """Envía una lectura procesada a la entidad de cumplimiento del perfil."""
    if not _void_automation_enabled():
        return {"skipped": True, "reason": "VOID_AUTOMATION_ENABLED is false"}

    try:
        profile = PointComplianceProfile.objects.select_related("authority").get(pk=profile_id)
        reading = ProcessedReading.objects.get(pk=reading_id)
    except (PointComplianceProfile.DoesNotExist, ProcessedReading.DoesNotExist):
        return {"error": "profile_or_reading_not_found"}

    service = ComplianceService()
    submission = service.submit_reading(profile, reading, auto_send=True)
    return {
        "submission_id": submission.id,
        "status": submission.status,
        "voucher": submission.voucher,
        "tracking_id": submission.tracking_id,
        "error_message": submission.error_message,
    }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def void_process_compliance_queue(
    self,
    authority_code: str = None,
    max_submissions: int = 30,
) -> dict:
    """Procesa cola de envíos de cumplimiento pendientes."""
    if not _void_automation_enabled():
        return {"skipped": True, "reason": "VOID_AUTOMATION_ENABLED is false"}

    service = ComplianceService()
    return service.process_queue(
        authority_code=authority_code,
        max_submissions=max_submissions,
    )


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def void_aggregate_compliance(
    self,
    profile_id: int,
    period_start_iso: str,
    period_end_iso: str,
) -> dict:
    """Envío agregado de un período. Placeholder para fase 2."""
    if not _void_automation_enabled():
        return {"skipped": True, "reason": "VOID_AUTOMATION_ENABLED is false"}

    try:
        profile = PointComplianceProfile.objects.get(pk=profile_id)
    except PointComplianceProfile.DoesNotExist:
        return {"error": "profile_not_found"}

    service = ComplianceService()
    since = timezone.datetime.fromisoformat(period_start_iso)
    until = timezone.datetime.fromisoformat(period_end_iso)
    submission = service.submit_period(profile, since, until, auto_send=True)
    return {
        "submission_id": submission.id,
        "status": submission.status,
        "error_message": submission.error_message,
    }


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def void_retry_compliance_submission(
    self,
    submission_id: int,
) -> dict:
    """Reintenta manualmente una submission existente."""
    try:
        submission = ComplianceSubmission.objects.select_related("profile__authority").get(pk=submission_id)
    except ComplianceSubmission.DoesNotExist:
        return {"error": "submission_not_found"}

    service = ComplianceService()
    submission = service.retry_submission(submission)
    return {
        "submission_id": submission.id,
        "status": submission.status,
        "attempt_number": submission.attempt_number,
        "voucher": submission.voucher,
        "tracking_id": submission.tracking_id,
        "error_message": submission.error_message,
    }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def void_dispatch_alerts(
    self,
    trigger_ids: list = None,
    limit: int = 100,
) -> dict:
    """Envía alertas pendientes.

    Si se pasan trigger_ids, despacha solo esas. Si no, procesa todos los
    triggers con status='pending' hasta el límite.
    """
    dispatcher = AlertDispatcher()
    if trigger_ids:
        from void.models import AlertTrigger
        results = {}
        for trigger in AlertTrigger.objects.filter(pk__in=trigger_ids):
            results[trigger.id] = dispatcher.dispatch(trigger)
        return {"mode": "by_id", "processed": len(results)}

    return {"mode": "batch", "stats": dispatcher.dispatch_pending(limit=limit)}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def void_shadow_totals(
    self,
    point_id: int,
    output_field: str = "total",
    window_minutes: int = 70,
    ingest: bool = True,
    process: bool = True,
) -> dict:
    """Ejecuta shadow mode para un campo procesado de un punto."""
    if not _void_automation_enabled():
        return {"skipped": True, "reason": "VOID_AUTOMATION_ENABLED is false"}

    try:
        point = Point.objects.select_related("device__point").get(pk=point_id)
        device = point.device
    except (Point.DoesNotExist, Device.DoesNotExist):
        return {"error": "point_or_device_not_found"}

    service = ShadowService()
    run = service.run_for_output_field(
        device=device,
        output_field=output_field,
        window_minutes=window_minutes,
        ingest=ingest,
        process=process,
    )
    return {
        "run_id": run.id,
        "status": run.status,
        "variable": run.variable,
        "output_field": run.output_field,
        "matched_count": run.matched_count,
        "mismatched_count": run.mismatched_count,
        "legacy_only_count": run.legacy_only_count,
        "void_only_count": run.void_only_count,
        "error_message": run.error_message,
    }
