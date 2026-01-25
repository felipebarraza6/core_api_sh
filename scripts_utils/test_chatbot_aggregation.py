
import sys
sys.path.append('/app')
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.chatbot.llm import resolve_intent_and_respond

def mock_gemini_response(prompt):
    """Simulate Gemini returning the correct tag for testing logic without burning API credits"""
    if "consume" in prompt.lower() or "consumió" in prompt.lower():
        return "[AGGREGATE:Cliente Test|sum|consumo]"
    if "config" in prompt.lower():
        return "[CONFIG:Cliente Test]"
    return "I don't know"

# Monkey patch google.generativeai for test environment
import api.chatbot.llm as llm_module
class MockModel:
    def __init__(self, system_instruction): pass
    def generate_content(self, prompt):
        class Resp:
            text = mock_gemini_response(prompt)
        return Resp()

class MockGenAI:
    def configure(self, api_key): pass
    GenerativeModel = MockModel

llm_module.genai = MockGenAI()
llm_module.HAS_GEMINI = True
llm_module.settings.GEMINI_API_KEY = "TEST_KEY"

def test_chat():
    print("--- Test Chatbot Aggregation ---")
    query = "Cuanto consumió el Cliente Test hoy?"
    print(f"User: {query}")
    
    # We expect this to trigger [AGGREGATE:...] and call the tool
    resp = resolve_intent_and_respond(query, "Tester")
    print(f"Bot: {resp}")
    
    if "consumo" in resp.lower() and "hoy" in resp.lower():
        print("✅ SUCCESS: Chatbot routed correctly to Aggregation Tool.")
    else:
        print("❌ FAILURE: Chatbot did not respond with metrics.")

if __name__ == "__main__":
    test_chat()
