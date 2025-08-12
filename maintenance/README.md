# 🛠️ MAINTENANCE - SMART HYDRO

**Scripts esenciales para mantener tu cluster DigitalOcean**

## 📋 SCRIPTS DISPONIBLES

### **1. `analyze_cluster.py`**

- **Qué hace:** Analiza el estado del cluster
- **Cuándo usar:** Antes de hacer cambios importantes
- **Output:** Lista de tablas, total de registros, estado de staging

### **2. `backup_cluster.py`**

- **Qué hace:** Backup completo de toda la base de datos
- **Cuándo usar:** ANTES de eliminar tablas o hacer cambios
- **Output:** Directorio con archivos SQL de cada tabla

### **3. `delete_staging.py`**

- **Qué hace:** Elimina la tabla staging_interactiondetail
- **Cuándo usar:** DESPUÉS del backup, para limpiar
- **Output:** Log de eliminación

## 🚀 USO RÁPIDO

```bash
cd maintenance

# 1. Analizar cluster
python analyze_cluster.py

# 2. Hacer backup (OBLIGATORIO)
python backup_cluster.py

# 3. Eliminar staging
python delete_staging.py
```

## ⚠️ IMPORTANTE

- **SIEMPRE** haz backup antes de eliminar
- Los scripts usan credenciales del cluster
- Cada script te pide confirmación
- Se crean logs automáticamente

## 📁 ESTRUCTURA

```
maintenance/
├── README.md              # Esta guía
├── analyze_cluster.py     # Análisis del cluster
├── backup_cluster.py      # Backup completo
└── delete_staging.py      # Eliminar tabla staging
```

---

_Mantenimiento simple y efectivo - SmartHydro_
