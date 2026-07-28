#!/usr/bin/env python
"""
Genera inventario de endpoints legacy (/api/) e Ikolu (/api/ik/).

Uso dentro del contenedor django_api_secure:
    python scripts/audit/generate_endpoint_inventory.py

Salida:
    docs/audit/endpoints_inventory.json
    docs/audit/endpoints_inventory.md
"""

import json
import os
import sys
from pathlib import Path

import django

# Configurar Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
django.setup()

from django.urls import URLPattern, URLResolver
from django.conf import settings

from api.urls import urlpatterns


def extract_endpoints(urlpatterns, prefix="", namespace=None):
    """Recorre urlpatterns y extrae rutas con sus vistas."""
    endpoints = []
    for pattern in urlpatterns:
        if isinstance(pattern, URLResolver):
            new_prefix = prefix + pattern.pattern._route if hasattr(pattern.pattern, '_route') else prefix + str(pattern.pattern)
            new_namespace = f"{namespace}:{pattern.namespace}" if namespace and pattern.namespace else (pattern.namespace or namespace)
            endpoints.extend(extract_endpoints(pattern.url_patterns, new_prefix, new_namespace))
        elif isinstance(pattern, URLPattern):
            route = prefix + (pattern.pattern._route if hasattr(pattern.pattern, '_route') else str(pattern.pattern))
            view = pattern.callback
            view_name = getattr(pattern, 'name', '')
            module = getattr(view, '__module__', '')
            qualname = getattr(view, '__qualname__', getattr(view, '__name__', str(view)))
            endpoints.append({
                "route": route,
                "namespace": namespace or '',
                "name": view_name,
                "view_module": module,
                "view": qualname,
            })
    return endpoints


def categorize(route):
    if route.startswith('api/ik/'):
        return 'ikolu'
    if route.startswith('api/'):
        return 'legacy'
    if route.startswith('admin/'):
        return 'admin'
    return 'other'


def main():
    endpoints = extract_endpoints(urlpatterns)
    for ep in endpoints:
        ep['category'] = categorize(ep['route'])

    # Guardar JSON
    json_path = Path("docs/audit/endpoints_inventory.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(endpoints, f, indent=2, ensure_ascii=False)

    # Generar Markdown
    md_path = Path("docs/audit/endpoints_inventory.md")
    legacy = [ep for ep in endpoints if ep['category'] == 'legacy']
    ikolu = [ep for ep in endpoints if ep['category'] == 'ikolu']
    admin_eps = [ep for ep in endpoints if ep['category'] == 'admin']
    other = [ep for ep in endpoints if ep['category'] == 'other']

    lines = [
        "# Inventario de Endpoints SmartHydro",
        "",
        f"> Generado automáticamente el: {django.utils.timezone.now().isoformat()}",
        f"> Total endpoints: {len(endpoints)} (legacy: {len(legacy)}, ikolu: {len(ikolu)}, admin: {len(admin_eps)}, other: {len(other)})",
        "",
        "## Resumen",
        "",
        "| Categoría | Cantidad |",
        "|-----------|----------|",
        f"| Legacy (`/api/`) | {len(legacy)} |",
        f"| Ikolu (`/api/ik/`) | {len(ikolu)} |",
        f"| Admin | {len(admin_eps)} |",
        f"| Otros | {len(other)} |",
        "",
        "---",
        "",
        "## Endpoints Legacy (`/api/`)",
        "",
        "| Ruta | Vista | Módulo |",
        "|------|-------|--------|",
    ]
    for ep in sorted(legacy, key=lambda x: x['route']):
        lines.append(f"| `{ep['route']}` | `{ep['view']}` | `{ep['view_module']}` |")

    lines.extend([
        "",
        "---",
        "",
        "## Endpoints Ikolu (`/api/ik/`)",
        "",
        "| Ruta | Vista | Módulo |",
        "|------|-------|--------|",
    ])
    for ep in sorted(ikolu, key=lambda x: x['route']):
        lines.append(f"| `{ep['route']}` | `{ep['view']}` | `{ep['view_module']}` |")

    lines.extend([
        "",
        "---",
        "",
        "## Endpoints Admin",
        "",
        "| Ruta | Vista | Módulo |",
        "|------|-------|--------|",
    ])
    for ep in sorted(admin_eps, key=lambda x: x['route']):
        lines.append(f"| `{ep['route']}` | `{ep['view']}` | `{ep['view_module']}` |")

    lines.extend([
        "",
        "---",
        "",
        "## Otros Endpoints",
        "",
        "| Ruta | Vista | Módulo |",
        "|------|-------|--------|",
    ])
    for ep in sorted(other, key=lambda x: x['route']):
        lines.append(f"| `{ep['route']}` | `{ep['view']}` | `{ep['view_module']}` |")

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"Inventario generado:")
    print(f"  - {json_path}")
    print(f"  - {md_path}")


if __name__ == "__main__":
    main()
