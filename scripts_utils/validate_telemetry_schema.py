"""
Script de validación rápida de la implementación del sistema dinámico.

Ejecutar con: python manage.py shell < api/telemetry/validate_implementation.py
"""

from api.telemetry.models.configuration import (
    ConfigurationScheme,
    ConfigurationSchemeField,
    PointConfigurationValue,
    SamplingFrequency,
    VariableType,
)
from api.telemetry.models.catchment_points import CatchmentPoint
from api.telemetry.models.telemetry import CoreVariable
from api.telemetry.processing import FormulaEngine

print("=" * 60)
print("VALIDACIÓN DE IMPLEMENTACIÓN - SISTEMA DINÁMICO")
print("=" * 60)

# 1. Verificar modelos
print("\n1. Verificando modelos...")
try:
    assert hasattr(ConfigurationScheme, 'fields')
    assert hasattr(ConfigurationSchemeField, 'scheme')
    assert hasattr(PointConfigurationValue, 'point')
    assert hasattr(PointConfigurationValue, 'field')
    assert hasattr(SamplingFrequency, 'code')
    assert hasattr(VariableType, 'default_formula')
    print("   ✅ Todos los modelos están correctamente definidos")
except AssertionError as e:
    print(f"   ❌ Error en modelos: {e}")

# 2. Verificar CatchmentPoint
print("\n2. Verificando CatchmentPoint...")
try:
    assert hasattr(CatchmentPoint, 'configuration_scheme')
    assert hasattr(CatchmentPoint, 'frequency')
    assert hasattr(CatchmentPoint, 'get_config_dict')
    print("   ✅ CatchmentPoint tiene los nuevos campos y métodos")
except AssertionError as e:
    print(f"   ❌ Error en CatchmentPoint: {e}")

# 3. Verificar CoreVariable
print("\n3. Verificando CoreVariable...")
try:
    assert hasattr(CoreVariable, 'type_definition')
    assert hasattr(CoreVariable, 'formula')
    # Verificar que formula tiene suficiente longitud
    field = CoreVariable._meta.get_field('formula')
    assert field.max_length >= 1000
    print("   ✅ CoreVariable tiene type_definition y formula mejorada")
except AssertionError as e:
    print(f"   ❌ Error en CoreVariable: {e}")

# 4. Verificar FormulaEngine
print("\n4. Verificando FormulaEngine...")
try:
    assert hasattr(FormulaEngine, 'evaluate')
    assert hasattr(FormulaEngine, 'process_variable')
    assert hasattr(FormulaEngine, 'get_formula_for_variable')
    print("   ✅ FormulaEngine tiene todos los métodos necesarios")
except AssertionError as e:
    print(f"   ❌ Error en FormulaEngine: {e}")

# 5. Verificar imports
print("\n5. Verificando imports...")
try:
    from api.telemetry.models import (
        ConfigurationScheme,
        SamplingFrequency,
        VariableType,
    )
    print("   ✅ Imports desde __init__.py funcionan correctamente")
except ImportError as e:
    print(f"   ❌ Error en imports: {e}")

print("\n" + "=" * 60)
print("VALIDACIÓN COMPLETA")
print("=" * 60)
print("\nSi todos los checks pasaron, puedes proceder con:")
print("  1. python manage.py makemigrations telemetry")
print("  2. python manage.py migrate")
print("  3. python manage.py migrate_to_dynamic")
