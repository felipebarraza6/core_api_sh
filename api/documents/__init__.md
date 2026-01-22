# documents: __init__ & AI SKILLS

Este es un resumen estructural de la aplicación `documents`. Úsalo para gestionar archivos, PDFs y almacenamiento.

## 🎯 Purpose & Scope
Gestión centralizada de documentos del sistema (Planos, Manuales, Certificados, Reportes Generados). Maneja el almacenamiento físico y los metadatos de archivos.

## 🧠 AI Specialist Skills (Mini-Agent Instructions)

Agente, al trabajar en esta carpeta, asume el rol de **Document Control Officer**. Debes seguir estas reglas:

| Skill | Description |
| :--- | :--- |
| **Logic Pattern** | Los documentos generados deben guardarse en `media/reports` con hash único. |
| **Restriction** | No permitas acceso público a archivos sin token de sesión. |
| **Tooling** | Usa `reportlab` o `xhtml2pdf` para la generación dinámica de archivos. |

### 🛠️ Standard Workflows
1. **Generating Report**: Recolectar datos -> Renderizar template HTML -> Convertir a PDF -> Guardar y notificar.
2. **Cleanup**: Archivar documentos antiguos de más de 2 años a almacenamiento frío.

## 🏗️ Core Architecture Components

### Models (Primary Tables)
- **`Document`**: Metadatos de un archivo vinculado a un proyecto o cliente.
- **`DocumentTemplate`**: Plantillas para generación dinámica de documentos.

---
*Referencia global: [ROOT_MAP.md](file:///Users/felipebarraza/projects/core_api_sh/api/ROOT_MAP.md)*
