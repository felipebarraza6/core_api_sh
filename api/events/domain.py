"""
Domain Events

Typed domain events for the SmartHydro platform.
All events follow the CloudEvents specification where applicable.
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional


@dataclass
class DomainEvent:
    """Base class for all domain events."""

    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_version: str = "1.0"
    occurred_at: str = field(
        default_factory=lambda: datetime.now(dt_timezone.utc).isoformat()
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "specversion": "1.0",
            "type": self.event_type,
            "source": f"smarthydro/{self.aggregate_type}",
            "id": self.event_id,
            "time": self.occurred_at,
            "datacontenttype": "application/json",
            "data": self.payload,
            "event_version": self.event_version,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DomainEvent":
        return cls(
            event_type=data["type"],
            aggregate_type=data.get("aggregate_type", "unknown"),
            aggregate_id=data.get("aggregate_id", ""),
            payload=data.get("data", {}),
            event_id=data.get("id", str(uuid.uuid4())),
            event_version=data.get("event_version", "1.0"),
            occurred_at=data.get("time", datetime.now(dt_timezone.utc).isoformat()),
            metadata=data.get("metadata", {}),
        )


# ==================== Telemetry Events ====================

@dataclass
class TelemetryReceived(DomainEvent):
    """Emitted when new telemetry data is ingested."""

    event_type: str = "telemetry.received"
    aggregate_type: str = "telemetry"

    def __init__(
        self,
        device_id: str,
        catchment_point_id: str,
        variables: List[Dict],
        provider: str,
        timestamp: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            event_type=self.event_type,
            aggregate_type=self.aggregate_type,
            aggregate_id=device_id,
            payload={
                "device_id": device_id,
                "catchment_point_id": catchment_point_id,
                "variables": variables,
                "provider": provider,
                "timestamp": timestamp or datetime.now(dt_timezone.utc).isoformat(),
                **kwargs,
            },
        )


@dataclass
class TelemetryProcessed(DomainEvent):
    """Emitted when telemetry data has been processed (calculations, aggregations)."""

    event_type: str = "telemetry.processed"
    aggregate_type: str = "telemetry"

    def __init__(
        self,
        device_id: str,
        catchment_point_id: str,
        processed_variables: List[Dict],
        processing_duration_ms: int,
        **kwargs
    ):
        super().__init__(
            event_type=self.event_type,
            aggregate_type=self.aggregate_type,
            aggregate_id=device_id,
            payload={
                "device_id": device_id,
                "catchment_point_id": catchment_point_id,
                "processed_variables": processed_variables,
                "processing_duration_ms": processing_duration_ms,
                **kwargs,
            },
        )


# ==================== Alert Events ====================

@dataclass
class AlertTriggered(DomainEvent):
    """Emitted when an alert threshold is triggered."""

    event_type: str = "alert.triggered"
    aggregate_type: str = "alert"

    def __init__(
        self,
        alert_rule_id: str,
        catchment_point_id: str,
        variable_name: str,
        threshold_value: float,
        actual_value: float,
        severity: str,  # low, medium, high, critical
        **kwargs
    ):
        super().__init__(
            event_type=self.event_type,
            aggregate_type=self.aggregate_type,
            aggregate_id=alert_rule_id,
            payload={
                "alert_rule_id": alert_rule_id,
                "catchment_point_id": catchment_point_id,
                "variable_name": variable_name,
                "threshold_value": threshold_value,
                "actual_value": actual_value,
                "severity": severity,
                **kwargs,
            },
        )


@dataclass
class AlertResolved(DomainEvent):
    """Emitted when an alert condition returns to normal."""

    event_type: str = "alert.resolved"
    aggregate_type: str = "alert"

    def __init__(
        self,
        alert_rule_id: str,
        catchment_point_id: str,
        variable_name: str,
        resolved_value: float,
        **kwargs
    ):
        super().__init__(
            event_type=self.event_type,
            aggregate_type=self.aggregate_type,
            aggregate_id=alert_rule_id,
            payload={
                "alert_rule_id": alert_rule_id,
                "catchment_point_id": catchment_point_id,
                "variable_name": variable_name,
                "resolved_value": resolved_value,
                **kwargs,
            },
        )


# ==================== Compliance Events ====================

@dataclass
class ComplianceSubmitted(DomainEvent):
    """Emitted when a compliance report is submitted to an authority."""

    event_type: str = "compliance.submitted"
    aggregate_type: str = "compliance"

    def __init__(
        self,
        submission_id: str,
        authority: str,  # dga, sma
        catchment_point_id: str,
        report_type: str,
        period_start: str,
        period_end: str,
        status: str,
        **kwargs
    ):
        super().__init__(
            event_type=self.event_type,
            aggregate_type=self.aggregate_type,
            aggregate_id=submission_id,
            payload={
                "submission_id": submission_id,
                "authority": authority,
                "catchment_point_id": catchment_point_id,
                "report_type": report_type,
                "period_start": period_start,
                "period_end": period_end,
                "status": status,
                **kwargs,
            },
        )


@dataclass
class ComplianceVerified(DomainEvent):
    """Emitted when a compliance submission is verified by the authority."""

    event_type: str = "compliance.verified"
    aggregate_type: str = "compliance"

    def __init__(
        self,
        submission_id: str,
        authority: str,
        verification_status: str,
        verification_details: Dict,
        **kwargs
    ):
        super().__init__(
            event_type=self.event_type,
            aggregate_type=self.aggregate_type,
            aggregate_id=submission_id,
            payload={
                "submission_id": submission_id,
                "authority": authority,
                "verification_status": verification_status,
                "verification_details": verification_details,
                **kwargs,
            },
        )


# ==================== Device/Infrastructure Events ====================

@dataclass
class DeviceStatusChanged(DomainEvent):
    """Emitted when an IoT device changes status."""

    event_type: str = "device.status_changed"
    aggregate_type: str = "device"

    def __init__(
        self,
        device_id: str,
        catchment_point_id: str,
        previous_status: str,
        new_status: str,
        reason: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            event_type=self.event_type,
            aggregate_type=self.aggregate_type,
            aggregate_id=device_id,
            payload={
                "device_id": device_id,
                "catchment_point_id": catchment_point_id,
                "previous_status": previous_status,
                "new_status": new_status,
                "reason": reason,
                **kwargs,
            },
        )


@dataclass
class CatchmentPointCreated(DomainEvent):
    """Emitted when a new catchment point is registered."""

    event_type: str = "catchment_point.created"
    aggregate_type: str = "catchment_point"

    def __init__(
        self,
        catchment_point_id: str,
        name: str,
        client_id: str,
        location: Dict,
        device_ids: List[str],
        **kwargs
    ):
        super().__init__(
            event_type=self.event_type,
            aggregate_type=self.aggregate_type,
            aggregate_id=catchment_point_id,
            payload={
                "catchment_point_id": catchment_point_id,
                "name": name,
                "client_id": client_id,
                "location": location,
                "device_ids": device_ids,
                **kwargs,
            },
        )


# ==================== Document/Export Events ====================

@dataclass
class ExportRequested(DomainEvent):
    """Emitted when a data export is requested."""

    event_type: str = "export.requested"
    aggregate_type: str = "export"

    def __init__(
        self,
        export_id: str,
        export_type: str,
        format: str,
        catchment_point_ids: List[str],
        date_range: Dict[str, str],
        requested_by: str,
        **kwargs
    ):
        super().__init__(
            event_type=self.event_type,
            aggregate_type=self.aggregate_type,
            aggregate_id=export_id,
            payload={
                "export_id": export_id,
                "export_type": export_type,
                "format": format,
                "catchment_point_ids": catchment_point_ids,
                "date_range": date_range,
                "requested_by": requested_by,
                **kwargs,
            },
        )
