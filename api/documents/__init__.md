# 📄 Documents App (Smart Files & Reports)

**Responsabilidad**: Gestión de archivos y Generación Automática de Reportes.
**Estado**: ✅ ACTIVO (Mejorado con DocGen)

## 🧠 Propósito
No solo guardar PDFs, sino **crearlos**. Permite a los usuarios diseñar sus propios reportes (Word/Excel/HTML) y programar su envío.

## 📦 Componentes Clave

1.  **Almacenamiento**:
    *   `Document`: Archivo subido (PDF, validaciones, planos).
    *   Asociado a Cliente, Proyecto o Punto.

2.  **Motor DocGen (`engine/generator.py`)**:
    *   Toma una plantilla (`.docx`, `.xlsx` o HTML).
    *   Inyecta contexto JSON (`{{ caudal }}`).
    *   Produce un archivo final reportable.

3.  **Scheduler (`ScheduledGeneration`)**:
    *   Cronjob (Celery Beat) que ejecuta reportes cada X tiempo y los envía por correo.
