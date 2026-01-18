"""
Ejemplo de cómo integrar métricas Prometheus en el código existente
Copiar estos patrones en api/core/tasks/telemetry.py y api/cronjobs/dga/
"""

from api.core.metrics import (
    # Contadores
    telemetry_ingestion_total,
    telemetry_ingestion_errors,
    dga_transmissions_total,
    dga_transmission_errors,
    dga_vouchers_received,
    alerts_generated_total,

    # Gauges
    telemetry_flow_current,
    telemetry_total_current,
    telemetry_daily_consumption,

    # Histograms
    telemetry_processing_duration,
)
import time


# ============================================
# PATRÓN 1: Instrumentar ingestión de telemetría
# ============================================

def process_telemetry_data_instrumented(point_id, point_name, provider="TWIN"):
    """
    Ejemplo de cómo instrumentar process_single_point_unified()
    en api/core/tasks/telemetry.py
    """

    # Medir tiempo de procesamiento
    start_time = time.time()

    try:
        # Tu código existente de procesamiento
        # ... (fetch data, process variables, etc.)

        # Simular datos procesados
        flow_value = 12.5  # L/s
        total_value = 344270  # m³
        daily_consumption = 450  # m³/día

        # ✅ INCREMENTAR CONTADOR DE ÉXITO
        telemetry_ingestion_total.labels(
            point_id=str(point_id),
            point_name=point_name,
            provider=provider
        ).inc()

        # ✅ ACTUALIZAR VALORES ACTUALES
        telemetry_flow_current.labels(
            point_id=str(point_id),
            point_name=point_name,
            project="Proyecto Demo"
        ).set(flow_value)

        telemetry_total_current.labels(
            point_id=str(point_id),
            point_name=point_name,
            project="Proyecto Demo"
        ).set(total_value)

        telemetry_daily_consumption.labels(
            point_id=str(point_id),
            point_name=point_name,
            project="Proyecto Demo"
        ).set(daily_consumption)

        # ✅ REGISTRAR DURACIÓN
        duration = time.time() - start_time
        telemetry_processing_duration.labels(
            point_id=str(point_id),
            provider=provider
        ).observe(duration)

        return True

    except ConnectionError as e:
        # ✅ REGISTRAR ERROR ESPECÍFICO
        telemetry_ingestion_errors.labels(
            point_id=str(point_id),
            point_name=point_name,
            error_type="connection_error"
        ).inc()
        raise

    except ValueError as e:
        # ✅ REGISTRAR ERROR DE VALIDACIÓN
        telemetry_ingestion_errors.labels(
            point_id=str(point_id),
            point_name=point_name,
            error_type="validation_error"
        ).inc()
        raise

    except Exception as e:
        # ✅ REGISTRAR ERROR GENÉRICO
        telemetry_ingestion_errors.labels(
            point_id=str(point_id),
            point_name=point_name,
            error_type="unknown_error"
        ).inc()
        raise


# ============================================
# PATRÓN 2: Instrumentar transmisión DGA
# ============================================

def send_data_to_dga_instrumented(point_id, point_name, standard_type, records):
    """
    Ejemplo de cómo instrumentar send_data_dga()
    en api/cronjobs/dga/send_data_dga.py
    """

    try:
        # Tu código existente de envío a DGA
        # ... (prepare data, send request, etc.)

        # Simular respuesta exitosa
        voucher_number = "DGA-2026-12345"

        # ✅ REGISTRAR TRANSMISIÓN EXITOSA
        dga_transmissions_total.labels(
            point_id=str(point_id),
            point_name=point_name,
            standard_type=standard_type,
            status="success"
        ).inc()

        # ✅ REGISTRAR VOUCHER RECIBIDO
        dga_vouchers_received.labels(
            point_id=str(point_id),
            point_name=point_name
        ).inc()

        return voucher_number

    except requests.exceptions.Timeout:
        # ✅ REGISTRAR ERROR DE TIMEOUT
        dga_transmission_errors.labels(
            point_id=str(point_id),
            error_code="TIMEOUT",
            error_type="network_error"
        ).inc()

        dga_transmissions_total.labels(
            point_id=str(point_id),
            point_name=point_name,
            standard_type=standard_type,
            status="timeout"
        ).inc()
        raise

    except requests.exceptions.HTTPError as e:
        # ✅ REGISTRAR ERROR HTTP
        error_code = f"HTTP_{e.response.status_code}"

        dga_transmission_errors.labels(
            point_id=str(point_id),
            error_code=error_code,
            error_type="http_error"
        ).inc()

        dga_transmissions_total.labels(
            point_id=str(point_id),
            point_name=point_name,
            standard_type=standard_type,
            status="failed"
        ).inc()
        raise


