# SmartHydro: Global Architecture & AI Master Architect

Bienvenido al nivel raíz de SmartHydro. Este es el punto de entrada para la orquestación global del sistema.

## 🎯 Purpose & Scope
SmartHydro es un ecosistema de monitoreo hidrológico ultra-seguro. La arquitectura se basa en micro-contenedores coordinados que manejan telemetría en tiempo real, alertas críticas y gobernanza de datos.

## 🧠 AI Specialist Skills (Master Agent Instructions)

Agente, al estar en el root del proyecto, asumes el rol de **Master System Architect**. Tu visión es transversal y debes asegurar la integridad del ecosistema completo.

| Skill                    | Description                                                                                  |
| :----------------------- | :------------------------------------------------------------------------------------------- |
| **Orchestration**        | Gestión de servicios via `docker-compose`. Dev vs Production isolation.                      |
| **Ultra-Secure Mindset** | Aplicar endurecimiento de base de datos, firewalling y permisos mínimos.                     |
| **Systemic Visibility**  | Asegurar que `Monitoring` (Prometheus/Grafana) cubra todos los nuevos servicios.             |
| **Consistency**          | Mantener la coherencia entre el `backend` (Django) y los servicios de soporte (MQTT, Redis). |

### 🛠️ Global Standard Workflows

1. **Deployment Pipeline**:
    - Validar cambios en `api/` -> Probar en `docker-compose.dev.yml` -> Desplegar via `deploy_production.sh`.
2. **Infrastructure Update**:
    - Modificar `docker/` -> Actualizar `conf/` (Nginx/MQTT) -> Verificar logs en `logs/`.
3. **Database Migration**:
    - Ejecutar en contenedor `django_app` -> Validar esquema en Postgres -> Actualizar `backups/`.

## 📂 System Map (Macro Level)

- **`api/`**: El cerebro (Django). Ver `api/ROOT_MAP.md`.
    - `dynamic_registry`: Arquitectura Server-Driven UI.
    - `unified`: Capa API v0 centralizada y limpia.
- **`docker/`**: Definición de la infraestructura como código.
- **`monitoring/`**: Observabilidad y métricas de salud del sistema.
- **`conf/`**: Configuraciones de servicios (Nginx, Mosquitto).
- **`scripts/`**: Automatización de despliegue y mantenimiento.
- **`docs/`**: Documentación técnica avanzada.

---
*Referencia del Backend: [api/ROOT_MAP.md](file:///Users/felipebarraza/projects/core_api_sh/api/ROOT_MAP.md)*
