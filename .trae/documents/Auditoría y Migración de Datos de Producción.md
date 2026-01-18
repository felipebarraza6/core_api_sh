# Plan de Auditoría, Migración y Puesta en Marcha

Este plan detalla los pasos para auditar el sistema, proporcionar credenciales, crear un superusuario y migrar los datos de producción desde SQLite a la base de datos de desarrollo.

## 1. Auditoría y Credenciales
Se recopilarán y presentarán todas las credenciales del sistema para facilitar el acceso:
- **Django Admin**: `http://localhost:8000/admin/`
- **PostgreSQL**: `smarthydro_dev` / `smarthydro_dev_user` / `dev_password_123`
- **Redis**: `redis://redis:6379/0`
- **MQTT Broker**: `smarthydro` / `dev_mqtt_password` (Puertos 1883, 8883)
- **Grafana**: `admin` / `admin123` (`http://localhost:3000`)
- **Flower**: `user` / `password` (`http://localhost:5555`)
- **Prometheus**: `http://localhost:9090`

## 2. Correcciones de Infraestructura
- Corregir el archivo `conf/mosquitto.conf` para resolver el error de inicio del broker MQTT (cambiar `message_size_limit` por `max_packet_size` y ajustar valor).
- Reiniciar el servicio MQTT.

## 3. Gestión de Usuarios
- Crear un superusuario inicial para el acceso al panel de administración:
  - **Email**: `admin@smarthydro.cl`
  - **Password**: `admin123`

## 4. Migración de Datos (SQLite a PostgreSQL)
Para mover los datos de producción de `dev_database.sqlite3` a PostgreSQL:
1. Crear un script de migración en Python (`api/migrate_production_data.py`).
2. El script usará el ORM de Django para:
   - Leer registros de `core_client`, `core_catchmentpoint` y `core_interactiondetail` desde SQLite.
   - Insertar o actualizar dichos registros en PostgreSQL.
   - Manejar las relaciones entre tablas para mantener la integridad.
3. Ejecutar el script dentro del contenedor `smarthydro_django_dev`.
4. Verificar la carga de datos mediante consultas rápidas al ORM.

## 5. Validación Final
- Realizar pruebas de conectividad a todos los endpoints principales.
- Verificar que Prometheus y Grafana estén recibiendo métricas correctamente.
- Confirmar que los datos migrados son visibles en el Admin de Django.

¿Deseas que proceda con la ejecución de este plan?
