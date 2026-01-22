# chatbot: __init__ & AI SKILLS

Este es un resumen estructural de la aplicación `chatbot`. Úsalo para gestionar la inteligencia artificial y comandos interactivos.

## 🎯 Purpose & Scope
Interfaz de lenguaje natural (LLM) que permite a los usuarios consultar datos de telemetría, estados de proyectos y realizar comandos via chat o slash commands.

## 🧠 AI Specialist Skills (Mini-Agent Instructions)

Agente, al trabajar en esta carpeta, asume el rol de **AI & Chatbot Engineer**. Debes seguir estas reglas:

| Skill | Description |
| :--- | :--- |
| **Logic Pattern** | El chatbot NO accede a la DB directamente; usa herramientas en `tools.py`. |
| **Restriction** | Los prompts en `llm.py` son sagrados. No los modifiques sin validar el `system_instruction`. |
| **Tooling** | Usa `view_code_item` en `tools.py` para entender qué funciones puede llamar el LLM. |

### 🛠️ Standard Workflows
1. **New AI Capability**: Definir función en `tools.py` -> Registrarla en `llm.py` -> Probar via `ChatView`.
2. **Intent Debugging**: Revisar logs de `intent_router.py` para ver por qué falla la clasificación.

## 🏗️ Core Architecture Components

### Key Logic Files
- **`tools.py`**: El puente entre el LLM y el resto de la API de SmartHydro.
- **`intent_router.py`**: Clasifica lo que el usuario quiere (ej: "Ver caudal" vs "Crear ticket").
- **`llm.py`**: Integración con proveedores de modelos (Gemini/OpenAI).
- **`slash_commands.py`**: Implementación de comandos rápidos (ej: `/report`).

### Service Layer / Logic
- **`cache.py`**: Manejo de sesiones y contexto histórico del chat.
- **`metrics.py`**: Tracking de tokens y performance del bot.

---
*Referencia global: [ROOT_MAP.md](file:///Users/felipebarraza/projects/core_api_sh/api/ROOT_MAP.md)*
