# SmartHydro - Sistema de Monitoreo con Prometheus y Grafana

Sistema completo de monitoreo en tiempo real para SmartHydro, con métricas de telemetría, DGA, alertas e infraestructura.

## 📊 Componentes

### 1. **Prometheus** (Puerto 9090)
- Recolecta métricas cada 30 segundos de Django
- Almacena datos históricos por 30 días
- Evalúa reglas de alertas cada minuto
- Expone interfaz web en http://localhost:9090

### 2. **Grafana** (Puerto 3000)
- Visualización de métricas con dashboards interactivos
- Usuario: `admin`
- Password: `smarthydro2026`
- URL: http://localhost:3000

### 3. **Alertmanager** (Puerto 9093)
- Gestión inteligente de alertas
- Notificaciones por email
- Agrupación y deduplicación de alertas
- URL: http://localhost:9093

### 4. **Node Exporter** (Puerto 9100)
- Métricas del sistema operativo (CPU, memoria, disco, red)
- Se ejecuta en el host

## 🚀 Deployment

### Paso 1: Instalar Dependencias

```bash
# En el contenedor Django o entorno local
pip install prometheus-client>=0.15.0
```

Ya está incluido en `requirements.txt`.

### Paso 2: Configurar Email para Alertas

Editar `monitoring/alertmanager/alertmanager.yml`:

```yaml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'notify@smarthydro.app'
  smtp_auth_username: 'notify@smarthydro.app'
  smtp_auth_password: 'YOUR_EMAIL_PASSWORD'  # ⚠️ CAMBIAR
  smtp_require_tls: true

receivers:
  - name: 'default-receiver'
    email_configs:
      - to: 'admin@smarthydro.app'  # ⚠️ CAMBIAR
```

### Paso 3: Levantar Servicios de Monitoreo

```bash
# Crear red Docker si no existe
docker network create smarthydro_network

# Levantar stack de monitoreo
docker-compose -f docker-compose.monitoring.yml up -d

# Verificar que todos los servicios estén corriendo
docker-compose -f docker-compose.monitoring.yml ps
```

Deberías ver:
- `smarthydro_prometheus` - UP
- `smarthydro_grafana` - UP
- `smarthydro_alertmanager` - UP
- `smarthydro_node_exporter` - UP

### Paso 4: Conectar Django a la Red

Si Django ya está corriendo, conéctalo a la red de monitoreo:

```bash
# Conectar contenedor Django existente
docker network connect smarthydro_network django_api_secure

# O agregar a docker-compose.production.secure.yml:
networks:
  smarthydro_network:
    external: true
```

### Paso 5: Verificar Endpoint de Métricas

```bash
# Verificar que Django expone métricas
curl http://localhost:8000/metrics/

# Deberías ver métricas como:
# smarthydro_telemetry_flow_liters_per_second{point_id="137",point_name="PC Descarga"} 3.34
# smarthydro_telemetry_total_cubic_meters{point_id="137",point_name="PC Descarga"} 344270
```

### Paso 6: Acceder a Grafana

1. Abrir http://localhost:3000
2. Login: `admin` / `smarthydro2026`
3. Los dashboards se cargan automáticamente:
   - **SmartHydro - Telemetría General**
   - **SmartHydro - Monitoreo DGA**
   - **SmartHydro - Infraestructura**

## 📈 Métricas Disponibles

### Telemetría

| Métrica | Tipo | Descripción |
|---------|------|-------------|
| `smarthydro_telemetry_flow_liters_per_second` | Gauge | Caudal actual en L/s por punto |
| `smarthydro_telemetry_total_cubic_meters` | Gauge | Total acumulado en m³ por punto |
| `smarthydro_telemetry_nivel_meters` | Gauge | Nivel de agua en metros |
| `smarthydro_telemetry_daily_consumption_cubic_meters` | Gauge | Consumo diario en m³ |
| `smarthydro_telemetry_last_data_seconds_ago` | Gauge | Segundos desde última recepción |
| `smarthydro_telemetry_ingestion_total` | Counter | Total de registros ingestados |
| `smarthydro_telemetry_ingestion_errors_total` | Counter | Errores de ingestión |
| `smarthydro_telemetry_processing_duration_seconds` | Histogram | Tiempo de procesamiento |

### DGA

| Métrica | Tipo | Descripción |
|---------|------|-------------|
| `smarthydro_dga_pending_records` | Gauge | Registros pendientes de enviar |
| `smarthydro_dga_transmissions_total` | Counter | Total de transmisiones DGA |
| `smarthydro_dga_transmission_errors_total` | Counter | Errores en transmisión |
| `smarthydro_dga_vouchers_received_total` | Counter | Vouchers DGA recibidos |

### Sistema

| Métrica | Tipo | Descripción |
|---------|------|-------------|
| `smarthydro_points_total` | Gauge | Total de puntos por estado |
| `smarthydro_points_with_data_today` | Gauge | Puntos activos hoy |
| `smarthydro_points_offline` | Gauge | Puntos sin datos >2h |
| `smarthydro_active_alerts` | Gauge | Alertas activas por punto |
| `smarthydro_database_records_total` | Gauge | Registros en BD |

