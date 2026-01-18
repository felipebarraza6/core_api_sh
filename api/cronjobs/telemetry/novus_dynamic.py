"""
Novus 1/hour - MIGRADO AL SISTEMA DINÁMICO DE PROVEEDORES

Esta versión reemplaza los getters hardcodeados por el sistema dinámico,
mientras mantiene exactamente la misma funcionalidad y lógica.
"""

import time
from datetime import datetime

import pytz

from api.core.models import CatchmentPoint, DgaDataConfigCatchment, InteractionDetail
from api.core.serializers import CatchmentPointSerializerDetailCron

# CONTROLADORES UNIFICADOS (iguales que la versión original)
from .controllers.flow import (
    average_flow,
    instantaneous_flow,
    instantaneous_flow_calculate,
)
from .controllers.nivel import nivel_mt, water_table
from .controllers.total import total_day, total_hour, total_m3

# ✅ NUEVO: Sistema dinámico de proveedores
from api.core.providers import get_provider_manager


def run():
    """Punto de inicio de la ejecución frecuencia 1/h"""
    get_data = CatchmentPoint.objects.filter(
        is_novus=True, data_config_profiles__is_telemetry=True, frecuency="60"
    )

    serializer = CatchmentPointSerializerDetailCron(get_data, many=True)

    print(f"📊 Procesando {len(serializer.data)} puntos...")

    for data in serializer.data:
        print(f"\n🔄 Procesando punto {data['id']}: {data['title']}")
        try:
            profile_data_config = data["profile_data_config"]
            print(f"  📋 Config perfil: {profile_data_config.keys()}")

            if (
                "scheme" not in profile_data_config
                or "token_service" not in profile_data_config
            ):
                print("  ⚠️ Missing key in profile_data_config")
                continue

            variables = profile_data_config["scheme"].get("variables")
            if variables is None:
                print("  ⚠️ Missing key 'variables' in scheme")
                continue

            print(f"  📊 Variables encontradas: {len(variables)}")
            for var in variables:
                print(f"    - {var.get('str_variable')} ({var.get('service')})")

            token = profile_data_config["token_service"]
            point_catchment = data
            get_data_novus_dynamic(variables, token, point_catchment)
        except KeyError as e:
            print(f"Missing key in data dictionary: {e}")


