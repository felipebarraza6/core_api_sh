"""Scheduling service for compliance submissions.

Determina si un ``ProcessedReading`` debe enviarse según el estándar
configurado en ``PointComplianceProfile``. Permite estándares dinámicos
(MAYOR, MEDIO, MENOR, etc.) sin lógica hardcodeada.
"""
from datetime import datetime
from typing import Optional

from void.models import ComplianceStandard, PointComplianceProfile


class ComplianceScheduleService:
    """Evalúa si un timestamp califica para envío de cumplimiento."""

    def should_submit(
        self,
        profile: PointComplianceProfile,
        timestamp: datetime,
    ) -> bool:
        """Retorna True si el timestamp califica para envío.

        Si el perfil no tiene estándar asignado, se acepta cualquier timestamp
        (comportamiento SIN_ESTANDAR).
        """
        standard = profile.standard
        if standard is None:
            return True
        return standard.matches_timestamp(timestamp)

    def next_due(
        self,
        standard: ComplianceStandard,
        after: datetime,
    ) -> Optional[datetime]:
        """Calcula el próximo timestamp que califica para envío.

        Placeholder simple: avanza en pasos de frequency_minutes hasta encontrar
        un match. Para estándares complejos (mensual/semestral) se recomienda
        calcular directamente.
        """
        if standard is None:
            return after

        from datetime import timedelta

        candidate = after.replace(second=0, microsecond=0)
        step = timedelta(minutes=standard.frequency_minutes or 1)
        max_iterations = 1440  # evitar loop infinito

        for _ in range(max_iterations):
            if standard.matches_timestamp(candidate) and candidate > after:
                return candidate
            candidate += step

        return None