### Infraestructura (Node Exporter)

- CPU: `node_cpu_seconds_total`
- Memoria: `node_memory_*`
- Disco: `node_filesystem_*`
- Red: `node_network_*`
- I/O: `node_disk_*`

## 🔔 Alertas Configuradas

### Telemetría

1. **PointOffline** (Warning)
   - Trigger: Punto sin datos >2 horas
   - For: 5 minutos

2. **PointCriticalOffline** (Critical)
   - Trigger: Punto sin datos >24 horas
   - For: 10 minutos

3. **HighIngestionErrorRate** (Warning)
   - Trigger: >0.1 errores/segundo
   - For: 5 minutos

4. **AbnormalFlowRate** (Warning)
   - Trigger: Caudal >1000 L/s
   - For: 5 minutos

5. **HighDailyConsumption** (Info)
   - Trigger: Consumo >50,000 m³/día
   - For: 10 minutos

### DGA

1. **DGAPendingRecordsHigh** (Warning)
   - Trigger: >1000 registros pendientes
   - For: 30 minutos

2. **DGAPendingRecordsCritical** (Critical)
   - Trigger: >5000 registros pendientes
   - For: 1 hora

3. **DGATransmissionErrors** (Warning)
   - Trigger: >0.05 errores/segundo
   - For: 15 minutos

### Sistema

1. **LowActivePoints** (Warning)
   - Trigger: <5 puntos activos hoy
   - For: 1 hora

2. **MultiplePointsOffline** (Critical)
   - Trigger: >10 puntos offline
   - For: 30 minutos

### Infraestructura

1. **HighCPUUsage** (Warning)
   - Trigger: CPU >80%
   - For: 5 minutos

2. **HighMemoryUsage** (Warning)
   - Trigger: Memoria >85%
   - For: 5 minutos

3. **HighDiskUsage** (Warning)
   - Trigger: Disco >80%
   - For: 5 minutos

4. **DjangoDown** (Critical)
   - Trigger: Django no responde
   - For: 1 minuto

## 🔧 Uso Programático

### Incrementar Contadores desde Código

```python
from api.core.metrics import (
    telemetry_ingestion_total,
    telemetry_ingestion_errors,
    dga_transmissions_total
)

# Éxito en ingestión
telemetry_ingestion_total.labels(
    point_id=137,
    point_name="PC Descarga",
    provider="TWIN"
).inc()

# Error en ingestión
telemetry_ingestion_errors.labels(
    point_id=137,
    point_name="PC Descarga",
    error_type="connection_timeout"
).inc()

# Transmisión DGA exitosa
dga_transmissions_total.labels(
    point_id=137,
    point_name="PC Descarga",
    standard_type="MAYOR",
    status="success"
).inc()
```

### Actualizar Gauges

```python
from api.core.metrics import (
    telemetry_flow_current,
    telemetry_total_current,
    dga_pending_records
)

# Actualizar caudal
telemetry_flow_current.labels(
    point_id=137,
    point_name="PC Descarga",
    project="Proyecto A"
).set(12.5)  # L/s

# Actualizar total
telemetry_total_current.labels(
    point_id=137,
    point_name="PC Descarga",
    project="Proyecto A"
).set(344270)  # m³

# Actualizar registros pendientes DGA
dga_pending_records.labels(
    point_id=137,
    point_name="PC Descarga",
    standard_type="MAYOR"
).set(245)
```

### Medir Tiempos de Procesamiento

```python
from api.core.metrics import telemetry_processing_duration
import time

# Usando como context manager
with telemetry_processing_duration.labels(point_id=137, provider="TWIN").time():
    # Tu código de procesamiento
    process_telemetry_data(point_id=137)

# O manualmente
start = time.time()
process_telemetry_data(point_id=137)
duration = time.time() - start
telemetry_processing_duration.labels(point_id=137, provider="TWIN").observe(duration)
```

## 📊 Queries PromQL Útiles

### Top 10 puntos con mayor caudal
```promql
topk(10, smarthydro_telemetry_flow_liters_per_second)
```

### Puntos offline hace más de 1 hora
```promql
smarthydro_telemetry_last_data_seconds_ago > 3600
```

### Consumo total diario de todos los puntos
```promql
sum(smarthydro_telemetry_daily_consumption_cubic_meters)
```

### Tasa de errores DGA en la última hora
```promql
rate(smarthydro_dga_transmission_errors_total[1h])
```

### Porcentaje de éxito en transmisiones DGA
```promql
sum(rate(smarthydro_dga_transmissions_total{status="success"}[5m]))
/
sum(rate(smarthydro_dga_transmissions_total[5m])) * 100
```

### Proyección de crecimiento de BD (7 días)
```promql
predict_linear(smarthydro_database_records_total{table="telemetry_records"}[7d], 7*24*3600)
```

## 🎯 Dashboards Incluidos

### 1. Telemetría General (`telemetry_overview.json`)