# ============================================
# PATRÓN 3: Instrumentar generación de alertas
# ============================================

def create_notification_instrumented(point_id, point_name, alert_type, severity="warning"):
    """
    Ejemplo de cómo instrumentar creación de NotificationsCatchment
    """

    # Tu código existente
    # notification = NotificationsCatchment.objects.create(...)

    # ✅ REGISTRAR ALERTA GENERADA
    alerts_generated_total.labels(
        point_id=str(point_id),
        alert_type=alert_type,
        severity=severity
    ).inc()

    return True


# ============================================
# PATRÓN 4: Context Manager para medir duración
# ============================================

def process_with_timing():
    """
    Usar context manager para medir tiempo automáticamente
    """

    # Forma 1: Context manager
    with telemetry_processing_duration.labels(point_id="137", provider="TWIN").time():
        # Tu código aquí
        process_data()
        calculate_flow()
        save_to_database()

    # Forma 2: Decorador (crear en tu código)
    @telemetry_processing_duration.labels(point_id="137", provider="TWIN").time()
    def my_function():
        pass


# ============================================
# INTEGRACIÓN REAL EN CÓDIGO EXISTENTE
# ============================================

"""
EN api/core/tasks/telemetry.py, función process_single_point_unified():

def process_single_point_unified(point_id, frequency):
    from api.core.metrics import (
        telemetry_ingestion_total,
        telemetry_ingestion_errors,
        telemetry_processing_duration
    )

    start_time = time.time()

    try:
        point = CatchmentPoint.objects.get(id=point_id)

        # ... tu código existente ...

        # AL FINAL, SI TODO SALIÓ BIEN:
        telemetry_ingestion_total.labels(
            point_id=str(point_id),
            point_name=point.title,
            provider=provider_name  # "TWIN", "NETTRA", etc.
        ).inc()

        duration = time.time() - start_time
        telemetry_processing_duration.labels(
            point_id=str(point_id),
            provider=provider_name
        ).observe(duration)

        return True

    except Exception as e:
        # REGISTRAR ERROR
        telemetry_ingestion_errors.labels(
            point_id=str(point_id),
            point_name=point.title if point else "Unknown",
            error_type=type(e).__name__
        ).inc()
        raise
"""

"""
EN api/telemetry/ingestion/controllers/unified_processing.py, función save_telemetry_data():

def save_telemetry_data(point_id, created_register, processed_variables=None):
    from api.core.metrics import (
        telemetry_flow_current,
        telemetry_total_current,
        telemetry_daily_consumption
    )

    # ... tu código existente que guarda en TelemetryRecord ...

    # AL GUARDAR, ACTUALIZAR MÉTRICAS
    point = CatchmentPoint.objects.get(id=point_id)
    project_name = point.project.name if point.project else "Sin Proyecto"

    if "flow" in created_register and created_register["flow"] is not None:
        telemetry_flow_current.labels(
            point_id=str(point_id),
            point_name=point.title,
            project=project_name
        ).set(float(created_register["flow"]))

    if "total" in created_register and created_register["total"] is not None:
        telemetry_total_current.labels(
            point_id=str(point_id),
            point_name=point.title,
            project=project_name
        ).set(float(created_register["total"]))

    if "total_today_diff" in created_register:
        telemetry_daily_consumption.labels(
            point_id=str(point_id),
            point_name=point.title,
            project=project_name
        ).set(float(created_register["total_today_diff"]))

    return record
"""

"""
EN api/cronjobs/dga/send_data_dga.py, en la función que envía a DGA:

def send_to_dga(point_config, records):
    from api.core.metrics import (
        dga_transmissions_total,
        dga_transmission_errors,
        dga_vouchers_received
    )

    point = point_config.point_catchment
    standard_type = point_config.standard

    try:
        # ... tu código de envío ...

        # SI RECIBE VOUCHER:
        if voucher_number:
            dga_transmissions_total.labels(
                point_id=str(point.id),
                point_name=point.title,
                standard_type=standard_type,
                status="success"
            ).inc()

            dga_vouchers_received.labels(
                point_id=str(point.id),
                point_name=point.title
            ).inc()

    except Exception as e:
        # REGISTRAR ERROR
        dga_transmission_errors.labels(
            point_id=str(point.id),
            error_code=getattr(e, 'code', 'UNKNOWN'),
            error_type=type(e).__name__
        ).inc()

        dga_transmissions_total.labels(
            point_id=str(point.id),
            point_name=point.title,
            standard_type=standard_type,
            status="failed"
        ).inc()

        raise
"""

print(__doc__)
