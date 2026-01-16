#!/usr/bin/env python3

# Simulación del caso de Selva Negra
print("=== SIMULACIÓN DEL PROBLEMA DE SELVA NEGRA ===\n")

# Datos simulados basados en tu descripción
nivel_raw_value = 5.2  # valor del nivel que llega desde API
base_calculation = 1.0  # factor de cálculo 
d3_posicionamiento = 4.5  # posicionamiento del sensor (d3)

print(f"📊 DATOS DE ENTRADA:")
print(f"   - Nivel raw value: {nivel_raw_value}")
print(f"   - Base para cálculo: {base_calculation}")
print(f"   - Posicionamiento (d3): {d3_posicionamiento}")

# Simulamos la función nivel_mt actual
def nivel_mt_actual(value, base, point_catchment_id=None, position=None):
    print(f"\n🔍 PROCESANDO CON LÓGICA ACTUAL:")
    calculate = float(value) / float(base)
    print(f"   - Nivel calculado: {calculate:.2f}")
    
    # Lógica problemática actual
    if (calculate < 0 or calculate == 0) and point_catchment_id:
        print("   ❌ Se activaría corrección (nivel negativo o cero)")
        return "{:.2f}".format(0.00)
    
    print(f"   ✅ Nivel válido: {calculate:.2f}")
    return "{:.2f}".format(calculate)

# Simulamos el cálculo del nivel freático
def water_table_actual(value, position):
    print(f"\n💧 CALCULANDO NIVEL FREÁTICO:")
    print(f"   - Fórmula: position - value = {position} - {value}")
    
    if not position or float(position if position else 0) <= 0:
        print(f"   ❌ Error: posición de nivel (d3) no válida: {position}")
        return "00.00"
    
    calculate = float(position) - float(value)
    print(f"   - Nivel freático calculado: {calculate:.2f}")
    
    if calculate < 0:
        print(f"   ⚠️  PROBLEMA: Nivel freático negativo ({calculate:.2f})")
        print(f"   ⚠️  Esto significa que el nivel está SOBRE el posicionamiento")
        return "00.00"
    
    return "{:.2f}".format(calculate)

# CASO 1: Simulación con valores actuales
print("\n" + "="*60)
print("CASO 1: SITUACIÓN ACTUAL (PROBLEMA)")
print("="*60)

nivel_calculado = nivel_mt_actual(nivel_raw_value, base_calculation, 1, d3_posicionamiento)
water_table_result = water_table_actual(nivel_calculado, d3_posicionamiento)

print(f"\n📋 RESULTADO ACTUAL:")
print(f"   - Nivel guardado: {nivel_calculado}")
print(f"   - Water table: {water_table_result}")

if float(water_table_result) == 0.00:
    print(f"   ❌ PROBLEMA: Water table = 0 porque nivel > posicionamiento")

# CASO 2: Propuesta de solución
print("\n" + "="*60)
print("CASO 2: SOLUCIÓN PROPUESTA")
print("="*60)

def nivel_mt_mejorado(value, base, point_catchment_id=None, position=None):
    print(f"\n🔍 PROCESANDO CON LÓGICA MEJORADA:")
    calculate = float(value) / float(base)
    print(f"   - Nivel calculado: {calculate:.2f}")
    
    # Solo corregir niveles REALMENTE negativos
    if calculate < 0 and point_catchment_id:
        print("   ⚠️  Corrigiendo solo niveles negativos")
        # Aplicar corrección...
        return "{:.2f}".format(0.00)
    
    # CAMBIO CLAVE: Permitir niveles 0 y positivos
    print(f"   ✅ Guardando nivel original: {calculate:.2f}")
    return "{:.2f}".format(calculate)

def water_table_mejorado(value, position):
    print(f"\n💧 CALCULANDO NIVEL FREÁTICO (MEJORADO):")
    nivel_numerico = float(value)
    posicion_numerica = float(position if position else 0)
    
    print(f"   - Nivel: {nivel_numerico:.2f}")
    print(f"   - Posición (d3): {posicion_numerica:.2f}")
    
    if posicion_numerica <= 0:
        print(f"   ❌ Error: posición no válida")
        return "00.00"
    
    water_table_calc = posicion_numerica - nivel_numerico
    
    if water_table_calc < 0:
        print(f"   ⚠️  Nivel sobre posicionamiento: {water_table_calc:.2f}")
        print(f"   ✅ SOLUCIÓN: Guardar nivel original y water_table = -1")
        return "-1.00"  # Indicador especial
    
    print(f"   ✅ Nivel freático normal: {water_table_calc:.2f}")
    return "{:.2f}".format(water_table_calc)

nivel_mejorado = nivel_mt_mejorado(nivel_raw_value, base_calculation, 1, d3_posicionamiento)
water_table_mejorado_result = water_table_mejorado(nivel_mejorado, d3_posicionamiento)

print(f"\n📋 RESULTADO MEJORADO:")
print(f"   - Nivel guardado: {nivel_mejorado} (ORIGINAL, no corregido)")
print(f"   - Water table: {water_table_mejorado_result} (indica nivel > posicionamiento)")

print(f"\n✅ VENTAJAS DE LA SOLUCIÓN:")
print(f"   1. Se guarda el nivel original real")
print(f"   2. Water table = -1 indica claramente la situación") 
print(f"   3. No se pierden datos válidos")
print(f"   4. Fácil identificar casos problemáticos")

