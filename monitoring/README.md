# SmartHydro Monitoring

Esta carpeta contiene la configuración para el stack de monitoreo del sistema SmartHydro.

## Archivos

- `prometheus.yml`: Configuración de Prometheus con todos los exporters y jobs de monitoreo
- `grafana-dashboard.json`: Dashboard básico de Grafana para visualizar métricas

## Servicios Monitoreados

- **Django App**: Aplicación principal (puerto 8000)
- **PostgreSQL**: Base de datos con exporter (puerto 9187)
- **Redis**: Cache y message broker con exporter (puerto 9121)
- **Node Exporter**: Métricas del sistema (puerto 9100)
- **Flower**: Monitoreo de tareas Celery (puerto 5555)
- **Grafana**: Dashboard de visualización (puerto 3000)

## Inicio del Stack de Monitoreo

```bash
docker-compose -f docker-compose.monitoring.yml up -d
```

## URLs de Acceso

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- Flower: http://localhost:5555

## Notas

- Las credenciales de Grafana por defecto son admin/admin
- Prometheus está configurado para hacer scrape cada 15 segundos
- Todos los servicios están configurados para funcionar en el entorno de desarrollo