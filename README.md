# SmartHydro - Sistema de Monitoreo Hidrológico Ultra-Seguro

Sistema completo de telemetría y monitoreo hidrológico con **configuración ultra-segura anti-ransomware**, alertas automáticas y envío de datos a servicios externos (DGA, SMA).

## 🚀 Características Principales

- **🛡️ Seguridad Ultra-Alta**: Protección anti-ransomware y acceso no autorizado
- **🌐 API REST Segura**: Endpoints protegidos con SSL/TLS automático
- **⏰ Telemetría en Tiempo Real**: Monitoreo continuo de puntos de captación
- **📧 Alertas Automáticas**: Sistema de notificaciones por email seguro
- **🔗 Integración DGA**: Envío automático de datos al servicio DGA
- **🔗 Integración SMA**: Envío automático de datos al servicio SMA
- **📊 Dashboard Web**: Interfaz de administración Django ultra-segura
- **⚡ Cron Jobs**: Automatización de procesos críticos con protección
- **🗄️ Base de Datos Local**: PostgreSQL 15 ultra-seguro no expuesto

## 🛡️ Características de Seguridad

### **🔒 Protección Anti-Ransomware:**

- **Base de datos completamente aislada** (red interna)
- **Contenedores con capacidades limitadas**
- **Filesystem de solo lectura** donde sea posible
- **Logs de seguridad completos** para auditoría
- **Usuarios con permisos mínimos** necesarios
- **SSL/TLS obligatorio** para todas las comunicaciones

### **🌐 Aislamiento de Redes:**

- **Red frontend**: Solo nginx expuesto (puertos 80/443)
- **Red backend**: Completamente interna (base de datos)
- **Contenedores aislados** por funcionalidad
- **Monitoreo de conexiones** en tiempo real

## 📋 Requisitos del Sistema

- **Docker** 20.10+
- **Docker Compose** 2.0+
- **VPS con Ubuntu 20.04+** o similar
- **Dominio configurado** (ej: api.smarthydro.app)
- **Acceso SMTP** para notificaciones

## 🚀 Despliegue Rápido y Seguro

### **1. Clonar el Repositorio**

```bash
git clone <repository-url>
cd core_api_sh
```

### **2. Configurar Variables de Entorno**

Crear archivo `.env`:

```env
# Base de datos local (VPS)
LOCAL_DB_PASSWORD=tu_password_super_seguro

# Dominio
VIRTUAL_HOST=api.smarthydro.app
LETSENCRYPT_EMAIL=api@smarthydro.app

# Cluster (solo para sincronización)
CLUSTER_DB_HOST=tu_cluster_host
CLUSTER_DB_PASSWORD=tu_cluster_password
```

### **3. Desplegar con Un Comando**

```bash
chmod +x deploy_production.sh
./deploy_production.sh
```

**¡Eso es todo!** El script configura automáticamente:

- ✅ Directorios seguros con permisos correctos
- ✅ Base de datos PostgreSQL 15 ultra-segura
- ✅ SSL/TLS automático con Let's Encrypt
- ✅ Sincronización de datos desde cluster
- ✅ Verificación de seguridad post-despliegue

## 🏗️ Arquitectura del Sistema

```
🌐 INTERNET
    ↓
🔒 NGINX PROXY (SSL/TLS)
    ↓
🐍 DJANGO API (api.smarthydro.app)
    ↓
🗄️ POSTGRESQL 15 (RED INTERNA)
    ↓
⏰ CRON JOBS (TELEMETRÍA)
```

## 📊 Monitoreo y Logs

### **📁 Directorios de Logs:**

- **PostgreSQL**: `/opt/smarthydro/postgres_logs`
- **Django**: `/opt/smarthydro/django_logs`
- **Cron**: `/opt/smarthydro/cron_logs`

### **🔍 Verificación de Seguridad:**

```bash
# Verificar que solo nginx esté expuesto
docker ps --format "table {{.Names}}\t{{.Ports}}"

# Verificar logs de seguridad
tail -f /opt/smarthydro/postgres_logs/postgresql-*.log
```

## 🚨 Mantenimiento y Sincronización

### **🔄 Sincronizar con Cluster:**

```bash
python3 maintenance/sync_cluster_to_local.py
```

### **📊 Backup Automático:**

```bash
python3 maintenance/backup_cluster.py
```

## 🔧 Configuración Avanzada

### **🌐 Múltiples Dominios:**

Para agregar más dominios, editar `docker-compose.production.secure.yml` y agregar servicios adicionales.

### **🔒 Personalizar Seguridad:**

Editar `init-db-secure.sql` para modificar configuraciones de PostgreSQL.

## 📚 Documentación

Para más detalles técnicos y guías, consulta la carpeta `docs/`:

- **[Análisis de Arquitectura](docs/analysis/)**: Esquemas y análisis técnicos del sistema.
- **[Guías de Usuario](docs/guides/)**: Manuales y guías de configuración.
- **[Planes y Roadmap](docs/plans/)**: Documentación sobre el desarrollo futuro y planes.
- **[Migración](docs/migration/)**: Información sobre procesos de migración (Celery, etc).

## 📞 Soporte y Scripts

- **Scripts de mantenimiento**: `scripts/maintenance/`
- **Configuración de servicios**: `conf/`

## 🎯 Ventajas de esta Arquitectura

1. **🛡️ Seguridad Máxima**: Base de datos inaccesible desde internet
2. **⚡ Despliegue Rápido**: Un comando para todo el sistema
3. **🔒 SSL Automático**: Certificados renovados automáticamente
4. **📊 Monitoreo Completo**: Logs de todas las operaciones
5. **🔄 Sincronización Fácil**: Datos del cluster en minutos
6. **🚀 Escalabilidad**: Fácil agregar más servicios
7. **💾 Persistencia**: Datos protegidos en volúmenes seguros

---

**¡SmartHydro: Seguridad y Eficiencia en Monitoreo Hidrológico!** 🚀
