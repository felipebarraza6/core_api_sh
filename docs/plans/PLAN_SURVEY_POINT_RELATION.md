# Plan de Migración: Vincular CatchmentPoint desde TechnicalSurvey

**Fecha:** 2026-01-21  
**Estado:** 🟡 Fase 1 En Progreso  
**Objetivo:** Modificar la relación entre `CatchmentPoint` y el módulo CRM para que el punto de captación se origine desde el `TechnicalSurvey` (Levantamiento Técnico) en lugar de directamente desde el `Project`.

---

## ✅ Cambios Realizados (Fase 1)

### Modelos Modificados:
1. **`api/crm/models.py` - TechnicalSurvey:**
   - ✅ Cambiado `project` de `OneToOneField` a `ForeignKey` (permite múltiples surveys por proyecto)
   - ✅ Agregado campo `name` para identificar cada levantamiento
   - ✅ Eliminada definición duplicada de `POWER_SOURCES`

2. **`api/telemetry/models/catchment_points.py` - CatchmentPoint:**
   - ✅ Agregado `technical_survey` como `OneToOneField` hacia `TechnicalSurvey`
   - ✅ Marcado campo `project` como deprecated (pero mantenido para compatibilidad)

3. **`api/crm/admin.py`:**
   - ✅ `TechnicalSurveyInline` cambiado a `TabularInline` (soporta múltiples)
   - ✅ `TechnicalSurveyAdmin` actualizado con link al punto generado

4. **Script de Migración de Datos:**
   - ✅ Creado `scripts/migration/link_survey_to_points.py`

---

## ⏳ Pasos Pendientes


**Problema:**
- `CatchmentPoint.project` es un FK directo a `Project`.
- El `TechnicalSurvey` es donde realmente se definen las especificaciones técnicas del punto (diámetro tubería, caudal esperado, coordenadas GPS, etc.), pero no tiene relación directa con el `CatchmentPoint`.
- Esto genera una desconexión lógica: los datos técnicos del levantamiento no fluyen directamente hacia la creación del punto.

---

## 2. Situación Propuesta

```
┌─────────────┐         ┌───────────────┐         ┌─────────────────────┐
│   Client    │──1:N───▶│    Project    │         │   CatchmentPoint    │
└─────────────┘         └───────────────┘         └─────────────────────┘
                               │                            ▲
                               │ 1:N                        │ 1:1 (nueva relación)
                               ▼                            │
                        ┌─────────────────────┐             │
                        │   TechnicalSurvey   │─────────────┘
                        └─────────────────────┘
```

**Cambios:**
1. `TechnicalSurvey` puede tener múltiples instancias por proyecto (1:N en lugar de 1:1).
2. Cada `TechnicalSurvey` puede generar un `CatchmentPoint` (relación 1:1 opcional).
3. `CatchmentPoint.project` se mantiene por compatibilidad pero se depreca a favor de `CatchmentPoint.technical_survey.project`.

---

## 3. Archivos Afectados

| Archivo | Cambios Necesarios |
|:--------|:-------------------|
| `api/crm/models.py` | Cambiar `TechnicalSurvey.project` de `OneToOneField` a `ForeignKey`. Agregar campo `catchment_point` opcional. |
| `api/telemetry/models/catchment_points.py` | Agregar FK `technical_survey` a `CatchmentPoint`. Marcar `project` como deprecated. |
| `api/crm/admin.py` | Actualizar `TechnicalSurveyAdmin` para mostrar/gestionar el `CatchmentPoint` vinculado. |
| `api/crm/serializers.py` | Incluir `catchment_point` en `TechnicalSurveySerializer`. |
| Migraciones Django | Crear migraciones para los cambios de modelo. |
| `docs/analysis/CRM_ARCHITECTURE_DIAGRAM.md` | Actualizar diagrama. |

---

## 4. Plan de Implementación (Fases)

### Fase 1: Preparación del Modelo (Sin romper compatibilidad)
> **Objetivo:** Agregar nuevos campos sin afectar datos existentes.

