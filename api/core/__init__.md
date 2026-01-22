# core: __init__ & AI SKILLS

El núcleo del sistema. Contiene los cimientos sobre los que se construyen las demás apps.

## 🎯 Purpose & Scope
Gestión de Usuarios (Auth), Permisos (Roles), Configuración Global del Sistema y Utilidades transversales (Notificaciones, Helpers).

## 🧠 AI Specialist Skills (Mini-Agent Instructions)

Agente, al trabajar aquí, asume el rol de **System Admin & Security Lead**. Debes seguir estas reglas:

| Skill | Description |
| :--- | :--- |
| **Logic Pattern** | Todo modelo nuevo DEBE heredar de `ModelApi` (auditoría automática). |
| **Restriction** | Nunca expongas passwords o tokens en serializers; usa `write_only=True`. |
| **Tooling** | Usa `core/utils/` para notificaciones y utilidades. No reinventes la rueda. |

### 🛠️ Standard Workflows
1. **New Model**: Definir en `models.py` -> Heredar de `ModelApi` -> Registrar en `admin.py` usando `ModelAdminApi`.
2. **Security Audit**: Verificar permisos en `views.py` usando `PermissionClasses` personalizados.

## 🏗️ Core Architecture Components

### Models (Primary Tables)
- **`User`**: Modelo personalizado con email como identificador.
- **`ModelApi`**: Clase abstracta base para `created` y `modified`.

### Key Logic Path
- `core/utils/`: Helpers de sistema, dispatchers de mensajes.

---
*Referencia global: [ROOT_MAP.md](file:///Users/felipebarraza/projects/core_api_sh/api/ROOT_MAP.md)*
