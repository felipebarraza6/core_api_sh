# Documentación de Modelos del Sistema SmartHydro

A continuación se detalla la estructura de datos del sistema, organizada por capas lógicas.

## 1. CRM (Gestión de Proyectos y Clientes)
**Ruta:** `api/crm/models.py`
Esta capa gestiona el ciclo de vida comercial y operativo, desde la prospección de clientes hasta la ejecución de proyectos y tareas.

| Modelo | Descripción | Campos Clave | Relaciones (Ejes) |
| :--- | :--- | :--- | :--- |
| **Client** | Entidad comercial (Cliente final). | `name`, `rut`, `status`, `business_type`. | -> `JobPosition`, -> `Project` |
| **Project** | Proyecto de instalación o mantenimiento. | `name`, `status` (PLANNING, ACTIVE...), `start_date`, `budget`. | -> `Client`, -> `contacts` (Person), -> `tasks` (CrmTask), -> `points` (CatchmentPoint) |
| **Person** | Contacto dentro de un proyecto/cliente. | `name`, `email`, `phone`. | -> `Project`, -> `JobPosition` |
| **CrmTask** | Tarea operativa (instalación, visita). | `title`, `priority`, `status`, `due_date`. | -> `Project`, -> `TaskCategory`, -> `assigned_to` (User) |
| **TechnicalSurvey** | Levantamiento técnico inicial en terreno. | `gps_coordinates`, `dynamic_data`, `status`. | -> `Project`, -> `surveyed_by` (User) |

---

## 2. Infraestructura (Hardware)
**Ruta:** `api/infrastructure/models.py`
Gestión de inventario físico. Desacoplado de la lógica de negocio hidrológica.

| Modelo | Descripción | Campos Clave | Relaciones (Ejes) |
| :--- | :--- | :--- | :--- |
| **Manufacturer** | Fabricante del equipo (Ej: Siemens, Nettra). | `name`, `code`, `support_contact`. | -> `DeviceModel` |
| **DeviceModel** | Modelo específico de hardware. | `model_name`, `model_code`. | -> `Manufacturer` |
| **Device** | Unidad física individual (Asset). | `device_id` (UUID), `imei`, `status`, `token`. | -> `DeviceModel`. Es referenciado por `CatchmentPoint` y `CatchmentPointProvider`. |

---

## 3. Configuración (Lógica de Negocio)
**Ruta:** `api/telemetry/models/configuration.py`
Define *cómo* se interpretan los datos. Permite flexibilidad sin cambios de código.

| Modelo | Descripción | Campos Clave | Relaciones (Ejes) |
| :--- | :--- | :--- | :--- |
| **ConfigurationScheme** | Plantilla de configuración (ej: "Pozo Estándar"). | `name`, `code`. | -> `fields` (ConfigurationSchemeField) |
| **ConfigurationSchemeField** | Definición de un parámetro (ej: "diámetro tubería"). | `code`, `data_type` (DECIMAL, TEXT...), `unit`. | -> `ConfigurationScheme` |
| **PointConfigurationValue** | Valor concreto para un punto específico. | `value` (JSON). | -> `CatchmentPoint`, -> `Field` |
| **VariableType** | Definición canónica de variable (Caudal, Nivel). | `code`, `default_unit`. | Usado por `CoreVariable`. |

---

## 4. Ingesta y Proveedores
**Ruta:** `api/telemetry/providers/models.py` y `mqtt_models.py`
Capa de abstracción para la entrada de datos. Normaliza orígenes heterogéneos.

| Modelo | Descripción | Campos Clave | Relaciones (Ejes) |
| :--- | :--- | :--- | :--- |
| **TelemetryProvider** | Fuente de datos externa (API DGA, MQTT Brokér). | `provider_type` (API, MQTT), `base_url`, `auth_config`. | -> `CatchmentPointProvider` |
| **CatchmentPointProvider** | Configuración de enlace Punto <-> Proveedor. | `provider_device_id` (ID externo), `priority`. | -> `CatchmentPoint`, -> `TelemetryProvider` |
| **MQTTProviderConfig** | Configuración específica para Brokers MQTT. | `broker_host`, `topic_template`. | -> `TelemetryProvider` |
| **PayloadParsingRule** | Reglas para decodificar payloads binarios/JSON. | `parsing_method` (JSONPATH, REGEX...), `script`. | -> `MQTTProviderConfig` |

---

## 5. Telemetría (Datos Core)
**Ruta:** `api/telemetry/models/`
El corazón del sistema. Almacena la serie de tiempo unificada y el estado hidrológico.

| Modelo | Descripción | Campos Clave | Relaciones (Ejes) |
| :--- | :--- | :--- | :--- |
| **CatchmentPoint** | Punto de monitoreo (Pozo, Canal). "La entidad principal". | `point_code`, `lat`, `lon`, `is_active`. | -> `Project` (CRM), -> `Device` (Infra), -> `ConfigurationScheme` |
| **CoreVariable** | Variable medida en un punto (Caudal, Nivel). | `internal_code`, `operation` (PHYSICAL, FORMULA). | -> `CatchmentPoint`, -> `VariableType` |
| **TelemetryRecord** | **[Big Data]** Registro de medición unificado. | `timestamp`, `data` (JSON: {flow: 10, total: 100}), `metadata`. | -> `CatchmentPoint`. *Tabla particionable.* |

---

## 6. Compliance (Cumplimiento Normativo) [EN REFACTOR]
**Ruta Actual:** `api/telemetry/providers/compliance_models.py`
**Ruta Destino:** `api/compliance/models.py`
Gestión de reportes regulatorios (DGA, SMA).

| Modelo | Descripción | Campos Clave | Relaciones (Ejes) |
| :--- | :--- | :--- | :--- |
| **ComplianceProvider** | Entidad regulatoria (Ej: DGA). | `service_type`, `api_endpoint`, `rules`. | -> `PointComplianceConfig` |
| **PointComplianceConfig** | Activación de reporte para un punto. | `is_active`, `send_compliance`, `credentials_override`. | -> `CatchmentPoint`, -> `ComplianceProvider` |
| **ComplianceStandard** | Normativa aplicada (Ej: "Caudal Medio"). | `code`, `frequency_rules`. | -> `PointComplianceConfig` |
| **ManualComplianceRecord** | Ingreso manual de datos para reporte. | `measurement_timestamp`, `data`, `voucher`. | -> `PointComplianceConfig` |

---

## Mapa de Contextos

- **Contexto CRM**: Personas, Contratos y Proyectos. Define *quién* es el dueño y *dónde* se opera.
- **Contexto Infraestructura**: Activos físicos. Define *qué hardware* existe.
- **Contexto Configuración**: Reglas de negocio. Define *cómo* se procesa la data.
- **Contexto Ingesta**: Puerta de entrada. Normaliza protocolos externos.
- **Contexto Telemetría**: Serie de tiempo. La "verdad" de los datos hídricos.
- **Contexto Compliance**: Salida Regulatoria. Transforma telemtría en reportes legales.
