"""Views for void API."""
import logging
from datetime import datetime

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from void.models import (
    ComplianceSubmission,
    Device,
    DeviceVariableConfig,
    PointComplianceProfile,
    ProcessedReading,
    RawReading,
)
from void.services import ComplianceService
from void.services.handlers.stateful_rulesets import apply_totalizer_schema
from void.services.pipeline import PipelineService

logger = logging.getLogger(__name__)


def _staff_required(request):
    """Retorna JsonResponse de error si el usuario no es staff."""
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"error": "Se requiere usuario staff"}, status=403)
    return None


@require_GET
def health_check(request):
    """Health check básico de void."""
    return JsonResponse({"status": "ok", "app": "void"})


@csrf_exempt
@require_POST
def ingest_reading(request):
    """Ingesta de una lectura cruda para un device.

    Payload esperado:
        {
            "serial_number": "SN-001",     # o "external_id"
            "source_variable": "pulses",
            "value": "150",
            "timestamp": "2026-07-05T14:00:00Z",  # opcional, default ahora
            "auto_configure": true         # opcional, aplica totalizador stateful si falta config
        }

    Header requerido:
        X-Device-Token: <token guardado en device.configuration["ingest_token"]>
    """
    token = request.headers.get("X-Device-Token", "")
    if not token:
        return JsonResponse({"error": "Falta header X-Device-Token"}, status=401)

    try:
        payload = __import__("json").loads(request.body)
    except Exception as exc:
        return JsonResponse({"error": f"JSON inválido: {exc}"}, status=400)

    serial_number = payload.get("serial_number", "")
    external_id = payload.get("external_id", "")

    device = None
    if serial_number:
        device = Device.objects.filter(serial_number=serial_number).first()
    if device is None and external_id:
        device = Device.objects.filter(external_id=external_id).first()

    if device is None:
        return JsonResponse({"error": "Device no encontrado"}, status=404)

    expected_token = device.configuration.get("ingest_token", "")
    if not expected_token or token != expected_token:
        return JsonResponse({"error": "Token inválido"}, status=403)

    source_variable = payload.get("source_variable", "")
    value = payload.get("value")
    if not source_variable or value is None:
        return JsonResponse(
            {"error": "Faltan source_variable y/o value"}, status=400
        )

    variable = payload.get("variable") or source_variable

    # Timestamp opcional; si no viene, ahora.
    ts_str = payload.get("timestamp")
    if ts_str:
        try:
            # Acepta ISO 8601 con o sin zona.
            timestamp = timezone.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            return JsonResponse({"error": "timestamp inválido"}, status=400)
    else:
        timestamp = timezone.now()

    if timestamp.tzinfo is None:
        timestamp = timezone.make_aware(timestamp)

    # Auto-configuración stateful si aplica.
    config = DeviceVariableConfig.objects.filter(
        device=device, source_variable=source_variable
    ).first()
    if config is None and payload.get("auto_configure"):
        apply_totalizer_schema(
            device=device,
            source_variable=source_variable,
            internal_variable=variable,
        )
    elif config is None:
        return JsonResponse(
            {"error": f"Variable '{source_variable}' no configurada. Envía auto_configure=true o configúrala en admin."},
            status=400,
        )

    raw = RawReading.objects.create(
        device=device,
        variable=variable,
        source_variable=source_variable,
        timestamp=timestamp,
        raw_value=str(value),
    )

    try:
        processed = PipelineService().process_reading(raw)
    except Exception as exc:
        logger.exception("Error procesando lectura ingestada: %s", exc)
        return JsonResponse({"error": f"Error procesando lectura: {exc}"}, status=500)

    return JsonResponse(
        {
            "raw_id": raw.id,
            "processed_id": processed.id,
            "device_id": device.id,
            "variable": variable,
            "timestamp": processed.timestamp.isoformat(),
            "total": f"{processed.total:.3f}" if processed.total is not None else None,
            "flow": f"{processed.flow:.3f}" if processed.flow is not None else None,
            "nivel": f"{processed.nivel:.3f}" if processed.nivel is not None else None,
            "is_error": processed.is_error,
            "error_message": processed.error_message,
        },
        status=201,
    )


@require_POST
def compliance_submit(request):
    """Envío manual de una lectura procesada a una entidad de cumplimiento.

    Payload:
        {
            "profile_id": 1,
            "reading_id": 2
        }
    """
    error = _staff_required(request)
    if error:
        return error

    try:
        payload = __import__("json").loads(request.body)
    except Exception as exc:
        return JsonResponse({"error": f"JSON inválido: {exc}"}, status=400)

    profile_id = payload.get("profile_id")
    reading_id = payload.get("reading_id")
    if not profile_id or not reading_id:
        return JsonResponse({"error": "Faltan profile_id y/o reading_id"}, status=400)

    try:
        profile = PointComplianceProfile.objects.select_related("authority").get(pk=profile_id)
        reading = ProcessedReading.objects.get(pk=reading_id)
    except (PointComplianceProfile.DoesNotExist, ProcessedReading.DoesNotExist):
        return JsonResponse({"error": "Perfil o lectura no encontrada"}, status=404)

    service = ComplianceService()
    submission = service.submit_reading(profile, reading, auto_send=True)
    return JsonResponse({
        "submission_id": submission.id,
        "status": submission.status,
        "voucher": submission.voucher,
        "tracking_id": submission.tracking_id,
        "error_message": submission.error_message,
    }, status=201)


@require_GET
def compliance_submissions(request):
    """Listado paginado simple de submissions."""
    error = _staff_required(request)
    if error:
        return error

    status_filter = request.GET.get("status")
    authority_code = request.GET.get("authority")
    limit = min(int(request.GET.get("limit", 50)), 200)
    offset = int(request.GET.get("offset", 0))

    qs = ComplianceSubmission.objects.select_related("profile__authority", "processed_reading")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if authority_code:
        qs = qs.filter(profile__authority__code=authority_code)

    total = qs.count()
    items = qs.order_by("-created")[offset:offset + limit]

    return JsonResponse({
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": s.id,
                "profile": str(s.profile),
                "authority": s.profile.authority.code,
                "status": s.status,
                "attempt_number": s.attempt_number,
                "sent_at": s.sent_at.isoformat() if s.sent_at else None,
                "voucher": s.voucher,
                "tracking_id": s.tracking_id,
                "error_message": s.error_message,
                "created": s.created.isoformat(),
            }
            for s in items
        ],
    })


@require_GET
def compliance_queue(request):
    """Resumen de la cola de envíos pendientes/reintentando."""
    error = _staff_required(request)
    if error:
        return error

    service = ComplianceService()
    summary = service.process_queue(max_submissions=0)  # resumen vacío, no procesa nada
    # Sobrescribimos con conteos reales.
    qs = ComplianceSubmission.objects.filter(status__in=["pending", "retrying"])
    by_status = {
        "pending": qs.filter(status="pending").count(),
        "retrying": qs.filter(status="retrying").count(),
    }
    return JsonResponse({
        "pending": by_status["pending"],
        "retrying": by_status["retrying"],
        "total": sum(by_status.values()),
    })
