
import os
import django
import sys

sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.chatbot.llm import resolve_intent_and_respond
from api.core.chatbot.tools import search_points
from api.core.chatbot.intent_router import get_routed_intent

TEST_QUERIES = [
    "iansa chillan p1 config",
    "configuracion iansa p1",
    "dga fpc",
    "historial p4 iansa",
    "mediciones del dia p1"
]

print("=== DIAGNÓSTICO DE BÚSQUEDA Y NAVEGACIÓN ===\n")

for query in TEST_QUERIES:
    print(f"🔹 Query: '{query}'")
    
    # 1. Router Intent
    intent = get_routed_intent(query)
    print(f"   Router Intent: {intent}")
    
    # 2. Simulación de extracción en llm.py (simplificada)
    import re
    if intent == 'CONFIG':
        clean = re.sub(r'\b(configuracion|configuración|config|parametros)\b', '', query, flags=re.IGNORECASE).strip()
        print(f"   Cleaned Param (CONFIG): '{clean}'")
        points = search_points(clean)
        print(f"   Search Results ({len(points)}): {[p['title'] + ' (' + p['client'] + ')' for p in points[:3]]}")
        
    elif intent == 'HISTORY':
        clean = re.sub(r'\b(historial|datos|registros)\b', '', query, flags=re.IGNORECASE).strip()
        print(f"   Cleaned Param (HISTORY): '{clean}'")
        points = search_points(clean)
        print(f"   Search Results ({len(points)}): {[p['title'] + ' (' + p['client'] + ')' for p in points[:3]]}")
        
    elif intent == 'DGA':
        clean = re.sub(r'\b(dga|normativa|cumplimiento|vouchers)\b', '', query, flags=re.IGNORECASE).strip()
        print(f"   Cleaned Param (DGA): '{clean}'")
        
    # 3. Respuesta Final del LLM Wrapper
    # response = resolve_intent_and_respond(query, "TestUser", "test_id")
    # print(f"   Response Preview: {response[:100]}...")
    print("-" * 40)
