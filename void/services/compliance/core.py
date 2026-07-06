"""Core compliance service for void."""
import logging
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from void.models import (
    ComplianceAuthority,
    ComplianceSubmission,
    PointComplianceProfile,
    ProcessedReading,
)

from .registry import ComplianceAdapterRegistry
from .schedule import ComplianceScheduleService

logger = logging.getLogger(__name__)


class ComplianceService:
    """Orquesta envíos de cumplimiento regulatorio."""

    def __init__(self):
        pass

    def get_active_profiles_for_reading(
        self,
        reading: ProcessedReading,
    ) -> list:
        """Retorna perfiles activos asociados al punto del reading."""
        return list(
            PointComplianceProfile.objects.filter(
                point=reading.device.point,
                is_active=True,
                authority__is_active=True,
            ).select_related("authority")
        )

    def submit_reading(
        self,
        profile: PointComplianceProfile,
        reading: ProcessedReading,
        auto_send: bool = True,
    ) -> ComplianceSubmission:
        """Crea/envía una submission para una lectura procesada."""
        adapter = ComplianceAdapterRegistry.get_adapter(profile.authority)

        # Validar schedule según estándar configurado.
        schedule_service = ComplianceScheduleService()
        if not schedule_service.should_submit(profile, reading.timestamp):
            return ComplianceSubmission.objects.create(
                profile=profile,
                processed_reading=reading,
                status="unrecoverable",
                error_message=(
                    f"Timestamp {reading.timestamp} no califica para envío "
                    f"según estándar {profile.standard}"
                ),
                payload={},
            )

        payload = adapter.build_payload(profile, reading)

        with transaction.atomic():
            submission = ComplianceSubmission.objects.create(
                profile=profile,
                processed_reading=reading,
                payload=payload,
                status="pending",
            )

            if auto_send:
                submission = self._execute_send(submission, adapter, payload)

        return submission

    def _execute_send(
        self,
        submission: ComplianceSubmission,
        adapter,
        payload: dict,
    ) -> ComplianceSubmission:
        """Ejecuta el envío y actualiza la submission con el resultado."""
        result = adapter.send(payload)

        submission.attempt_number += 1
        submission.last_retry_at = timezone.now()
        submission.response_status = result.response_status
        submission.response_body = result.response_body
        submission.voucher = result.voucher
        submission.tracking_id = result.tracking_id
        submission.error_message = result.error_message
        submission.status = result.status

        if result.status in ("confirmed", "sent", "duplicate"):
            submission.sent_at = submission.sent_at or timezone.now()
            if result.status in ("confirmed", "duplicate"):
                submission.confirmed_at = submission.confirmed_at or timezone.now()

        submission.save(update_fields=[
            "attempt_number", "last_retry_at", "response_status",
            "response_body", "voucher", "tracking_id", "error_message",
            "status", "sent_at", "confirmed_at",
        ])
        return submission

    def retry_submission(self, submission: ComplianceSubmission) -> ComplianceSubmission:
        """Reintenta una submission existente."""
        if submission.status not in ("pending", "failed", "retrying"):
            return submission

        if submission.attempt_number >= submission.profile.authority.retry_attempts:
            submission.status = "failed"
            submission.error_message = "Agotados reintentos configurados"
            submission.save(update_fields=["status", "error_message"])
            return submission

        adapter = ComplianceAdapterRegistry.get_adapter(submission.profile.authority)
        submission.status = "retrying"
        submission.save(update_fields=["status"])
        return self._execute_send(submission, adapter, submission.payload)

    def process_queue(
        self,
        authority_code: Optional[str] = None,
        max_submissions: int = 30,
    ) -> dict:
        """Procesa cola de submissions pendientes o en reintento."""
        qs = ComplianceSubmission.objects.filter(
            status__in=["pending", "retrying"],
        ).select_related("profile__authority")

        if authority_code:
            qs = qs.filter(profile__authority__code=authority_code)

        # Backoff simple: no reintentar si el último reintento fue hace menos de 15 min.
        cutoff = timezone.now() - timedelta(minutes=15)
        qs = qs.exclude(
            status="retrying",
            last_retry_at__gt=cutoff,
        ).order_by("created")[:max_submissions]

        summary = {"processed": 0, "confirmed": 0, "failed": 0, "duplicate": 0, "unrecoverable": 0}
        for submission in qs:
            self.retry_submission(submission)
            summary["processed"] += 1
            status_key = submission.status
            if status_key in summary:
                summary[status_key] += 1

        return summary

    def submit_period(
        self,
        profile: PointComplianceProfile,
        period_start,
        period_end,
        auto_send: bool = True,
    ) -> ComplianceSubmission:
        """Envío agregado de un período. Placeholder para fase 2."""
        # TODO: calcular valores agregados del período y enviar.
        payload = {
            "profile_id": profile.id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "note": "Envío agregado aún no implementado",
        }
        return ComplianceSubmission.objects.create(
            profile=profile,
            period_start=period_start,
            period_end=period_end,
            payload=payload,
            status="unrecoverable",
            error_message="Envío agregado no implementado",
        )
