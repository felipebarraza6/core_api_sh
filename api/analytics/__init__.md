# API Analytics Module

## Proposito

Sistema de analiticas completo para monitoreo de API:
- **Usage Tracking**: Uso por endpoint, tenant, tiempo y recurso
- **Performance Monitor**: Latencia, throughput y tasas de error
- **Health Score**: Scoring proactivo de salud por endpoint
- **Dashboard API**: Endpoints para visualizacion de metricas

## Metricas

### Usage Metrics
- Requests por endpoint (RPM, RPH, RPD)
- Requests por tenant y tier
- Distribucion por metodo HTTP
- Top consumers y endpoints

### Performance Metrics
- Latencia P50, P95, P99 por endpoint
- Throughput (requests/segundo)
- Error rate por endpoint y modulo
- Tendencias de performance

### Health Score
- Score 0-100 por endpoint
- Degradacion gradual con alertas
- Umbrales configurables
- Historial de scores

## Endpoints

| Endpoint | Metodo | Descripcion |
|----------|--------|-------------|
| `/api/analytics/usage/` | GET | Metricas de uso |
| `/api/analytics/performance/` | GET | Metricas de performance |
| `/api/analytics/health/` | GET | Health scores |
| `/api/analytics/dashboard/` | GET | Dashboard consolidado |
