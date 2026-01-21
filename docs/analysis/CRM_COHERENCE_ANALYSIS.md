# Análisis de Coherencia: Módulo CRM V2.0

**Fecha:** 2026-01-21  
**Versión:** 2.0  
**Estado:** ✅ Coherente con observaciones menores

---

## 1. Resumen Ejecutivo

El módulo CRM ha sido refactorizado para soportar un flujo de trabajo completo desde la captación del cliente hasta la operación del punto de captación. La arquitectura es **coherente** y sigue patrones consistentes.

### Puntos Fuertes:
- ✅ Jerarquías claras: Category → SubCategory, Type → SubType
- ✅ Relaciones bidireccionales con documentos
- ✅ Levantamiento técnico dinámico con campos configurables
- ✅ Tareas con respuestas y archivos adjuntos
- ✅ Costos clasificados por categoría Y tipo de flujo

### Áreas de Mejora Identificadas:
- ⚠️ Campo `is_active` faltaba en TechnicalSurvey (CORREGIDO)
- ⚠️ Validación de subcategoría perteneciente a categoría padre
- ⚠️ Person vinculado a Project pero JobPosition a Client

---

## 2. Análisis de Modelos

### 2.1 Cliente y Cargos

| Modelo | Campos Clave | Coherencia |
|:-------|:-------------|:-----------|
| `Client` | name, rut, status, logo | ✅ Correcto |
| `JobPosition` | client (FK), name, department | ✅ Correcto |

**Observación:**
- `JobPosition` está vinculado a `Client` (correcto).
- `Person` está vinculado a `Project` (correcto).
- **Posible inconsistencia:** Si una `Person` tiene un `JobPosition` de un cliente diferente al del proyecto.
- **Recomendación:** Agregar validación en `Person.clean()` para verificar que el `JobPosition.client` coincida con `project.client`.

```python
# Sugerencia de validación:
def clean(self):
    if self.job_position and self.project:
        if self.job_position.client and self.job_position.client != self.project.client:
            raise ValidationError("El cargo debe pertenecer al mismo cliente del proyecto.")
```

---

### 2.2 Proyecto

| Modelo | Campos Clave | Coherencia |
|:-------|:-------------|:-----------|
| `Project` | client (FK), status, budget, documents (M2M) | ✅ Correcto |

**Flujo de Estados:**
```
PLANNING → PROPOSAL → APPROVED → IN_PROGRESS → ACTIVE → MAINTENANCE → CLOSED
```

**Observación:**
- El flujo de estados es lógico y cubre el ciclo de vida completo.
- Falta un campo `end_date` para proyectos cerrados (recomendación menor).

---

### 2.3 Costos

| Modelo | Estructura | Coherencia |
|:-------|:-----------|:-----------|
| `CostCategory` → `CostSubCategory` | Jerarquía simple | ✅ |
| `CostType` → `CostSubType` | Jerarquía simple | ✅ |
| `ProjectCost` | Doble clasificación | ✅ |

**Observación:**
- La doble clasificación (Category + Type) es poderosa pero puede confundir.
- **Recomendación:** Documentar claramente en el Admin:
  - `Category`: QUÉ es (Hardware, Mano de Obra)
  - `Type`: CÓMO fluye (Ingreso, Egreso)

**Posible inconsistencia:**
- `CostSubCategory` no valida que pertenezca a la `CostCategory` seleccionada.
- Mismo problema en `CostSubType` con `CostType`.

```python
# Sugerencia de validación en ProjectCost:
def clean(self):
    if self.subcategory and self.category:
        if self.subcategory.category != self.category:
            raise ValidationError("La subcategoría debe pertenecer a la categoría seleccionada.")
```

---

### 2.4 Tareas

| Modelo | Estructura | Coherencia |
|:-------|:-----------|:-----------|
| `TaskCategory` → `TaskSubCategory` | Jerarquía simple | ✅ |
| `TaskType` → `TaskSubType` | Jerarquía simple | ✅ |
| `CrmTask` | Doble clasificación + contacts | ✅ |
| `TaskResponse` | Respuesta con documentos | ✅ |

**Observación:**
- La estructura es consistente con Costos.
- `CrmTask.contacts` permite asociar personas del cliente a la tarea (excelente).
- **Posible inconsistencia:** Los contactos deberían pertenecer al mismo proyecto/cliente.

```python
# Sugerencia de validación en formulario Admin:
def clean(self):
    for contact in self.contacts:
        if contact.project != self.project:
            raise ValidationError(f"El contacto {contact} no pertenece al proyecto.")
```

**Flujo de Estados:**
```
PENDING → IN_PROGRESS → AWAITING_RESPONSE → COMPLETED
                     ↘                    ↗
                       → CANCELLED ←
```

---

### 2.5 Levantamiento Técnico

| Modelo | Estructura | Coherencia |
|:-------|:-----------|:-----------|
| `SurveyFieldType` | Tipos de dato | ✅ |
| `SurveyFieldDefinition` | Campos configurables | ✅ |
| `TechnicalSurvey` | Datos dinámicos + status + is_active | ✅ |

