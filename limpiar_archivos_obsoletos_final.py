#!/usr/bin/env python3
"""
Script para limpiar archivos obsoletos del proyecto.

Este script identifica y elimina:
- Archivos .bak, .backup, .bak-*
- Directorios de backup antiguos
- Archivos de prueba y debug obsoletos
- Archivos duplicados

IMPORTANTE: Revisa la lista antes de ejecutar con --execute
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Directorio raíz del proyecto
BASE_DIR = Path(__file__).parent

# Patrones de archivos a eliminar
PATTERNS_TO_REMOVE = [
    # Archivos de backup
    '**/*.bak',
    '**/*.backup',
    '**/*.bak-*',
    '**/*.backup-*',
    '**/*.bak_*',
    '**/*.backup_*',
    '**/*.stream.patch.bak',
    
    # Archivos de prueba y debug
    'debug_*.py',
    'test_*.py',
    'probar_*.py',
    'ejemplo_*.py',
    'consultar_*.py',
    'simulate_*.py',
    
    # Archivos de configuración obsoletos
    '**/*.backup-cors',
    '**/*.backup-before-fix',
    '**/*.backup2',
]

# Directorios completos a eliminar
DIRECTORIES_TO_REMOVE = [
    'api/cronjobs/telemetry_backup_20250819_0234',
    'maintenance/backup_cluster_20250813_023409',
    'backup_local',
    'backups',
]

# Archivos específicos a mantener (no eliminar)
FILES_TO_KEEP = [
    'api/cronjobs/test_single_backup.py',  # Puede ser útil
    'limpiar_archivos_obsoletos.sh',  # Script de limpieza
    'limpiar_archivos_obsoletos_final.py',  # Este script
]


def find_files_to_remove():
    """Encuentra todos los archivos que coinciden con los patrones."""
    files_to_remove = []
    
    # Buscar por patrones
    for pattern in PATTERNS_TO_REMOVE:
        for file_path in BASE_DIR.glob(pattern):
            if file_path.is_file() and str(file_path) not in FILES_TO_KEEP:
                files_to_remove.append(file_path)
    
    # Buscar directorios
    for dir_pattern in DIRECTORIES_TO_REMOVE:
        dir_path = BASE_DIR / dir_pattern
        if dir_path.exists() and dir_path.is_dir():
            # Agregar todos los archivos del directorio
            for file_path in dir_path.rglob('*'):
                if file_path.is_file():
                    files_to_remove.append(file_path)
            # Agregar el directorio mismo
            files_to_remove.append(dir_path)
    
    # Eliminar duplicados y ordenar
    files_to_remove = sorted(set(files_to_remove))
    
    return files_to_remove


def get_file_size(file_path):
    """Obtiene el tamaño de un archivo o directorio."""
    if file_path.is_file():
        return file_path.stat().st_size
    elif file_path.is_dir():
        total = 0
        for f in file_path.rglob('*'):
            if f.is_file():
                total += f.stat().st_size
        return total
    return 0


def format_size(size_bytes):
    """Formatea el tamaño en bytes a formato legible."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def main():
    """Función principal."""
    print("=" * 80)
    print("LIMPIEZA DE ARCHIVOS OBSOLETOS")
    print("=" * 80)
    print()
    
    # Buscar archivos
    print("Buscando archivos obsoletos...")
    files_to_remove = find_files_to_remove()
    
    if not files_to_remove:
        print("✅ No se encontraron archivos obsoletos para eliminar.")
        return
    
    # Calcular tamaño total
    total_size = sum(get_file_size(f) for f in files_to_remove)
    
    # Mostrar resumen
    print(f"\n📋 RESUMEN:")
    print(f"   - Archivos/directorios encontrados: {len(files_to_remove)}")
    print(f"   - Espacio a liberar: {format_size(total_size)}")
    print()
    
    # Agrupar por tipo
    files_by_type = {
        'backup': [],
        'test_debug': [],
        'directories': [],
        'other': []
    }
    
    for file_path in files_to_remove:
        if file_path.is_dir():
            files_by_type['directories'].append(file_path)
        elif any(pattern in str(file_path) for pattern in ['.bak', '.backup']):
            files_by_type['backup'].append(file_path)
        elif any(pattern in str(file_path) for pattern in ['debug_', 'test_', 'probar_', 'ejemplo_']):
            files_by_type['test_debug'].append(file_path)
        else:
            files_by_type['other'].append(file_path)
    
    # Mostrar lista detallada
    print("📁 ARCHIVOS A ELIMINAR:")
    print()
    
    if files_by_type['backup']:
        print(f"  🔹 Archivos de backup ({len(files_by_type['backup'])}):")
        for f in sorted(files_by_type['backup'])[:20]:  # Mostrar primeros 20
            print(f"     - {f.relative_to(BASE_DIR)}")
        if len(files_by_type['backup']) > 20:
            print(f"     ... y {len(files_by_type['backup']) - 20} más")
        print()
    
    if files_by_type['test_debug']:
        print(f"  🔹 Archivos de prueba/debug ({len(files_by_type['test_debug'])}):")
        for f in sorted(files_by_type['test_debug']):
            print(f"     - {f.relative_to(BASE_DIR)}")
        print()
    
    if files_by_type['directories']:
        print(f"  🔹 Directorios completos ({len(files_by_type['directories'])}):")
        for d in sorted(files_by_type['directories']):
            size = get_file_size(d)
            print(f"     - {d.relative_to(BASE_DIR)} ({format_size(size)})")
        print()
    
    if files_by_type['other']:
        print(f"  🔹 Otros archivos ({len(files_by_type['other'])}):")
        for f in sorted(files_by_type['other'])[:10]:
            print(f"     - {f.relative_to(BASE_DIR)}")
        if len(files_by_type['other']) > 10:
            print(f"     ... y {len(files_by_type['other']) - 10} más")
        print()
    
    # Verificar si se debe ejecutar
    if '--execute' not in sys.argv:
        print("⚠️  MODO PREVIEW - No se eliminará nada")
        print()
        print("Para ejecutar la limpieza, ejecuta:")
        print(f"   python3 {sys.argv[0]} --execute")
        print()
        return
    
    # Confirmar
    print("⚠️  ADVERTENCIA: Esta acción no se puede deshacer.")
    response = input("¿Deseas continuar? (escribe 'SI' para confirmar): ")
    
    if response != 'SI':
        print("❌ Operación cancelada.")
        return
    
    # Eliminar archivos
    print()
    print("🗑️  Eliminando archivos...")
    
    removed_count = 0
    removed_size = 0
    errors = []
    
    for file_path in files_to_remove:
        try:
            size = get_file_size(file_path)
            if file_path.is_dir():
                import shutil
                shutil.rmtree(file_path)
            else:
                file_path.unlink()
            removed_count += 1
            removed_size += size
            print(f"   ✓ {file_path.relative_to(BASE_DIR)}")
        except Exception as e:
            errors.append((file_path, str(e)))
            print(f"   ✗ Error eliminando {file_path.relative_to(BASE_DIR)}: {e}")
    
    # Resumen final
    print()
    print("=" * 80)
    print("✅ LIMPIEZA COMPLETADA")
    print("=" * 80)
    print(f"   - Archivos eliminados: {removed_count}")
    print(f"   - Espacio liberado: {format_size(removed_size)}")
    
    if errors:
        print(f"   - Errores: {len(errors)}")
        for file_path, error in errors:
            print(f"     - {file_path.relative_to(BASE_DIR)}: {error}")
    
    print()


if __name__ == '__main__':
    main()

