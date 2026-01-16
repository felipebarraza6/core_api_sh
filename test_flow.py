
import os
import django
import sys
import json

sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.chatbot.llm import resolve_intent_and_respond, get_conversation_context, clear_conversation_context

USER_ID = "test_flow_user"

print("=== PRUEBA DE FLUJO DE CONTEXTO ===\n")

# 1. Limpiar
clear_conversation_context(USER_ID)

# 2. "iansa mediciones"
print(">>> User: 'iansa mediciones'")
resp1 = resolve_intent_and_respond("iansa mediciones", USER_ID, USER_ID)
print(f"Bot: {resp1[:200]}...")

# 3. "p4" (Simulando selección)
print("\n>>> User: 'p4'")
resp2 = resolve_intent_and_respond("p4", USER_ID, USER_ID)
print(f"Bot: {resp2[:200]}...")

# Verificar contexto
ctx = get_conversation_context(USER_ID)
print(f"\n[Context Check] Last Point: {ctx.get('last_point')}, Last Client: {ctx.get('last_client')}")

# 4. "config" (Debería usar contexto P4)
print("\n>>> User: 'config'")
resp3 = resolve_intent_and_respond("config", USER_ID, USER_ID)
print(f"Bot: {resp3[:300]}...")

if "P4" in resp3: 
    print("\n✅ ÉXITO: Configuración trajo datos de P4.")
else:
    print("\n❌ FALLO: Configuración no trajo P4.")

