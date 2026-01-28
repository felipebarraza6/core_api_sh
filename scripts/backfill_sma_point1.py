"""
Script de Backfill para SMA (Punto 1 - PC Descarga)
--------------------------------------------------
Envía registros pendientes a la SMA ignorando la restricción de tiempo de 2 horas.
"""
import os
import sys
import django
import time
from datetime import datetime

# Configurar Django
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, DgaDataConfigCatchment
# Importar funciones internas del cron existente para reutilizar lógica
from api.cronjobs.sma.cron_sma import _get_sma_token, _send_to_sma, _prepare_response_data, _validate_register

def run_backfill():
    print("🚀 Iniciando Backfill SMA para Punto 1...")
    
    # 1. Obtener Token
    token = _get_sma_token()
    if not token:
        print("❌ Error crítico: No se pudo obtener token SMA.")
        return

    # 2. Buscar registros pendientes (sin voucher) del Punto 1
    # CRÍTICO: Filtramos SOLO 2026 en adelante según instrucción del usuario
    qs = InteractionDetail.objects.filter(
        catchment_point_id=1,
        n_voucher__isnull=True,
        date_time_medition__year__gte=2026
    ).order_by('date_time_medition')
    
    total_count = qs.count()
    print(f"📊 Total registros pendientes encontrados: {total_count}")
    
    if total_count == 0:
        print("✅ Nada que procesar.")
        return

    # Obtener configuración una sola vez
    dga_config = DgaDataConfigCatchment.objects.filter(point_catchment_id=1).first()
    if not dga_config:
        print("❌ Error: No hay configuración DGA para el punto 1")
        return

    success_count = 0
    error_count = 0
    
    # 3. Procesar en lotes para no saturar memoria ni API
    # Usamos iterator() para manejo eficiente de memoria
    for i, register in enumerate(qs.iterator(), 1):
        try:
            # Filtro estricto de minutos (0, 5, 10...)
            # Replicamos la lógica del cron para no enviar basura
            if not register.date_time_medition:
                continue
                
            # Ajuste de zona horaria si es necesario (el modelo ya debería tenerlo o ser aware)
            # En el cron original hacen un chequeo de modulo 5
            dt = register.date_time_medition
            if dt.minute % 5 != 0:
                print(f"⚠️ Salteando registro {register.id}: minuto {dt.minute} no es múltiplo de 5")
                continue

            print(f"📋 [{i}/{total_count}] Procesando ID {register.id} ({dt})")

            # Preparar datos
            response_data = _prepare_response_data(register, dga_config)
            if not response_data:
                print(f"❌ Error preparando datos ID {register.id}")
                error_count += 1
                continue

            # Enviar
            success, msg, id_verificacion = _send_to_sma(response_data, token, dga_config)
            
            if success:
                print(f"✅ Enviado! Voucher: {id_verificacion}")
                register.n_voucher = id_verificacion
                register.return_dga = msg
                register.send_dga = False # Asegurar que quede limpio
                register.is_error = False
                register.save()
                success_count += 1
            else:
                print(f"❌ Falló envío: {msg}")
                register.return_dga = msg
                register.is_error = True
                register.save()
                error_count += 1
            
            # Pequeña pausa para no ser rate-limited agresivamente
            time.sleep(0.5)

        except Exception as e:
            print(f"💥 Excepción en registro {register.id}: {e}")
            error_count += 1

    print("="*40)
    print(f"🏁 RESUMEN BACKFILL")
    print(f"✅ Exitosos: {success_count}")
    print(f"❌ Errores: {error_count}")
    print("="*40)

if __name__ == '__main__':
    run_backfill()