- **Métricas Clave**: Puntos activos, offline, alertas activas, total registros
- **Gráficos en Tiempo Real**:
  - Caudal (L/s) por punto
  - Total acumulado (m³) por punto
  - Consumo diario (m³/día)
- **Tabla de Estado**: Segundos desde última recepción por punto

### 2. Monitoreo DGA (`dga_monitoring.json`)

- **Métricas Clave**: Registros pendientes, transmisiones exitosas, errores
- **Gráficos**:
  - Registros pendientes por punto y estándar
  - Tasa de transmisiones por estado
  - Errores por tipo
- **Tabla**: Registros pendientes detallados

### 3. Infraestructura (`infrastructure.json`)

- **Gauges**: CPU, Memoria, Disco, Estado Django
- **Gráficos**:
  - Histórico de CPU
  - Uso de memoria
  - Tráfico de red
  - I/O de disco

## 🔄 Integración con Telemetría

El exportador de métricas se actualiza automáticamente cada vez que Prometheus hace scraping (cada 30s).

Para forzar actualización manual:

```python
from api.core.metrics import update_all_metrics

# Actualizar todas las métricas
update_all_metrics()
```

O desde bash:

```bash
# En desarrollo
docker exec smarthydro_django_dev python -c "
from api.core.metrics import update_all_metrics
update_all_metrics()
"

# En producción
docker exec django_api_secure python -c "
from api.core.metrics import update_all_metrics
update_all_metrics()
"
```

## 🛠️ Troubleshooting

### Prometheus no encuentra Django

```bash
# Verificar que Django está en la red correcta
docker network inspect smarthydro_network

# Debería listar django_api_secure o smarthydro_django_dev
```

### Grafana no muestra datos

1. Verificar datasource en Grafana:
   - Settings → Data Sources → Prometheus
   - URL debe ser `http://prometheus:9090`
   - Click "Save & Test" debe mostrar "Data source is working"

2. Verificar que Prometheus está scrapeando:
   - Ir a http://localhost:9090/targets
   - Target `smarthydro_django` debe estar UP

### Alertas no se envían

1. Verificar configuración de email en `alertmanager.yml`
2. Ver logs de Alertmanager:
   ```bash
   docker logs smarthydro_alertmanager
   ```
3. Probar envío manual desde Alertmanager UI (http://localhost:9093)

### Métricas no aparecen

1. Verificar endpoint Django:
   ```bash
   curl http://localhost:8000/metrics/ | grep smarthydro
   ```

2. Ver logs de Django:
   ```bash
   docker logs django_api_secure | grep metrics
   ```

3. Verificar que prometheus-client está instalado:
   ```bash
   docker exec django_api_secure pip list | grep prometheus
   ```

## 📝 Comandos Útiles

```bash
# Ver todos los servicios de monitoreo
docker-compose -f docker-compose.monitoring.yml ps

# Ver logs
docker-compose -f docker-compose.monitoring.yml logs -f prometheus
docker-compose -f docker-compose.monitoring.yml logs -f grafana
docker-compose -f docker-compose.monitoring.yml logs -f alertmanager

# Reiniciar servicios
docker-compose -f docker-compose.monitoring.yml restart prometheus
docker-compose -f docker-compose.monitoring.yml restart grafana

# Detener todo el stack
docker-compose -f docker-compose.monitoring.yml down

# Detener y eliminar volúmenes (⚠️ borra datos históricos)
docker-compose -f docker-compose.monitoring.yml down -v

# Recargar configuración de Prometheus sin reiniciar
curl -X POST http://localhost:9090/-/reload

# Recargar configuración de Alertmanager
curl -X POST http://localhost:9093/-/reload
```

## 📚 Referencias

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PromQL Cheat Sheet](https://promlabs.com/promql-cheat-sheet/)
- [Node Exporter](https://github.com/prometheus/node_exporter)

## 🔐 Seguridad

**Recomendaciones para Producción**:

1. **Cambiar credenciales de Grafana**:
   ```yaml
   environment:
     - GF_SECURITY_ADMIN_PASSWORD=CONTRASEÑA_SEGURA
   ```

2. **Usar autenticación en Prometheus**:
   - Agregar `basic_auth` en prometheus.yml

3. **Exponer solo mediante reverse proxy**:
   - Nginx con SSL/TLS
   - Autenticación básica HTTP

4. **Limitar acceso por firewall**:
   - Solo IPs autorizadas pueden acceder a puertos 9090, 3000, 9093

5. **Rotar credenciales de email regularmente**

6. **Usar secretos de Docker en lugar de variables de entorno**

## 🎓 Próximos Pasos

1. **Integrar con Slack/Teams**: Agregar webhooks en Alertmanager
2. **Métricas de Celery**: Exportar métricas de workers y tareas
3. **Postgres Exporter**: Monitorear queries, conexiones, locks
4. **Backup Automático**: Exportar métricas a S3 para análisis histórico
5. **Machine Learning**: Predicción de anomalías con Prophet
6. **Dashboards Personalizados**: Crear vistas por proyecto/cliente
