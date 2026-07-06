# Event Bus Module

## Proposito

Sistema de eventos para arquitectura desacoplada basada en **Event-Driven Architecture (EDA)**:
- **Comunicacion asincrona** entre modulos sin acoplamiento directo
- **Audit trail** completo de eventos de dominio
- **Event replay** para reconstruccion de estado
- **Dead letter queue** para manejo de eventos fallidos

## Arquitectura

```
┌─────────────┐     ┌──────────┐     ┌──────────────┐
│  Publisher  │────▶│ EventBus │────▶│ Redis Stream │
│  (Cualquier │     │          │     │              │
│   modulo)   │     └──────────┘     └──────┬───────┘
└─────────────┘                              │
                                             ▼
                                      ┌──────────────┐
                                      │   Handlers   │
                                      │  (Async)     │
                                      └──────────────┘
                                             │
                                             ▼
                                      ┌──────────────┐
                                      │ EventStore   │
                                      │ (PostgreSQL) │
                                      └──────────────┘
```

## Eventos de Dominio

| Evento | Origen | Destinatarios | Descripcion |
|--------|--------|--------------|-------------|
| `TelemetryReceived` | `api.ingestion` | `api.telemetry`, `api.alerts` | Nuevos datos de telemetria |
| `AlertTriggered` | `api.alerts` | `api.notifications`, `api.compliance` | Alerta umbral activada |
| `ComplianceSubmitted` | `api.compliance` | `api.notifications`, `api.documents` | Reporte enviado a DGA/SMA |
| `DeviceStatusChanged` | `api.infrastructure` | `api.telemetry`, `api.notifications` | Cambio de estado IoT |
| `CatchmentPointCreated` | `api.infrastructure` | `api.crm`, `api.compliance` | Nuevo punto de captacion |
| `ExportRequested` | `api.documents` | `api.notifications` | Solicitud de exportacion |

## Uso

```python
# Publicar evento
from api.events.bus import EventBus
from api.events.domain import TelemetryReceived

event = TelemetryReceived(
    device_id="12345",
    catchment_point_id="cp-001",
    variables=[{"name": "caudal", "value": 12.5}],
    timestamp="2026-01-01T00:00:00Z"
)
await EventBus.publish(event)

# Handler
from api.events.handlers import EventHandler

class TelemetryAlertHandler(EventHandler):
    async def handle(self, event: TelemetryReceived):
        # Procesar telemetria para alertas
        pass
```
