#!/usr/bin/env python3
"""
Ejemplo de cómo migrar un cronjob al sistema dinámico

Muestra cómo reemplazar los getters hardcodeados con el sistema dinámico.
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.providers import get_provider_manager

def get_data_with_dynamic_provider(point_id, variable_type, variable_config):
    """
    Versión migrada que usa el sistema dinámico de proveedores

    Reemplaza la lógica hardcodeada:
    if variable.get("service") == "TWIN":
        data = get_data_tdata(token, variable_name)
    elif variable.get("service") == "NETTRA":
        data = get_data_tago(token, variable_name)
    """
    manager = get_provider_manager()

    # Mapear servicios antiguos a proveedores dinámicos
    service_to_provider = {
        "TWIN": "twin",
        "NETTRA": "nettra",
        "THETHINGS": "nettra",  # TheThings usa la misma API que Nettra
        "NOVUS": "nettra"       # Novus también usa Nettra
    }

    service_name = variable_config.get("service")
    provider_name = service_to_provider.get(service_name)

    if not provider_name:
        print(f"⚠️ Servicio no soportado: {service_name}")
        return {"value": 0, "date_time": None}

    try:
        # Obtener datos usando el sistema dinámico
        result = manager.fetch_point_data(
            point_id=point_id,
            provider_name=provider_name,
            variable_type=variable_config.get("str_variable")
        )

        # El sistema dinámico ya incluye reintentos y manejo de errores
        return {
            "value": result["data"]["value"],
            "date_time": result["data"]["timestamp"].isoformat() if result["data"]["timestamp"] else None
        }

    except Exception as e:
        print(f"❌ Error obteniendo datos dinámicos: {e}")
        return {"value": 0, "date_time": None}


def compare_old_vs_new():
    """Comparación entre sistema antiguo y nuevo"""

    # Configuración de ejemplo (como viene de la BD)
    example_config = {
        "point_id": 1,
        "variables": [
            {
                "service": "TWIN",           # ← Hardcodeado
                "str_variable": "caudal",
                "token_service": "device_123",
                "type_variable": "CAUDAL"
            },
            {
                "service": "NETTRA",         # ← Hardcodeado
                "str_variable": "nivel",
                "token_service": "sensor_456",
                "type_variable": "NIVEL"
            }
        ]
    }

    print("🔄 COMPARACIÓN: Sistema Actual vs Dinámico")
    print("=" * 60)

    for variable in example_config["variables"]:
        print(f"\n📊 Variable: {variable['str_variable']} ({variable['service']})")
        print("-" * 40)

        # Sistema ACTUAL (hardcodeado)
        print("❌ SISTEMA ACTUAL:")
        print(f"   if variable['service'] == '{variable['service']}':")
        if variable['service'] == 'TWIN':
            print("       data = get_data_tdata(token, variable_name)")
        elif variable['service'] == 'NETTRA':
            print("       data = get_data_tago(token, variable_name)")
        print("   ↑ Código hardcodeado, difícil de cambiar")

        # Sistema NUEVO (dinámico)
        print("\n✅ SISTEMA DINÁMICO:")
        print("   data = manager.fetch_point_data(")
        print(f"       point_id={example_config['point_id']},")
        print(f"       provider_name='{variable['service'].lower()}',")
        print(f"       variable_type='{variable['str_variable']}'")
        print("   )")
        print("   ↑ Configurable, extensible, con failover automático")

        print("\n🎯 VENTAJAS DINÁMICO:")
        print("   ✅ Sin código hardcodeado")
        print("   ✅ Múltiples proveedores por punto")
        print("   ✅ Failover automático")
        print("   ✅ Health monitoring")
        print("   ✅ Configuración centralizada")


def main():
    """Función principal"""
    print("📚 MIGRACIÓN DE CRONJOBS - Sistema Actual vs Dinámico")
    print("=" * 60)

    print("\n🎭 SISTEMA LEGACY (ELIMINADO)")
    print("-" * 50)
    print("• Los getters legacy han sido eliminados:")
    print("  ❌ from .getters.tago import get_data_tago (ELIMINADO)")
    print("  ❌ from .getters.tdata import get_data_tdata (ELIMINADO)")
    print("  ❌ from .getters.thingsio import get_data_thethings (ELIMINADO)")
    print()
    print("• El sistema ahora usa solo el sistema dinámico")
    print("• Todos los cronjobs deben usar ProviderManager")

    print("\n🚀 SISTEMA DINÁMICO (Disponible ahora)")
    print("-" * 50)
    print("• Un solo método para todos:")
    print("  manager.fetch_point_data(point_id, provider_name, variable)")
    print()
    print("• Configuración en base de datos:")
    print("  - Proveedores: TelemetryProvider")
    print("  - Config por punto: CatchmentPointProvider")
    print()
    print("• Altamente flexible y escalable")

    print("\n🔄 MIGRACIÓN OPCIONAL")
    print("-" * 50)
    print("• Los cronjobs actuales SIGUEN funcionando")
    print("• Puedes migrar uno por uno cuando quieras")
    print("• Ambos sistemas coexisten perfectamente")
    print("• Sin interrupción del servicio")

    compare_old_vs_new()

    print("\n🎯 CONCLUSIÓN")
    print("-" * 50)
    print("• Los getters antiguos existen porque se usan actualmente")
    print("• El sistema dinámico es una evolución, no reemplazo")
    print("• Puedes migrar gradualmente según tu conveniencia")
    print("• Ambos sistemas son 100% compatibles")


if __name__ == "__main__":
    main()