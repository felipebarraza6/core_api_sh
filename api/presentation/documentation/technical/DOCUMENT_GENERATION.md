# 📄 Motor de Generación de Documentos

SmartHydro ahora incluye un motor nativo para generar reportes dinámicos en Word (.docx) y Excel (.xlsx).

## 1. Conceptos Básicos

*   **Template**: Un archivo `.docx` o `.xlsx` subido al sistema que contiene "placeholders" (variables entre llaves `{{variable}}`).
*   **Contexto**: Los datos que rellenarán esos placeholders (ej: `{ "cliente": "Aguas Andinas", "caudal": 45.5 }`).
*   **Generador**: Un servicio que combina Template + Contexto para crear un archivo final.

## 2. Cómo crear un Template

### Word (.docx)
Usamos el motor `docxtpl` (Jinja2 syntax).

1.  Abre Word.
2.  Escribe tu documento.
3.  Donde quieras un dato dinámico, usa `{{ variable }}`.
    *   Ejemplo: *"El caudal promedio fue de {{ caudal_promedio }} L/s"*.
4.  Para tablas dinámicas:
    *   Usa etiquetas `{% tr for item in items %}` dentro de las filas de la tabla.
5.  Sube el archivo en **Admin > Documentos > Plantillas**.

### Excel (.xlsx)
Usamos `openpyxl`.

1.  Abre Excel.
2.  Diseña tu planilla.
3.  En las celdas, escribe `{{ variable }}`.
    *   El sistema buscará texto con `{{...}}` y lo reemplazará por el valor exacto.

## 3. Automatización (Cron)

Puedes programar reportes automáticos en **Admin > Documentos > Generaciones Programadas**.

*   **Cron Expression**: Define la frecuencia (ej: `0 8 * * 1` para todos los lunes a las 8am).
*   **Contexto Estático**: JSON con datos fijos para el reporte.
*   **Destinatarios**: Correos donde se enviará el adjunto.

## 4. Uso Programático

```python
from api.documents.models import DocumentTemplate
from api.documents.engine.generator import DocumentGenerator

# 1. Cargar Template
tpl = DocumentTemplate.objects.get(code='REPORTE_MENSUAL')

# 2. Definir Datos
ctx = {
    'cliente': 'Fundo San José',
    'mes': 'Enero 2026',
    'total_m3': 15000
}

# 3. Generar
gen = DocumentGenerator(tpl)
path = gen.generate(ctx)
print(f"Documento creado en: {path}")
```

## 5. Previsualización y Estilos

SmartHydro expone un endpoint para que el frontend pueda mostrar una vista previa en tiempo real.

*   **Endpoint**: `POST /api/documents/templates/{id}/preview/`
*   **Body**: JSON con datos de prueba.
*   **Respuesta**: HTML renderizado.

### Estilos Personalizados (CSS)
En el editor HTML, puedes usar etiquetas `<style>` para definir tu branding:

```html
<style>
    body { font-family: 'Arial'; color: #333; }
    .header { background: #004488; color: white; padding: 20px; }
    .alert { color: red; font-weight: bold; }
</style>

<div class="header">
    <h1>Reporte de: {{ cliente }}</h1>
</div>
```