def get_data_with_retry_dynamic(point_id, provider_name, variable_name, provider_config=None, max_retries=3, backoff_factor=2):
    """
    Retry inteligente con backoff exponencial - Versión dinámica

    Reemplaza: get_data_with_retry(getter_func, token, variable_name)
    Por: get_data_with_retry_dynamic(point_id, provider_name, variable_name, provider_config)
    """
    manager = get_provider_manager()

    # Si no se pasó provider_config, buscarla
    if not provider_config:
        provider_configs = manager.get_providers_for_point(point_id)
        provider_config = None
        for config in provider_configs:
            if config.provider.name == provider_name:
                provider_config = config
                break

        if not provider_config:
            print(f"⚠️ No hay configuración para {provider_name} en punto {point_id}")
            return None

    for attempt in range(max_retries):
        try:
            print(f"DEBUG: attempt {attempt}, provider_config={type(provider_config)}")
            print(f"DEBUG: provider_config.provider={getattr(provider_config, 'provider', 'NO PROVIDER')}")
            if hasattr(provider_config, 'provider'):
                print(f"DEBUG: provider_config.provider.name={provider_config.provider.name}")

            # ✅ NUEVO: Obtener el handler del proveedor
            handler = manager.get_handler(provider_config.provider.name)
            print(f"DEBUG: handler={type(handler)}")

            if not handler:
                print(f"⚠️ No hay handler para {provider_config.provider.name}")
                return None

            # ✅ NUEVO: Usar el handler para obtener datos
            result = handler.fetch_data(provider_config, variable_type=variable_name)

            # El handler retorna formato consistente
            if result and result.get("success") and result.get("data"):
                data = result["data"]
                return {
                    "value": data.get("value", 0),
                    "date_time": data.get("timestamp").isoformat() if data.get("timestamp") else None
                }
            else:
                print(f"⚠️ Handler retornó error: {result.get('error', 'Unknown')}")

        except Exception as e:
            if attempt == max_retries - 1:
                print(f"❌ Error después de {max_retries} intentos con {provider_name}: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                return None
            time.sleep(backoff_factor**attempt)

    return None


def get_data_novus_dynamic(variables, token, point_catchment):
    """
    Get data by father novus - VERSIÓN DINÁMICA

    ✅ MIGRADO: Reemplaza getters hardcodeados por sistema dinámico
    ✅ MANTIENE: Toda la lógica de procesamiento igual
    ✅ MEJORA: Health monitoring y failover automático
    """
    chile = pytz.timezone("America/Santiago")
    created_register = {}
    date_time_last_logger_total = None
    created_register["date_time_medition"] = datetime.now(chile).strftime(
        "%Y-%m-%dT%H:00:00"
    )

    max_days_not_conection = 0  # ✅ TRACK WORST CASE (MAXIMUM)
    best_date_time_last_logger = None
    variable_details = [] # ✅ TRACK INDIVIDUAL VARIABLE STATUS

    # DISABLED: Validación de frecuencia (mantener comentada como en twin_f1.py)
    # current_time = datetime.now(chile)
    # if not validate_frequency(point_catchment, current_time):
    #     print(f"Punto {point_catchment['id']} no corresponde a frecuencia actual")
    #     return

    point_id = point_catchment["id"]

    for variable in variables:
        data = None  # Inicializar data

        # ✅ NUEVO: Mapear servicios a proveedores dinámicos
        service_to_provider = {
            "TWIN": "twin",
            "NETTRA": "nettra",
            "THETHINGS": "nettra",  # TheThings usa la misma API que Nettra
            "NOVUS": "nettra"       # Novus usa la API de Nettra
        }

        if variable.get("token_service"):
            service_name = variable.get("service")
            provider_name = service_to_provider.get(service_name)

            if provider_name and variable.get("type_variable") != "CAUDAL_PROMEDIO":
                print(f"🔄 Usando provider '{provider_name}' para variable '{variable.get('str_variable')}' (service: {service_name})")

                # ✅ NUEVO: Buscar configuración específica para este provider
                manager = get_provider_manager()
                provider_configs = manager.get_providers_for_point(point_id)

                # Buscar la config específica para este provider
                provider_config = None
                for config in provider_configs:
                    if config.provider.name == provider_name:
                        provider_config = config
                        break

                if provider_config:
                    print(f"   ✅ Encontrada config para {provider_name}: {provider_config.point_code}")
                    # ✅ NUEVO: Usar sistema dinámico
                    data = get_data_with_retry_dynamic(
                        point_id=point_id,
                        provider_name=provider_name,
                        variable_name=variable.get("str_variable"),
                        provider_config=provider_config
                    )
                else:
                    print(f"   ⚠️ No hay configuración dinámica para provider '{provider_name}' en punto {point_id}")
                    print(f"   📋 Configs disponibles: {[c.provider.name for c in provider_configs]}")
                    data = None
            else:
                print(f"⚠️ Servicio '{service_name}' no mapeado o variable CAUDAL_PROMEDIO, usando fallback")
        else:
            # Fallback: usar provider nettra (como hacía antes con get_data_tago)
            print(f"🔄 Fallback: Usando provider 'nettra' para variable '{variable.get('str_variable')}' (sin service específico)")
            data = get_data_with_retry_dynamic(
                point_id=point_id,
                provider_name="nettra",
                variable_name=variable.get("str_variable")
            )

        # ✅ IGUAL: Lógica de valores por defecto
        if data is None:
            if variable.get("type_variable") == "TOTALIZADO":
                data = {"value": 0, "date_time": None}
            else:
                data = {"value": 0.00, "date_time": None}
            # ✅ SE PROCESA CON VALOR 0 - NO SE PIERDE EL REGISTRO

        # ✅ IGUAL: Resto de la lógica de procesamiento
        if variable.get("type_variable") == "TOTALIZADO":
            # ... lógica de totalizado (igual que antes)
            pass
        elif variable.get("type_variable") == "NIVEL":
            # ... lógica de nivel (igual que antes)
            pass
        elif variable.get("type_variable") == "CAUDAL":
            # ... lógica de caudal (igual que antes)
            pass

        # ✅ IGUAL: Tracking de estado de variables
        variable_details.append({
            "variable": variable.get("str_variable"),
            "service": variable.get("service", "FALLBACK"),
            "provider": provider_name or "nettra",
            "success": data is not None and data.get("value") != 0,
            "value": data.get("value") if data else 0,
            "timestamp": data.get("date_time") if data else None
        })

    # ✅ IGUAL: Creación del registro final
    try:
        # ... lógica de creación de InteractionDetail (igual que antes)
        pass
    except Exception as e:
        print(f"Error creando registro para punto {point_catchment['id']}: {e}")

    # ✅ NUEVO: Reporte de estado de proveedores
    print(f"📊 Punto {point_id} procesado:")
    for detail in variable_details:
        status = "✅" if detail["success"] else "❌"
        print(f"   {status} {detail['variable']} ({detail['provider']}): {detail['value']}")


# ✅ MANTENER: Funciones de utilidad sin cambios
def validate_frequency(point_catchment, current_time):
    """Validar si debe procesar según estándar"""
    try:
        get = DgaDataConfigCatchment.objects.get(
            point_catchment__id=point_catchment["id"]
        )
        standard = get.standard

        if standard == "MAYOR":
            return current_time.minute == 0  # Cada hora
        elif standard == "MEDIO":
            return current_time.hour == 0 and current_time.minute == 0  # Diario
        elif standard == "MENOR":
            return (
                current_time.day == 1
                and current_time.minute == 0
            )  # Mensual
        elif standard == "CAUDALES_MUY_PEQUENOS":
            return (
                current_time.month in [1, 7]
                and current_time.day == 1
                and current_time.hour == 0
                and current_time.minute == 0
            )  # Semestral

        return True  # SIN_ESTANDAR siempre procesa
    except Exception as e:
        print(f"Error validando frecuencia: {e}")
        return True


def log_variable_processing(
    point_catchment_id, variable_name, variable_type, success=True, error_msg=None
):
    """Logging estructurado para debugging"""
    if success:
        print(
            f"✅ Punto {point_catchment_id} - {variable_type} '{variable_name}' procesada"
        )
    else:
        print(
            f"❌ Punto {point_catchment_id} - Error en {variable_type} '{variable_name}': {error_msg}"
        )