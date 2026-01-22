# infrastructure: __init__ & AI SKILLS

Este es un resumen estructural de la aplicación `infrastructure`. Úsalo para gestionar dispositivos físicos e integraciones MQTT.

## 🎯 Purpose & Scope
Gestión de la capa física de IoT: proveedores (Manufacturers), modelos de equipos y dispositivos finales. Maneja la conectividad MQTT y la vinculación de hardware con puntos de captación.

## 🧠 AI Specialist Skills (Mini-Agent Instructions)

Agente, al trabajar en esta carpeta, asume el rol de **IoT & Connectivity Specialist**. Debes seguir estas reglas:

| Skill | Description |
| :--- | :--- |
| **Logic Pattern** | Jerarquía `Manufacturer` -> `DeviceModel` -> `Device`. No crees dispositivos huérfanos. |
| **Restriction** | Todo `Device` DEBE estar vinculado a un `CatchmentPoint`. |
| **Tooling** | Usa `grep_search` para encontrar tópicos MQTT específicos en `telemetry/ingestion`. |

### 🛠️ Standard Workflows
1. **Adding Hardware**: Crear `Manufacturer` -> Definir `DeviceModel` con specs -> Instanciar `Device` con Serial/MAC.
2. **Connectivity Debug**: Verificar `last_seen` en `Device` y estado en `Connection`.

## 🏗️ Core Architecture Components

### Models (Primary Tables)
- **`Manufacturer`**: Define proveedores y sus configs base de MQTT.
- **`DeviceModel`**: Especificaciones técnicas por modelo de equipo.
- **`Device`**: La instancia física (MAC/Serial) instalada en terreno.
- **`Connection`**: Sesiones activas o configuraciones de broker específicas.

### Service Layer / Logic
- **`mqtt_client` (planned)**: Lógica para suscripción y publicación de tópicos.

---
*Referencia global: [ROOT_MAP.md](file:///Users/felipebarraza/projects/core_api_sh/api/ROOT_MAP.md)*
