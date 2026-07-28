#!/usr/bin/env python
"""
Orquesta la generación de artefactos de auditoría.

Uso:
    # Generar inventario de endpoints (requiere Django)
    docker exec django_api_secure python scripts/audit/run_full_audit.py --inventory

    # Generar Markdown desde inventario existente (host local)
    python scripts/audit/run_full_audit.py --markdown

    # Todo
    docker exec django_api_secure python scripts/audit/run_full_audit.py --all
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def generate_inventory():
    """Genera docs/audit/endpoints_inventory.json introspectando urls.py."""
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
    django.setup()

    from django.urls import URLPattern, URLResolver
    from api.urls import urlpatterns

    def extract(urlpatterns, prefix="", namespace=None):
        endpoints = []
        for pattern in urlpatterns:
            if isinstance(pattern, URLResolver):
                new_prefix = prefix + (
                    pattern.pattern._route
                    if hasattr(pattern.pattern, "_route")
                    else str(pattern.pattern)
                )
                new_ns = (
                    f"{namespace}:{pattern.namespace}"
                    if namespace and pattern.namespace
                    else (pattern.namespace or namespace)
                )
                endpoints.extend(extract(pattern.url_patterns, new_prefix, new_ns))
            elif isinstance(pattern, URLPattern):
                route = prefix + (
                    pattern.pattern._route
                    if hasattr(pattern.pattern, "_route")
                    else str(pattern.pattern)
                )
                view = pattern.callback
                endpoints.append(
                    {
                        "route": route,
                        "namespace": namespace or "",
                        "name": getattr(pattern, "name", ""),
                        "view_module": getattr(view, "__module__", ""),
                        "view": getattr(
                            view, "__qualname__", getattr(view, "__name__", str(view))
                        ),
                    }
                )
        return endpoints

    endpoints = extract(urlpatterns)
    for ep in endpoints:
        if ep["route"].startswith("api/ik/"):
            ep["category"] = "ikolu"
        elif ep["route"].startswith("api/"):
            ep["category"] = "legacy"
        elif ep["route"].startswith("admin/"):
            ep["category"] = "admin"
        else:
            ep["category"] = "other"

    out = Path("docs/audit/endpoints_inventory.json")
    out.write_text(json.dumps(endpoints, indent=2, ensure_ascii=False))
    print(f"[audit] {out} ({len(endpoints)} endpoints)")


def generate_markdown():
    """Genera docs/audit/endpoints_inventory.md desde JSON."""
    json_path = Path("docs/audit/endpoints_inventory.json")
    if not json_path.exists():
        print(f"[audit] No existe {json_path}; ejecute --inventory primero.")
        return

    endpoints = json.loads(json_path.read_text(encoding="utf-8"))
    by_category = defaultdict(list)
    for ep in endpoints:
        by_category[ep["category"]].append(ep)

    md_path = Path("docs/audit/endpoints_inventory.md")
    lines = [
        "# Inventario de Endpoints SmartHydro",
        "",
        f"> Generado automáticamente: {datetime.now().isoformat()}",
        f"> Total endpoints: {len(endpoints)} (legacy: {len(by_category['legacy'])}, "
        f"ikolu: {len(by_category['ikolu'])}, admin: {len(by_category['admin'])}, "
        f"other: {len(by_category['other'])})",
        "",
        "## Resumen",
        "",
        "| Categoría | Cantidad |",
        "|-----------|----------|",
        f"| Legacy (`/api/`) | {len(by_category['legacy'])} |",
        f"| Ikolu (`/api/ik/`) | {len(by_category['ikolu'])} |",
        f"| Admin | {len(by_category['admin'])} |",
        f"| Otros | {len(by_category['other'])} |",
        "",
        "---",
        "",
    ]

    for category, title in [
        ("legacy", "Endpoints Legacy (`/api/`)"),
        ("ikolu", "Endpoints Ikolu (`/api/ik/`)"),
        ("admin", "Endpoints Admin"),
        ("other", "Otros Endpoints"),
    ]:
        lines.extend(
            [
                f"## {title}",
                "",
                "| Ruta | Vista | Módulo |",
                "|------|-------|--------|",
            ]
        )
        for ep in sorted(by_category[category], key=lambda x: x["route"]):
            lines.append(
                f"| `{ep['route']}` | `{ep['view']}` | `{ep['view_module']}` |"
            )
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[audit] {md_path}")


def main():
    parser = argparse.ArgumentParser(description="Genera artefactos de auditoría")
    parser.add_argument("--inventory", action="store_true", help="Generar JSON de endpoints")
    parser.add_argument("--markdown", action="store_true", help="Generar Markdown desde JSON")
    parser.add_argument("--all", action="store_true", help="Generar todo")
    args = parser.parse_args()

    if args.all or args.inventory:
        generate_inventory()
    if args.all or args.markdown:
        generate_markdown()


if __name__ == "__main__":
    main()