**Nuevos campos agregados:**
- `status`: DRAFT → IN_PROGRESS → COMPLETED → APPROVED/REJECTED
- `is_active`: Permite desactivar sin eliminar

**Observación:**
- El sistema dinámico es flexible y escalable.
- Los datos se almacenan en `dynamic_data` (JSONField).
- **Recomendación:** Agregar método de validación que verifique campos requeridos.

```python
def validate_required_fields(self):
    """Valida que todos los campos requeridos estén presentes."""
    required_fields = SurveyFieldDefinition.objects.filter(is_required=True, is_active=True)
    missing = []
    for field in required_fields:
        if field.code not in self.dynamic_data or self.dynamic_data[field.code] in [None, '']:
            missing.append(field.name)
    return missing
```

---

## 3. Relaciones entre Modelos

```
                                    ┌─────────────────┐
                                    │     Client      │
                                    │                 │
                                    │  • JobPosition  │◄────────────┐
                                    └────────┬────────┘             │
                                             │ 1:N                  │
                                             ▼                      │
┌──────────────┐         ┌─────────────────────────────────┐        │
│   Document   │◄───────▶│            Project              │        │
│              │ M2M     │                                 │        │
│ sourced_from │         │  • technical_surveys (1:N)      │────────┤
│ (FK)         │         │  • tasks (1:N)                  │        │
└──────────────┘         │  • costs (1:N)                  │        │
                         │  • contacts (Person, 1:N)       │────────┘
                         └─────────────────────────────────┘          
                                    │                      
                                    │ 1:N                  
                    ┌───────────────┼───────────────┐      
                    ▼               ▼               ▼      
          ┌─────────────────┐ ┌─────────────┐ ┌─────────────┐
          │ TechnicalSurvey │ │   CrmTask   │ │ ProjectCost │
          │                 │ │             │ │             │
          │ • status        │ │ • contacts  │ │ • category  │
          │ • is_active     │ │ • responses │ │ • cost_type │
          │ • dynamic_data  │ │ • documents │ │ • documents │
          └────────┬────────┘ └──────┬──────┘ └─────────────┘
                   │                 │
                   │ 1:1             │ 1:N
                   ▼                 ▼
          ┌─────────────────┐ ┌─────────────┐
          │ CatchmentPoint  │ │TaskResponse │
          │   (Telemetry)   │ │ • documents │
          └─────────────────┘ └─────────────┘
```

---

## 4. Validaciones Recomendadas

### 4.1 A nivel de Modelo (clean methods)

| Modelo | Validación |
|:-------|:-----------|
| `Person` | `job_position.client == project.client` |
| `ProjectCost` | `subcategory.category == category` |
| `ProjectCost` | `cost_subtype.cost_type == cost_type` |
| `CrmTask` | `subcategory.category == category` |
| `CrmTask` | `task_subtype.task_type == task_type` |
| `CrmTask` | `contacts.all().project == project` |
| `TechnicalSurvey` | Campos requeridos presentes en `dynamic_data` |

### 4.2 A nivel de Admin (formfield_for_foreignkey)

```python
def formfield_for_foreignkey(self, db_field, request, **kwargs):
    if db_field.name == "subcategory":
        # Filtrar subcategorías por la categoría seleccionada
        # (requiere JavaScript adicional para dinamismo)
        pass
    return super().formfield_for_foreignkey(db_field, request, **kwargs)
```

---

## 5. Campos `is_active` Pendientes

| Modelo | Tiene `is_active` | Recomendación |
|:-------|:------------------|:--------------|
| `Client` | ❌ (usa `status`) | OK, status es suficiente |
| `Project` | ❌ (usa `status`) | OK |
| `TechnicalSurvey` | ✅ | Recién agregado |
| `CrmTask` | ❌ (usa `status`) | OK |
| `SurveyFieldDefinition` | ✅ | OK |
| `CostCategory` | ❌ | **Considerar agregar** |
| `CostType` | ❌ | **Considerar agregar** |
| `TaskCategory` | ❌ | **Considerar agregar** |
| `TaskType` | ❌ | **Considerar agregar** |
| `JobPosition` | ❌ | **Considerar agregar** |

---

## 6. Checklist de Coherencia

| Aspecto | Estado |
|:--------|:-------|
| Nomenclatura consistente | ✅ |
| Relaciones bidireccionales | ✅ |
| Jerarquías Category/SubCategory | ✅ |
| Jerarquías Type/SubType | ✅ |
| Documentos M2M en modelos principales | ✅ |
| Estados/Status definidos | ✅ |
| Campo `is_active` en levantamientos | ✅ |
| Validaciones de integridad | ⚠️ Pendiente |
| Tests unitarios | ❌ Pendiente |

---

## 7. Próximos Pasos

1. **Agregar validaciones** en métodos `clean()` de los modelos.
2. **Agregar `is_active`** a categorías y tipos si se requiere.
3. **Crear tests unitarios** para validar relaciones.
4. **Documentar en Admin** la diferencia entre Category y Type.
5. **Ejecutar migraciones** para aplicar cambios pendientes.

```bash
docker-compose -f docker/docker-compose.dev.yml exec django_app python manage.py makemigrations crm
docker-compose -f docker/docker-compose.dev.yml exec django_app python manage.py migrate
```
