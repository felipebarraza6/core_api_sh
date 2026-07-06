# Milestone 4 — Auth JWT + API REST base + Modelo Project

> Estado: **cerrado** — autenticación JWT, CRUD de puntos/devices/providers/projects y consulta histórica lista.  
> Fecha cierre: 2026-07-06  
> Objetivo: dejar operativo un front nuevo sobre `void` para gestión básica, sin tocar legacy.

---

## 1. Contexto

El **Milestone 3** cerró con compliance multi-frecuencia y puntos superficiales.  
El **Milestone 4** construye los cimientos de API REST de `void` para que un front nuevo pueda operar sobre el nuevo modelo de dominio:

- Autenticación JWT independiente.
- Roles y permisos por punto.
- CRUD de usuarios, proyectos, puntos, dispositivos y proveedores.
- Modelo `Project` real y migración desde campos texto legacy.

---

## 2. Entregables

| Entregable | Estado |
|---|---|
| JWT para void (`/void/auth/*`) | ✅ |
| Roles: admin, operator, client_admin, viewer | ✅ |
| Permisos por punto via `PointPermission` | ✅ |
| Modelo `Project` + migración `Point.client_fk`/`project_fk` | ✅ |
| Viewsets DRF: users, projects, points, devices, providers | ✅ |
| Serializadores y permisos DRF | ✅ |
| `PointService` con filtrado por permisos, resumen y config | ✅ |
| Endpoint `/void/points/<id>/records/` (histórico filtrado) | ✅ |
| Tests de void | ✅ 111/111 OK |
| Documentación actualizada | ✅ |

---

## 3. Modelo de datos

```
User (legacy core.User, USERNAME_FIELD=email)
└── VoidUserProfile (role, timezone, preferences)
    └── PointPermission → PointGroup → Point

Client
├── Project
│   └── Point (client_fk, project_fk)
│       └── Device
│           ├── DeviceVariableConfig
│           ├── DeviceHardware
│           └── Provider (HTTP/MQTT)
│               ├── ProviderEndpoint
│               └── MqttTopicConfig
└── Contract / Subscription / Invoice
```

---

## 4. API

### Auth

| Endpoint | Descripción |
|---|---|
| `POST /void/auth/login/` | email + password → access/refresh |
| `POST /void/auth/refresh/` | refresh → new access |
| `GET /void/auth/me/` | perfil, rol, puntos accesibles |
| `POST /void/auth/change-password/` | cambio de password |

### Gestión

| Endpoint | Descripción |
|---|---|
| `/void/users/` | CRUD perfiles void |
| `/void/projects/` | CRUD proyectos |
| `/void/points/` | CRUD puntos |
| `/void/points/<id>/summary/` | resumen + última lectura |
| `/void/points/<id>/config/` | config + variables del device |
| `/void/points/<id>/records/` | lecturas históricas filtradas |
| `/void/devices/` | CRUD dispositivos |
| `/void/providers/` | CRUD proveedores |

---

## 5. Permisos

| Rol | Alcance |
|---|---|
| `admin` / `operator` | Todo |
| `client_admin` | Ver/editar puntos en grupos asignados |
| `viewer` | Solo ver puntos en grupos asignados |

---

## 6. Migraciones

- `0024_add_project_and_point_project_fk`: crea `Project`, agrega `Point.project_fk`, altera `Point.project` a texto legacy.
- `0025_migrate_project_data`: crea `Client`/`Project` desde texto y asigna FKs.
- `0026_add_project_point_indexes`: índices `client_fk+project_fk+is_active` y `client+is_active`.

---

## 7. Tests

```bash
python manage.py test void.tests --noinput --keepdb
```

Resultado: **111 tests OK**.

---

## 8. Qué NO incluye este milestone

- Throttling específico de void.
- Schema OpenAPI separado para `/void/`.
- Conexión pipeline → compliance auto-send.
- Motor de alertas.
- Backfill real masivo.

---

## 9. Próximos pasos recomendados (Milestone 5)

1. API REST de compliance (authorities, standards, profiles).
2. Conectar `ComplianceService.submit_reading` al pipeline bajo `VOID_AUTOMATION_ENABLED`.
3. Motor de alertas basado en `DeviceEvent` + canales configurables.
4. Reportes async (JSON/XLSX).
