# Script simple para ejecutar desde el shell de Django
# Copiar y pegar este código en el shell

print("=== EJECUTANDO CRONJOB PARA PUNTO 161 ===")

# Obtener el punto
try:
    punto = CatchmentPoint.objects.get(id=161)
    print(f"✅ Punto encontrado: {punto.title}")
    print(f"   ID: {punto.id}")
    print(f"   Frecuencia: {punto.frecuency} minutos")
except CatchmentPoint.DoesNotExist:
    print("❌ Punto 161 no encontrado")
    exit()

# Obtener el último registro
ultimo_registro = InteractionDetail.objects.filter(
    catchment_point_id=161
).order_by('-created').first()

if ultimo_registro:
    print(f"✅ Último registro encontrado:")
    print(f"   Total: {ultimo_registro.total}")
    print(f"   Fecha: {ultimo_registro.created}")
else:
    print("⚠️  No hay registros previos")

# Simular los datos que llegaron del sensor
# Sabemos que son 55 pulsos con factor 1000
pulsos_recibidos = 55
factor = 1000

print(f"\n=== DATOS DEL SENSOR ===")
print(f"Pulsos recibidos: {pulsos_recibidos}")
print(f"Factor: {factor}")

# Calcular total usando la lógica del cronjob
print(f"\n=== CÁLCULO DEL TOTAL ===")
total_calculado = total_m3(factor, pulsos_recibidos, {'id': 161})
print(f"Total calculado: {total_calculado}")

# Calcular diferencia por hora
if ultimo_registro:
    diferencia_hora = total_hour(total_calculado, {'id': 161})
    print(f"Diferencia por hora: {diferencia_hora}")

# Calcular acumulado del día
acumulado_dia = total_day({'id': 161}, None, None)
print(f"Acumulado del día: {acumulado_dia}")

# Crear el registro manualmente para las 23:00 horas
print(f"\n=== CREANDO REGISTRO PARA 23:00 HORAS ===")

# Configurar zona horaria de Chile
chile_tz = pytz.timezone('America/Santiago')
ahora_chile = datetime.now(chile_tz)

# Crear timestamp para las 23:00 horas
timestamp_23h = ahora_chile.replace(
    hour=23, minute=0, second=0, microsecond=0
)

print(f"Hora actual en Chile: {ahora_chile.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"Timestamp para 23:00: {timestamp_23h.strftime('%Y-%m-%d %H:%M:%S')}")

# Crear el registro
nuevo_registro = InteractionDetail(
    catchment_point_id=161,
    created=timestamp_23h,
    pulses=pulsos_recibidos,
    total=total_calculado,
    total_diff=diferencia_hora if ultimo_registro else 0,
    total_today_diff=acumulado_dia,
    send_dga=True  # Enviar a DGA
)

# Guardar el registro
try:
    nuevo_registro.save()
    print(f"✅ Registro creado exitosamente:")
    print(f"   ID: {nuevo_registro.id}")
    print(f"   Total: {nuevo_registro.total}")
    print(f"   Fecha: {nuevo_registro.created}")
    print(f"   Diferencia hora: {nuevo_registro.total_diff}")
    print(f"   Acumulado día: {nuevo_registro.total_today_diff}")
except Exception as e:
    print(f"❌ Error al crear registro: {e}")

print(f"\n=== VERIFICACIÓN FINAL ===")

# Verificar que el registro se creó correctamente
registro_verificado = InteractionDetail.objects.get(id=nuevo_registro.id)
print(f"Registro verificado en BD:")
print(f"   Total: {registro_verificado.total}")
print(f"   Diferencia: {registro_verificado.total_diff}")

print(f"\n🎯 REGISTRO DE 23:00 HORAS RECUPERADO EXITOSAMENTE!")
print(f"   El punto 161 ahora tiene el total correcto: {registro_verificado.total}")
