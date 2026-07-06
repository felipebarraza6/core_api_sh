# API Gateway Module

## Proposito

Capa de gateway a nivel de aplicacion que proporciona:
- **Versionado semantico de API**: Migracion gradual entre versiones sin breaking changes
- **Circuit Breaker**: Proteccion contra fallos en cascada de providers externos (DGA, SMA, MQTT)
- **Rate Limiting Multi-Tenant**: Throttling por tenant, endpoint y recurso
- **Request Lifecycle**: Logging estructurado, correlacion de requests y trazabilidad
- **Respuestas Estandarizadas**: Formato uniforme con metadata del gateway

## Arquitectura

```
Cliente → Nginx → Django URL Router → API Gateway → Views/ViewSets
                                          ↓
                                    Circuit Breaker
                                    Rate Limiter
                                    Version Router
                                    Request Logger
```

## Componentes

| Componente | Clase | Proposito |
|-----------|-------|-----------|
| Versioning | `APIVersioningMiddleware` | Enrutamiento por version de API |
| Circuit Breaker | `CircuitBreakerMixin` | Proteccion contra fallos en cascada |
| Rate Limiting | `TenantRateThrottle` | Throttling multi-tenant avanzado |
| Lifecycle | `APIGatewayMiddleware` | Logging y correlacion de requests |
| Responses | `GatewayResponse` | Formato estandarizado de respuestas |

## Integracion

```python
# settings.py
MIDDLEWARE = [
    "api.gateway.middleware.APIGatewayMiddleware",  # Primero en la cadena
    # ... resto de middlewares
]

REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": [
        "api.gateway.throttling.TenantRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_VERSIONING_CLASS": "api.gateway.versioning.APIVersioning",
}
```
