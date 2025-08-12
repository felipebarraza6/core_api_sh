# SmartHydro - Sistema de Monitoreo Hidrológico

Sistema completo de telemetría y monitoreo hidrológico con alertas automáticas y envío de datos a servicios externos (DGA, SMA).

## 🚀 Características Principales

- **Telemetría en Tiempo Real**: Monitoreo continuo de puntos de captación
- **Alertas Automáticas**: Sistema de notificaciones por email
- **Integración DGA**: Envío automático de datos al servicio DGA
- **Integración SMA**: Envío automático de datos al servicio SMA
- **Dashboard Web**: Interfaz de administración Django
- **API REST**: Endpoints para integración externa
- **Cron Jobs**: Automatización de procesos críticos

## 📋 Requisitos del Sistema

- Python 3.8+
- PostgreSQL 12+
- Redis (opcional, para cache)
- cPanel con acceso SMTP

## 🛠️ Instalación

### 1. Clonar el Repositorio

```bash
git clone <repository-url>
cd stack_dev_sh
```

### 2. Configurar Entorno Virtual

```bash
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

### 3. Instalar Dependencias

```bash
pip install -r api/requirements.txt
```

### 4. Configurar Base de Datos

```bash
# Crear base de datos PostgreSQL
createdb smarthydro_db

# Aplicar migraciones
python manage.py migrate
```

### 5. Crear Superusuario

```bash
python manage.py createsuperuser
```

### 6. Configurar Variables de Entorno

Crear archivo `.env` en la raíz del proyecto:

```env
DEBUG=True
SECRET_KEY=tu-secret-key-aqui
DATABASE_URL=postgresql://usuario:password@localhost:5432/smarthydro_db
```

### 7. Configurar Email (Obligatorio)

Editar `api/settings.py` con tu configuración SMTP:

```python
EMAIL_HOST = "tu-servidor-smtp.com"
EMAIL_PORT = 465
EMAIL_USE_SSL = True
EMAIL_HOST_USER = "tu-email@dominio.com"
EMAIL_HOST_PASSWORD = "tu-password"
DEFAULT_FROM_EMAIL = "tu-email@dominio.com"
CONTACT_EMAIL = "telemetry@smarthydro.app"
```

### 8. Configurar Alertas

Editar `api/cronjobs/alerts/config_alerts.py`:

```python
ALERT_CONFIG = {
    "points_emails": {
        1: ["admin@tuempresa.com", "tecnico@tuempresa.com"],
        2: ["soporte@tuempresa.com"],
        # Agregar más puntos según necesites
    },
    "dga_queue_threshold": 5,
    "disconnection_threshold": 1,
    "smtp_server": "tu-servidor-smtp.com",
    "smtp_port": 465,
    "smtp_user": "tu-email@dominio.com",
    "smtp_password": "tu-password",
}
```

## 🚀 Ejecución

### Desarrollo

```bash
# Activar entorno virtual
source venv/bin/activate

# Ejecutar servidor de desarrollo
python manage.py runserver
```

### Producción

```bash
# Usar Docker Compose
docker-compose -f production.yml up -d

# O ejecutar directamente
./run-production.sh
```

## ⏰ Configuración de Cron Jobs

El sistema incluye varios cron jobs automáticos:

- **Telemetría**: Cada 1, 5 y 60 minutos
- **DGA**: Cada 3 minutos
- **SMA**: Cada 5 minutos
- **Alertas**: Cada 10 minutos

### Configurar Cron Jobs

```bash
# Instalar django-crontab
pip install django-crontab

# Agregar jobs al crontab
python manage.py crontab add

# Ver jobs activos
python manage.py crontab show

# Remover jobs
python manage.py crontab remove
```

## 📧 Sistema de Alertas

### Tipos de Alertas

1. **⚠️ Advertencia**: Cola DGA (registros pendientes)
2. **📢 Notificación**: Recuperación del sistema
3. **🚨 Error Crítico**: Desconexión de puntos
4. **⏸️ Suspensión**: Mantenimiento programado

### Configuración de Emails

- **Remitente**: `notify@smarthydro.app`
- **Contacto**: `telemetry@smarthydro.app`
- **Templates**: HTML profesionales con branding

### Probar Alertas

```bash
# Ejecutar script de prueba
python3 send_all_templates.py
```

## 📊 API Endpoints

### Puntos de Captación

- `GET /api/catchment-points/` - Listar puntos
- `POST /api/catchment-points/` - Crear punto
- `GET /api/catchment-points/{id}/` - Detalle del punto
- `PUT /api/catchment-points/{id}/` - Actualizar punto
- `DELETE /api/catchment-points/{id}/` - Eliminar punto

### Interacciones

- `GET /api/interaction-detail/` - Listar interacciones
- `POST /api/interaction-detail/` - Crear interacción

### Usuarios

- `GET /api/users/` - Listar usuarios
- `POST /api/users/` - Crear usuario

## 🔧 Mantenimiento

### Logs

Los logs se encuentran en:

- `api/cronjobs/telemetry/logs/` - Logs de telemetría
- `api/cronjobs/telemetry/logs/dga.log` - Logs DGA
- `api/cronjobs/telemetry/logs/alerts.log` - Logs de alertas

### Backup de Base de Datos

```bash
# Crear backup
pg_dump smarthydro_db > backup/dump_$(date +%Y%m%d_%H%M%S).sql

# Restaurar backup
psql smarthydro_db < backup/dump.sql
```

### Actualizar Dependencias

```bash
pip install --upgrade -r api/requirements.txt
```

## 🐛 Solución de Problemas

### Error de Conexión SMTP

1. Verificar configuración en `settings.py`
2. Probar conexión con script de prueba
3. Verificar credenciales de cPanel

### Cron Jobs No Ejecutan

1. Verificar que django-crontab esté instalado
2. Ejecutar `python manage.py crontab add`
3. Verificar logs en `/var/log/cron`

### Base de Datos

1. Verificar conexión PostgreSQL
2. Ejecutar `python manage.py migrate`
3. Verificar permisos de usuario

## 📞 Soporte

- **Email**: telemetry@smarthydro.app
- **Documentación**: [URL de documentación]
- **Issues**: [URL del repositorio]

## 📄 Licencia

Este proyecto está bajo la licencia [LICENCIA]. Ver archivo `LICENSE` para más detalles.

## 🤝 Contribución

1. Fork el proyecto
2. Crear rama para feature (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abrir Pull Request

---

**SmartHydro** - Sistema de Monitoreo Hidrológico Inteligente