1. **Modificar `TechnicalSurvey`:**
   - Cambiar `project = models.OneToOneField(...)` a `project = models.ForeignKey(...)`.
   - Agregar campo `catchment_point = models.OneToOneField(CatchmentPoint, null=True, blank=True, ...)`.

2. **Modificar `CatchmentPoint`:**
   - Agregar `technical_survey = models.OneToOneField('crm.TechnicalSurvey', null=True, blank=True, related_name='generated_point', ...)`.
   - **NO eliminar** el campo `project` aún.

3. **Crear migración Django:**
   ```bash
   docker-compose -f docker-compose.dev.yml exec django_app python manage.py makemigrations
   docker-compose -f docker-compose.dev.yml exec django_app python manage.py migrate
   ```

### Fase 2: Migración de Datos
> **Objetivo:** Vincular datos existentes.

1. **Crear script de migración de datos** (`scripts/migration/link_survey_to_points.py`):
   - Para cada `CatchmentPoint` con `project` asignado:
     - Buscar el `TechnicalSurvey` del mismo proyecto.
     - Si existe, vincular `CatchmentPoint.technical_survey = survey`.
     - Vincular en reversa `TechnicalSurvey.catchment_point = point`.

2. **Ejecutar script:**
   ```bash
   docker-compose -f docker-compose.dev.yml exec django_app python manage.py shell < scripts/migration/link_survey_to_points.py
   ```

### Fase 3: Actualización de Lógica de Negocio
> **Objetivo:** Usar la nueva relación en código.

1. **Actualizar `CatchmentPoint` para obtener `project` de forma transitiva:**
   ```python
   @property
   def project(self):
       if self.technical_survey:
           return self.technical_survey.project
       return self._project  # Campo legacy deprecated
   ```

2. **Actualizar Admin:**
   - En `TechnicalSurveyAdmin`, agregar acción "Crear Punto de Captación desde este Levantamiento".
   - En `CatchmentPointAdmin`, mostrar link al `TechnicalSurvey` relacionado.

3. **Actualizar Serializers:**
   - `TechnicalSurveySerializer`: Incluir `catchment_point` como nested read-only.
   - `CatchmentPointSerializer`: Incluir `technical_survey` para ver origen.

### Fase 4: Deprecación del Campo Legacy
> **Objetivo:** Preparar para futura eliminación.

1. **Marcar `CatchmentPoint.project` como deprecated en docstrings y help_text.**

2. **Agregar logging warnings cuando se acceda directamente a `CatchmentPoint.project`.**

3. **Documentar en `GEMINI.md` o changelog.**

---

## 5. Rollback Plan

Si algo falla:
1. Los campos nuevos son `null=True, blank=True`, por lo que se pueden revertir las migraciones.
2. El campo `project` original en `CatchmentPoint` **no se elimina** durante esta fase.
3. Simplemente ignorar los nuevos campos si hay problemas.

---

## 6. Riesgos y Mitigaciones

| Riesgo | Mitigación |
|:-------|:-----------|
| Queries rotas que usan `CatchmentPoint.project` directamente | Property wrapper que busca primero en `technical_survey.project`. |
| Admin no muestra relación correctamente | Actualizar inlines y list_display. |
| Serializers incompletos | Tests de API antes de desplegar. |
| Datos históricos sin `TechnicalSurvey` | Script de migración crea/vincula automáticamente. |

---

## 7. Checklist de Implementación

- [ ] Modificar `api/crm/models.py` (TechnicalSurvey: FK, add catchment_point)
- [ ] Modificar `api/telemetry/models/catchment_points.py` (add technical_survey FK)
- [ ] Crear y aplicar migraciones Django
- [ ] Crear script de migración de datos (`link_survey_to_points.py`)
- [ ] Ejecutar script de migración de datos
- [ ] Actualizar `api/crm/admin.py`
- [ ] Actualizar `api/crm/serializers.py`
- [ ] Actualizar `api/telemetry/serializers.py` (si aplica)
- [ ] Actualizar diagrama de arquitectura CRM
- [ ] Agregar tests básicos
- [ ] Documentar cambio en GEMINI.md

---

## 8. Próximos Pasos

**Esperando confirmación del usuario para proceder con Fase 1.**

