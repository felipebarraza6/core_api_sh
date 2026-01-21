"""
Compliance Models

NOTA: Los modelos completos se migrarán desde api.telemetry.providers.compliance_models
Este archivo define la estructura base.
"""

from django.db import models
from api.core.models.utils import ModelApi


# Los modelos ComplianceProvider, PointComplianceConfig, ComplianceStandard, etc.
# se migrarán aquí desde api/telemetry/providers/compliance_models.py

# Por ahora, dejamos imports para evitar romper el código existente:
# from api.telemetry.providers.compliance_models import (
#     ComplianceProvider,
#     PointComplianceConfig,
#     ManualComplianceRecord,
# )
# from api.telemetry.providers.compliance_standard import ComplianceStandard

# TODO: Migración gradual de modelos desde telemetry/providers
