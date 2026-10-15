# Seguridad de credenciales en la API (2026-10-02)

## Problema

Varios serializers/endpoints devolvían en claro:

- `token_service` (tokens de dispositivo TDATA / TheThings / Tago / Nettra)
- `auth_password` / `auth_token` de `TelemetryProvider` y `ComplianceProvider`
- `password_dga_software` (clave software DGA)
- `txt_password` / `password` (hash o texto legacy en `User`)

## Cambios

| Endpoint / serializer | Antes | Ahora |
|----------------------|-------|-------|
| `GET/PATCH /api/variable/` | `token_service` en claro | write-only (acepta en POST/PATCH, no sale en GET) |
| `GET/PATCH /api/profile_data_config_catchment/` | `token_service` en claro | write-only |
| `GET/PATCH /api/dga_data_config_catchment/` | `password_dga_software` en claro | write-only |
| `GET /api/telemetry_providers/` | `auth_password`, `auth_token` | ocultos; flags `has_auth_password` / `has_auth_token` |
| `GET /api/compliance_providers/` | `auth_password`, `auth_token` | ocultos; mismos flags |
| Nested `variables` en perfil Ikolu (`VariableConfigSerializer`) | `token_service` | reemplazado por `has_token_service` (bool) |
| `GET /api/users/me/` y serializers de usuario | `password`, `txt_password` | excluidos |

Los serializers **internos de cron** (`CatchmentPointSerializerDetailCron`, `TelemetryProviderInternalSerializer`) **siguen** incluyendo secretos: la telemetría unificada los necesita en proceso, no vía HTTP.

## Excepción intencional (sigue exponiendo tokens)

- `GET /api/ik/agent/points/` — solo staff/superuser. Entrega `token` (`token_service`) a agentes automatizados. Documentado en `docs/API_IKOLU_ENDPOINTS.md`.

## Consumidores que podrían romperse

1. **Frontend / integraciones** que leían `token_service` del GET de `/api/variable/` o `/api/profile_data_config_catchment/` para mostrarlo o reenviarlo. Deben usar admin o PATCH con el valor nuevo (write-only).
2. **UI** que esperaba `token_service` dentro de `config_data.variables` del perfil Ikolu → ahora solo `has_token_service`.
3. **Clientes** de `/api/telemetry_providers/` o `/api/compliance_providers/` que leían `auth_token`/`auth_password` (raro; endpoints pensados para listar metadatos).
4. **Cualquier cliente** de `/api/users/me/` que dependiera de `txt_password` (campo deprecated).

Los writes (POST/PATCH) de tokens/passwords **siguen funcionando**.

## Rotación recomendada

Si estos secretos circularon en respuestas JSON (logs de proxy, navegador, Postman, etc.), conviene rotar de forma genérica:

- Tokens de dispositivo por proveedor (Tago, TheThings, TDATA/Twin, Nettra)
- Passwords / API keys de proveedores de telemetría y compliance
- Contraseñas DGA por punto (`password_dga_software`) y default de sistema (`DGA_DEFAULT_PASSWORD`)
- Cualquier valor legacy en `User.txt_password` (vaciar; las contraseñas reales van hasheadas)

**No** se listan valores aquí a propósito.
