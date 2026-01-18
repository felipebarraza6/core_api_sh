# 🚀 SmartHydro - Inicio Rápido del Sistema de Monitoreo

## ¿Qué es esto?

Sistema de monitoreo en tiempo real para SmartHydro que te permite:

- 📊 Ver métricas de telemetría en dashboards interactivos
- 🔔 Recibir alertas cuando algo falla
- 📈 Analizar tendencias y detectar anomalías
- 🎯 Monitorear DGA, SMA y estado del sistema

## ⚡ Inicio en 3 Pasos

### 1. Levantar el Sistema

```bash
./start_monitoring.sh
```

Espera 10 segundos y listo. El script hace todo automáticamente.

### 2. Abrir Grafana

```
URL: http://localhost:3000
Usuario: admin
Password: smarthydro2026
```

Verás 3 dashboards precargados.

### 3. Explorar los Dashboards

#### 📊 Telemetría General
- Puntos activos vs offline
- Caudal en tiempo real (L/s)
- Totales acumulados (m³)
- Consumo diario
- Última recepción de datos

#### 🏛️ Monitoreo DGA
- Registros pendientes de enviar
- Tasa de transmisiones exitosas
- Errores por tipo
- Vouchers recibidos

#### 💻 Infraestructura
- CPU, Memoria, Disco
- Red y I/O
- Estado de Django

## 🔍 ¿Qué Puedo Hacer?

### Ver Estado en Tiempo Real

Los dashboards se actualizan automáticamente cada 30 segundos. Puedes:

- Hacer zoom en un período específico
- Filtrar por punto o proyecto
- Ver detalles al pasar el mouse sobre las gráficas
- Exportar datos a CSV

### Recibir Alertas

Las alertas se envían automáticamente cuando:

- Un punto lleva >2 horas sin enviar datos
- Hay errores en la ingestión
- Se acumulan >1000 registros DGA pendientes
- CPU/Memoria/Disco >80%
- Django está caído

**Configurar alertas por email:**

Edita `monitoring/alertmanager/alertmanager.yml` y pon tu SMTP:

```yaml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'tu-email@smarthydro.app'
  smtp_auth_username: 'tu-email@smarthydro.app'
  smtp_auth_password: 'TU_PASSWORD'
```

### Crear Queries Personalizadas

En Prometheus (http://localhost:9090):

```promql
# Top 5 puntos con mayor caudal
topk(5, smarthydro_telemetry_flow_liters_per_second)

# Puntos offline ahora mismo
smarthydro_telemetry_last_data_seconds_ago > 7200

# Consumo total del día
sum(smarthydro_telemetry_daily_consumption_cubic_meters)

# Tasa de errores DGA última hora
rate(smarthydro_dga_transmission_errors_total[1h])
```

## 📊 Métricas Disponibles

### Telemetría
- `smarthydro_telemetry_flow_liters_per_second` - Caudal actual
- `smarthydro_telemetry_total_cubic_meters` - Total acumulado
- `smarthydro_telemetry_daily_consumption_cubic_meters` - Consumo diario
- `smarthydro_telemetry_last_data_seconds_ago` - Tiempo sin datos

### DGA
- `smarthydro_dga_pending_records` - Registros pendientes
- `smarthydro_dga_transmissions_total` - Total transmisiones
- `smarthydro_dga_vouchers_received_total` - Vouchers recibidos

### Sistema
- `smarthydro_points_with_data_today` - Puntos activos hoy
- `smarthydro_points_offline` - Puntos sin conexión
- `smarthydro_active_alerts` - Alertas activas

## 🛠️ Comandos Útiles

```bash
# Ver estado
docker-compose -f docker-compose.monitoring.yml ps

# Ver logs de Grafana
docker logs -f smarthydro_grafana

# Ver logs de Prometheus
docker logs -f smarthydro_prometheus

# Detener todo
docker-compose -f docker-compose.monitoring.yml down

# Reiniciar Prometheus (si cambias config)
docker-compose -f docker-compose.monitoring.yml restart prometheus
```

## 🔧 Troubleshooting

### "No data" en los dashboards

1. Verifica que Django está corriendo:
   ```bash
   docker ps | grep django
   ```

2. Verifica el endpoint de métricas:
   ```bash
   curl http://localhost:8000/metrics/ | grep smarthydro
   ```

3. Verifica que Prometheus está scrapeando:
   - Ir a http://localhost:9090/targets
   - Buscar `smarthydro_django`
   - Debe estar **UP** (verde)

### Django no aparece en targets

1. Conectar Django a la red:
   ```bash
   docker network connect smarthydro_network django_api_secure
   ```

2. Reiniciar Prometheus:
   ```bash
   docker-compose -f docker-compose.monitoring.yml restart prometheus
   ```

### Alertas no se envían

1. Edita `monitoring/alertmanager/alertmanager.yml`
2. Configura SMTP correctamente
3. Reinicia Alertmanager:
   ```bash
   docker-compose -f docker-compose.monitoring.yml restart alertmanager
   ```

## 📚 Documentación Completa

Para documentación detallada:

```bash
cat monitoring/README.md
```

Incluye:
- Configuración avanzada de alertas
- Integración con Slack/Teams
- Queries PromQL avanzadas
- Patrones de instrumentación de código
- Exportación de datos históricos

## 🎯 Próximos Pasos

1. **Personalizar Dashboards**
   - Editar en Grafana UI
   - Guardar cambios
   - Exportar JSON si quieres versionarlos

2. **Agregar Alertas Personalizadas**
   - Editar `monitoring/prometheus/alerts.yml`
   - Agregar tus propias reglas
   - Reiniciar Prometheus

3. **Instrumentar Más Código**
   - Ver ejemplos en `api/core/metrics_integration_example.py`
   - Agregar métricas en tu código
   - Ver resultados en Grafana

4. **Backup de Métricas**
   - Prometheus guarda 30 días
   - Para más, configurar remote storage
   - O exportar periódicamente

## 💡 Tips

- **Refresh Rate**: Los dashboards se actualizan cada 30s por defecto. Puedes cambiar esto en Grafana.

- **Time Range**: Por defecto muestra las últimas 6 horas. Cambia el selector de tiempo en la esquina superior derecha.

- **Variables**: Puedes agregar variables en Grafana para filtrar por proyecto, tipo de punto, etc.

- **Alertas Silenciadas**: En Alertmanager (http://localhost:9093) puedes silenciar alertas temporalmente.

- **Export Data**: Cualquier panel se puede exportar a CSV haciendo click en el título → Inspect → Data → Download CSV.

## 🎉 ¡Listo!

Tu sistema de monitoreo está funcionando. Ahora puedes:

✅ Ver el estado de todos tus puntos en tiempo real
✅ Detectar problemas antes de que los usuarios reporten
✅ Analizar tendencias históricas
✅ Recibir alertas proactivas
✅ Tomar decisiones basadas en datos

---

**¿Preguntas?** Lee `monitoring/README.md` para más detalles.

**¿Problemas?** Revisa la sección Troubleshooting arriba.
