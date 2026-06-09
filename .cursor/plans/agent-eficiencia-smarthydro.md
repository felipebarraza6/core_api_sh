# Checklist de Eficiencia — SmartHydro API

> Creado: 2026-05-31
> Propósito: Evitar que el agente se pierda en tareas de API/debugging

## 🔴 Antes de tocar cualquier endpoint

- [ ] Leer `docker-compose.production.secure.yml` para entender bind mounts y qué se monta en `/app`
- [ ] Recordar: el contenedor usa Gunicorn (no recarga automática). Los `.pyc` pueden quedar desincronizados con `.py`
- [ ] Si hay 500, `docker logs --tail 30 django_api_secure` **inmediatamente**, sin preguntar al usuario
- [ ] Si el error es `AttributeError` en un campo de modelo que existe en el archivo → usar `getattr()` defensivo al toque, NO intentar limpiar cachés ni reiniciar contenedores

## 🟡 Reglas de tipos numéricos (Python 3)

- [ ] `DecimalField` devuelve `Decimal`, NO `float`
- [ ] Nunca hacer `sum([float, Decimal])` → explota con `TypeError`
- [ ] Siempre convertir: `float(valor)` antes de sumar/promediar
- [ ] `max(0.0, Decimal('x'))` devuelve tipos mixtos → convertir ambos argumentos a `float`

## 🟢 Cambios mínimos

- [ ] Una sola razón de cambio por edición
- [ ] Si el cambio es defensivo (ej: `getattr`), aplicarlo directamente sin rodeos
- [ ] No refactorizar código que no está roto
- [ ] Documentación (`docs/*.md`) se actualiza solo si el contrato de la API cambia

## 🚨 Prohibido en este proyecto

- Hacer `docker-compose down` sin confirmación explícita del usuario
- Asumir que los contenedores recargan código automáticamente
- Pedirle al usuario que haga debugging (logs, comandos) cuando puedo hacerlo yo con `docker exec`/`docker logs`
- Dejar prints de debug en el código
