#!/usr/bin/env python3
"""
RESPALDO A DIGITALOCEAN SPACES
==============================
Backup completo cada hora de:
- Config (tablas core_*)      → config.dump
- Mediciones (InteractionDetail) → telemetry.dump

Retención: completos 14 días (configurable via .env)
"""

import os
import subprocess
import tempfile
import time
from datetime import datetime, timedelta


# ---------------------------------------------------------------
# Cargar .env
# ---------------------------------------------------------------
def _load_env():
    env_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
    )
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key, value)


_load_env()

# ---------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------
SPACE_ENABLED = os.environ.get("SPACE_BACKUP_ENABLED", "true").lower() == "true"
SPACE_ENDPOINT = os.environ.get("SPACE_ENDPOINT", "https://nyc3.digitaloceanspaces.com")
SPACE_BUCKET = os.environ.get("SPACE_BUCKET", "smarthydro-data")
SPACE_ACCESS_KEY = os.environ.get("SPACE_ACCESS_KEY", "")
SPACE_SECRET_KEY = os.environ.get("SPACE_SECRET_KEY", "")
SPACE_PREFIX = os.environ.get("SPACE_BACKUP_PREFIX", "smarthydro_backup")

LOCAL_DB_HOST = os.environ.get("LOCAL_DB_HOST", "postgres")
LOCAL_DB_PORT = os.environ.get("LOCAL_DB_PORT", "5432")
LOCAL_DB_USER = os.environ.get("LOCAL_DB_USER", "smarthydro_user")
LOCAL_DB_PASSWORD = os.environ.get("LOCAL_DB_PASSWORD", "")
LOCAL_DB_NAME = os.environ.get("LOCAL_DB_NAME", "smarthydro_prod")

RETENTION_DAYS = int(os.environ.get("SPACE_RETENTION_DAYS", "14"))

OPERATIONAL_TABLES = [
    "core_client", "core_user", "core_user_groups", "core_user_user_permissions",
    "core_typefilecatchment", "core_registerpersons", "core_projectcatchments",
    "core_schemescatchment", "core_variable", "core_catchmentpoint",
    "core_dgadataconfigcatchment", "core_profiledataconfigcatchment",
    "core_profileikolucatchment", "core_filecatchment",
    "core_catchmentpoint_users_viewers", "core_schemescatchment_points_catchment",
    "core_notificationscatchment", "core_responsenotificationscatchment",
]


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def _ts():
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _s3_key(suffix: str) -> str:
    now = datetime.utcnow()
    ts = now.strftime("%H%M%S")
    return f"{SPACE_PREFIX}/{now:%Y/%m/%d}/{ts}_{suffix}"


def _pg_env():
    env = os.environ.copy()
    env["PGPASSWORD"] = LOCAL_DB_PASSWORD
    return env


def _run_pg_dump(output_path: str, table_patterns=None, single_table=None) -> bool:
    cmd = [
        "pg_dump", "-h", LOCAL_DB_HOST, "-p", LOCAL_DB_PORT,
        "-U", LOCAL_DB_USER, "-d", LOCAL_DB_NAME, "-Fc",
        "--no-owner", "--no-privileges",
    ]
    if single_table:
        cmd.extend(["-t", single_table])
    elif table_patterns:
        for pat in table_patterns:
            cmd.extend(["-t", pat])
    cmd.extend(["-f", output_path])

    print(f"  🗃️  pg_dump → {os.path.basename(output_path)} …")
    start = time.time()
    try:
        subprocess.run(cmd, env=_pg_env(), capture_output=True, text=True, check=True)
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"     ✅ {size_mb:.1f} MB en {time.time() - start:.1f}s")
        return True
    except subprocess.CalledProcessError as e:
        print(f"     ❌ Falló: {e.stderr[:300] if e.stderr else 'unknown'}")
        return False
    except FileNotFoundError:
        print("     ❌ pg_dump no encontrado")
        return False


def _get_s3_client():
    import boto3
    from botocore.config import Config
    if not SPACE_ACCESS_KEY or not SPACE_SECRET_KEY:
        raise RuntimeError("Faltan credenciales S3")
    session = boto3.session.Session()
    return session.client(
        "s3", region_name="nyc3", endpoint_url=SPACE_ENDPOINT,
        aws_access_key_id=SPACE_ACCESS_KEY, aws_secret_access_key=SPACE_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def _upload(local_path: str, key: str) -> bool:
    try:
        s3 = _get_s3_client()
        print(f"  ☁️  Subiendo a s3://{SPACE_BUCKET}/{key} …")
        start = time.time()
        s3.upload_file(local_path, SPACE_BUCKET, key)
        print(f"     ✅ Subido en {time.time() - start:.1f}s")
        return True
    except Exception as e:
        print(f"     ❌ Error subiendo: {e}")
        return False


def _cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


# ---------------------------------------------------------------
# Retención
# ---------------------------------------------------------------
def _cleanup_old_backups():
    try:
        s3 = _get_s3_client()
        print("\n🧹 Limpiando backups antiguos …")
        cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
        paginator = s3.get_paginator("list_objects_v2")
        deleted = 0
        for page in paginator.paginate(Bucket=SPACE_BUCKET, Prefix=SPACE_PREFIX):
            for obj in page.get("Contents", []):
                if obj["LastModified"].replace(tzinfo=None) < cutoff:
                    s3.delete_object(Bucket=SPACE_BUCKET, Key=obj["Key"])
                    deleted += 1
        print(f"     🗑️  Borrados (> {RETENTION_DAYS} días): {deleted}")
    except Exception as e:
        print(f"     ⚠️  Error limpiando: {e}")


# ---------------------------------------------------------------
# Flujo principal
# ---------------------------------------------------------------
def run():
    start_global = time.time()
    print(f"[{_ts()}] Iniciando backup completo a Spaces …")

    if not SPACE_ENABLED:
        print("SPACE_BACKUP_ENABLED=false → abortando.")
        return False

    tmpdir = tempfile.mkdtemp(prefix="space_backup_")
    config_path = os.path.join(tmpdir, "config.dump")
    telemetry_path = os.path.join(tmpdir, "telemetry.dump")
    ok_config = False
    ok_telemetry = False

    try:
        print("\n🔄 BACKUP 1: Configuración operativa (core_*)")
        patterns = [f"public.{t}" for t in OPERATIONAL_TABLES]
        if _run_pg_dump(config_path, table_patterns=patterns):
            ok_config = _upload(config_path, _s3_key("config.dump"))

        print("\n🔄 BACKUP 2: Mediciones (InteractionDetail)")
        if _run_pg_dump(telemetry_path, single_table="public.core_interactiondetail"):
            ok_telemetry = _upload(telemetry_path, _s3_key("telemetry.dump"))

    finally:
        _cleanup(config_path, telemetry_path)
        try:
            os.rmdir(tmpdir)
        except Exception:
            pass

    _cleanup_old_backups()

    elapsed = time.time() - start_global
    status = "exitoso" if (ok_config and ok_telemetry) else "parcial" if (ok_config or ok_telemetry) else "fallido"
    print(f"\n[{_ts()}] Backup {status} en {elapsed:.1f}s")
    print(f"   Config:     {'✅' if ok_config else '❌'}")
    print(f"   Telemetry:  {'✅' if ok_telemetry else '❌'}")
    return ok_config and ok_telemetry


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
