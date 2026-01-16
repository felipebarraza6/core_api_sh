#!/usr/bin/env python3
import os
import sys
import django

# Configurar Django
sys.path.append('/root/core_api_sh')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')

try:
    django.setup()
    print("✅ Django configurado correctamente")
    
    # Intentar importar y ejecutar el cron de DGA
    from api.cronjobs.dga.cron_dga import run as dga_run
    
    print("🔄 Ejecutando cron DGA manualmente...")
    result = dga_run()
    print(f"✅ Cron DGA ejecutado. Resultado: {result}")
    
except Exception as e:
    print(f"❌ Error ejecutando DGA: {e}")
    import traceback
    traceback.print_exc()
