# Auditoría de Coherencia App-por-App

Documento vivo de análisis para depuración profunda del sistema.

## 1. App: `api/core` (Nucleo)

| Elemento                         | Estado       | Observación                                                                         | Acción Recomendada                                    |
| :------------------------------- | :----------- | :---------------------------------------------------------------------------------- | :---------------------------------------------------- |
| `models/users.py`                | ✅ OK         | Modelo de usuario robusto (AbstractUser).                                           | Mantener.                                             |
| `mqtt_broker.py`                 | ⚠️ Misplaced  | Implementación de Broker embebido. Debería estar en `telemetry` o `infrastructure`. | Mover a `api/infrastructure/mqtt/` (Refactor futuro). |
| `chatbot/` (Folder)              | 🔴 Redundante | Carpeta VACÍA. El chatbot real vive en `api/chatbot/`.                              | **ELIMINAR**.                                         |
| `metrics_integration_example.py` | 🗑️ Basura     | Archivo de ejemplo/demo. No código productivo.                                      | **ELIMINAR**.                                         |
| `admin_enhanced.py`              | ✅ OK         | Personalización del Admin. Útil.                                                    | Mantener.                                             |

### Conclusión App 1
`api/core` está sólida pero tiene "ruido" (carpetas vacías y ejemplos) que confunden la navegación.

---

## 2. App: `api/telemetry` (Negocio Principal)

| Elemento                    | Estado     | Observación                                     | Acción Recomendada                                                  |
| :-------------------------- | :--------- | :---------------------------------------------- | :------------------------------------------------------------------ |
| `ingestion/DEPRECATED_*.md` | ⚠️ Ruido    | Archivos de texto indicando qué borrar.         | **Borrar archivos si ya se completó**.                              |
| `ingestion/controllers`     | ✅ OK       | Estructura unificada.                           | Mantener.                                                           |
| `providers/mqtt_*.py`       | ✅ Vital    | Implementación real de MQTT (Handlers, Models). | Mantener. Confirma que el `broker.py` de Core es redundante/legacy. |
| `admin_*.py` (Multiple)     | ⚠️ Complejo | Lógica de admin fragmentada en 4 archivos.      | Unificar en package `telemetry/admin/` a futuro.                    |
| `*.md` (Root)               | ℹ️ Docs     | 5 archivos de documentación en raíz de app.     | Mover a `documents/` o `wiki/`.                                     |

### Conclusión App 2
Telemetry es monolítica y contiene mucha documentación mezclada con código. Funcionalmente parece coherente (Estructura Providers/Ingestion clara), pero visualmente está sucia.

---

## 3. App: `api/compliance` (Normativa DGA/SMA)

| Elemento               | Estado        | Observación                                                  | Acción Recomendada        |
| :--------------------- | :------------ | :----------------------------------------------------------- | :------------------------ |
| `models.py`            | ✅ Vital       | 23KB de lógica normativa y tablas de reportes.               | Mantener.                 |
| `admin.py`             | ✅ Vital       | Única interfaz actual de gestión.                            | Mantener.                 |
| `views.py` / `urls.py` | 🔴 **MISSING** | **NO EXISTEN**. El módulo es invisible para el Frontend/API. | **CREAR** (Próximo paso). |

### Conclusión App 3
Es un "Módulo Silencioso". Existe en DB y Admin, pero no tiene API. Esto es un bloqueo para cualquier Dashboard de Cumplimiento.

---

## 4. App: `api/infrastructure` (Inventario Físico)

| Elemento    | Estado  | Observación                  | Acción Recomendada                                                                  |
| :---------- | :------ | :--------------------------- | :---------------------------------------------------------------------------------- |
| `models.py` | ✅ OK    | Catálogo de activos físicos. | Mantener.                                                                           |
| `mqtt/`     | ❌ Falta | No existe carpeta MQTT aquí. | Debería recibir el `mqtt_broker.py` de Core.                                        |
| `views.py`  | ℹ️ N/A   | No tiene vistas propias.     | Aceptable si solo es consumida por Telemetry (relation `CatchmentPoint -> Device`). |

### Conclusión App 4
Funciona correctamente como un "Diccionario de Hardware" pasivo. No necesita API compleja propia.


