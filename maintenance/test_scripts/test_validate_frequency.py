#!/usr/bin/env python3
"""
Script para verificar validate_frequency
"""

import os
import django
from datetime import datetime
import pytz

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.cronjobs.telemetry.controllers.unified_processing import validate_frequency

def test_validate_frequency():
    print("🔍 VERIFICANDO VALIDATE_FREQUENCY")
    print("=" * 50)
    
    point_catchment = {'id': 161}
    chile_tz = pytz.timezone('America/Santiago')
    
    print("Probando validate_frequency para horas en punto:")
    for hour in [14, 15, 16, 17, 18, 19]:
        check_time = datetime.now(chile_tz).replace(hour=hour, minute=0, second=0, microsecond=0)
        result = validate_frequency(point_catchment, check_time)
        print(f"  {hour}:00 - Resultado: {result}")

if __name__ == "__main__":
    test_validate_frequency()
