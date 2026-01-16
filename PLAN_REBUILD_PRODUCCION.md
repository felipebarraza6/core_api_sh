# 🚀 Plan de Rebuild Seguro para Producción

## 📅 Fecha: 2025-01-20

## 🎯 Objetivo

Aplicar los cambios de código (CAUDAL_PROMEDIO dinámico y protección total=0) en producción mediante rebuild seguro de contenedores Docker.

---

## ✅ Cambios a Aplicar

### **1. CAUDAL_PROMEDIO Dinámico**
- ✅ Serializers calculan dinámicamente
- ✅ Admin muestra valores calculados
- ✅ Cronjobs NO guardan flow para CAUDAL_PROMEDIO
- **Impacto:** Solo lógica, NO requiere migraciones

### **2. Protección contra Guardar 0**
- ✅ `total_m3()` usa último valor válido cuando `value=0`
- ✅ Permite 0 solo si es el primer dato
- **Impacto:** Solo lógica, NO requiere migraciones

---

## 🛡️ Verificaciones de Seguridad

### **✅ Configuración Docker**
- ✅ `docker-compose.production.secure.yml`: YAML válido
- ✅ `Dockerfile`: Correcto y funcional
- ✅ Volúmenes persistentes configurados
- ✅ Redes seguras configuradas

### **✅ Cambios de Código**
- ✅ No requieren migraciones de base de datos
- ✅ No modifican estructura de datos
- ✅ Compatible con datos existentes
- ✅ Solo afectan lógica de procesamiento

### **✅ Datos**
- ✅ Volúmenes persistentes preservarán datos
- ✅ Base de datos NO se tocará
- ✅ No hay riesgo de pérdida de datos

---

## 📋 Pasos para Rebuild Seguro

### **Paso 1: Verificación Pre-Deploy**
```bash
# Verificar que estamos en el directorio correcto
cd /root/core_api_sh

# Verificar que existe .env
test -f .env || echo "ERROR: .env no existe"

# Verificar sintaxis YAML
python3 -c "import yaml; yaml.safe_load(open('docker-compose.production.secure.yml'))"
```

### **Paso 2: Backup de Seguridad (Opcional pero Recomendado)**
```bash
# Backup de base de datos (si tienes acceso)
# docker-compose -f docker-compose.production.secure.yml exec postgres pg_dump -U smarthydro_user smarthydro_prod > backup_$(date +%Y%m%d_%H%M%S).sql
```

### **Paso 3: Rebuild de Contenedores**
```bash
# Opción A: Rebuild solo Django y Cron (recomendado)
docker-compose -f docker-compose.production.secure.yml build django cron

# Opción B: Rebuild completo (si hay cambios en Dockerfile)
docker-compose -f docker-compose.production.secure.yml build --no-cache

# Levantar servicios con rebuild
docker-compose -f docker-compose.production.secure.yml up -d
```

### **Paso 4: Verificación Post-Deploy**
```bash
# Verificar que los contenedores están corriendo
docker-compose -f docker-compose.production.secure.yml ps

# Verificar logs de Django
docker-compose -f docker-compose.production.secure.yml logs django --tail=50

# Verificar logs de Cron
docker-compose -f docker-compose.production.secure.yml logs cron --tail=50

# Verificar salud de servicios
docker-compose -f docker-compose.production.secure.yml exec django curl -f http://localhost/health
```

### **Paso 5: Verificación Funcional**
```bash
# Verificar que la API responde
curl -f https://${VIRTUAL_HOST}/api/interaction_detail_json/ -H "Authorization: Bearer TOKEN"

# Verificar que los cronjobs siguen funcionando
docker-compose -f docker-compose.production.secure.yml exec cron ls -la /tmp/smarthydro/
```

---

## 🚨 Rollback (Si algo sale mal)

### **Opción 1: Revertir a imagen anterior**
```bash
# Detener servicios
docker-compose -f docker-compose.production.secure.yml down

# Restaurar imagen anterior (si tienes tag)
docker tag smarthydro_django_secure:previous smarthydro_django_secure:latest

# Levantar servicios
docker-compose -f docker-compose.production.secure.yml up -d
```

### **Opción 2: Revertir código y rebuild**
```bash
# Revertir cambios en git
git checkout HEAD -- api/core/serializers/interaction_detail.py
git checkout HEAD -- api/cronjobs/telemetry/controllers/total.py
# ... otros archivos

# Rebuild
docker-compose -f docker-compose.production.secure.yml build django cron
docker-compose -f docker-compose.production.secure.yml up -d
```

---

## ⚠️ Consideraciones Importantes

### **1. Tiempo de Inactividad**
- ⏱️ Rebuild: ~2-5 minutos
- ⏱️ Restart de servicios: ~30 segundos
- ⏱️ **Total estimado:** ~3-6 minutos de inactividad

### **2. Cronjobs**
- ⏰ Los cronjobs se reiniciarán automáticamente
- ⏰ No se perderán ejecuciones (se reanudarán)
- ⏰ Los logs se preservarán

### **3. API**
- 🌐 La API estará inactiva durante el rebuild
- 🌐 Las conexiones activas se perderán
- 🌐 Los clientes deberán reconectar

### **4. Base de Datos**
- 💾 NO se tocará la base de datos
- 💾 Los datos existentes se preservarán
- 💾 No hay riesgo de pérdida de datos

---

## ✅ Checklist Pre-Deploy

- [ ] Verificar que `.env` existe y tiene todas las variables
- [ ] Verificar que `docker-compose.production.secure.yml` es válido
- [ ] Verificar que no hay migraciones pendientes
- [ ] (Opcional) Hacer backup de base de datos
- [ ] Verificar que hay espacio en disco suficiente
- [ ] Notificar a usuarios sobre mantenimiento (si es necesario)
- [ ] Verificar que los cambios están en el código local

---

## 📊 Monitoreo Post-Deploy

### **Primeros 30 minutos:**
- ✅ Verificar logs de Django cada 5 minutos
- ✅ Verificar logs de Cron cada 5 minutos
- ✅ Verificar que la API responde correctamente
- ✅ Verificar que los cronjobs están ejecutando

### **Primeras 24 horas:**
- ✅ Monitorear logs de errores
- ✅ Verificar que los cálculos dinámicos funcionan
- ✅ Verificar que la protección total=0 funciona
- ✅ Verificar que no hay errores en producción

---

## 🎯 Resultado Esperado

Después del rebuild:
- ✅ CAUDAL_PROMEDIO se calcula dinámicamente
- ✅ Protección contra guardar 0 activa
- ✅ Todos los servicios funcionando
- ✅ Datos preservados
- ✅ Sin errores en logs

---

*Plan creado: 2025-01-20*
*Estado: ✅ LISTO PARA EJECUTAR*

