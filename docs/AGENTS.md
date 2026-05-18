# AGENTS.md - Documentación

> Reglas para mantener la documentación del proyecto actualizada y consistente.

## Estructura de Documentación

### Archivos existentes y su propósito

| Archivo | Propósito |
|---------|-----------|
| `CLAUDE.md` | Guía original para Claude Code (legado, mantener por referencia) |
| `FULL_SYSTEM_ANALYSIS.md` | Análisis arquitectónico completo del sistema |
| `CLOUDFLARE_MIGRATION.md` | Guía de migración a Cloudflare |
| `CSP_VALIDATION.md` | Validación y configuración de Content Security Policy |
| `GUIA_FRONTEND_*.md` | Guías para desarrolladores frontend (Login, Alertas, Reportes) |
| `API_FRONTEND.md` | Documentación de endpoints para frontend |
| `MANUAL_API_FRONTEND.md` | Manual completo de la API |

### Reglas para nueva documentación

1. **Idioma**: Documentación técnica interna en español (Chile). Documentación de API puede ser bilingüe si es para consumo externo.
2. **Formato**: Markdown con headers claros.
3. **Código**: Los bloques de código deben especificar el lenguaje (```bash, ```python, etc.).
4. **Diagramas**: Preferir texto ASCII o Mermaid. Evitar imágenes embebidas.

### Cuándo actualizar docs

- **SIEMPRE** que se modifique la API (agregar/eliminar/cambiar endpoints)
- **SIEMPRE** que se modifique el flujo de autenticación
- **SIEMPRE** que se agregue una integración nueva (DGA, SMA, etc.)
- **SIEMPRE** que se modifique la arquitectura de Docker

### Archivos que NUNCA deben editarse

- `CLAUDE.md` - Es referencia histórica. Si hay info desactualizada, crear archivo nuevo en vez de modificarlo.
