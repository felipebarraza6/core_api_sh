#!/usr/bin/env python
"""Genera Markdown a partir de endpoints_inventory.json."""
import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime


def main():
    json_path = Path("docs/audit/endpoints_inventory.json")
    endpoints = json.loads(json_path.read_text(encoding="utf-8"))

    by_category = defaultdict(list)
    for ep in endpoints:
        by_category[ep["category"]].append(ep)

    md_path = Path("docs/audit/endpoints_inventory.md")
    lines = [
        "# Inventario de Endpoints SmartHydro",
        "",
        f"> Generado automáticamente: {datetime.now().isoformat()}",
        f"> Total endpoints: {len(endpoints)} (legacy: {len(by_category['legacy'])}, ikolu: {len(by_category['ikolu'])}, admin: {len(by_category['admin'])}, other: {len(by_category['other'])})",
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
        lines.extend([
            f"## {title}",
            "",
            "| Ruta | Vista | Módulo |",
            "|------|-------|--------|",
        ])
        for ep in sorted(by_category[category], key=lambda x: x["route"]):
            lines.append(
                f"| `{ep['route']}` | `{ep['view']}` | `{ep['view_module']}` |"
            )
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Markdown generado: {md_path}")


if __name__ == "__main__":
    main()
