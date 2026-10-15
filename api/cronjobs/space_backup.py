#!/usr/bin/env python3
"""
RESPALDO A OBJECT STORAGE
=========================
Backup de la base de datos a un bucket, con dos backends:

- `SPACE_BACKEND=s3`  -> cualquier storage S3-compatible (DO Spaces, etc.) vía boto3.
- `SPACE_BACKEND=gcs` -> Google Cloud Storage vía REST + service account
                         (tokens de corta vida, sin claves HMAC estáticas y sin
                          dependencias nuevas: usa google-auth + requests).

Qué se respalda:
- Config operativa (tablas core_*)  -> config.dump    en cada corrida
- Mediciones (InteractionDetail)    -> telemetry.dump cada N horas

El cron se dispara cada hora (`0 * * * *`). Internamente se decide si
corresponde dumpear la telemetría según `SPACE_TELEMETRY_EVERY_HOURS`,
para no redumpear millones de filas que casi no cambian.

Retención independiente por tipo:
- SPACE_CONFIG_RETENTION_DAYS    (default 30)
- SPACE_TELEMETRY_RETENTION_DAYS (default 14)

Modos de ejecución manual:
    python -m api.cronjobs.space_backup check      # config y si toca telemetría
    python -m api.cronjobs.space_backup config     # solo config
    python -m api.cronjobs.space_backup telemetry  # solo telemetría
    python -m api.cronjobs.space_backup            # flujo completo (como el cron)
"""

import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from urllib.parse import quote


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
SPACE_BACKEND = os.environ.get("SPACE_BACKEND", "s3").strip().lower()
SPACE_BUCKET = os.environ.get("SPACE_BUCKET", "smarthydro-data")
SPACE_PREFIX = os.environ.get("SPACE_BACKUP_PREFIX", "smarthydro_backup")

# Backend s3 (DO Spaces / S3-compatible)
SPACE_ENDPOINT = os.environ.get("SPACE_ENDPOINT", "https://nyc3.digitaloceanspaces.com")
SPACE_REGION = os.environ.get("SPACE_REGION", "nyc3")
SPACE_ACCESS_KEY = os.environ.get("SPACE_ACCESS_KEY", "")
SPACE_SECRET_KEY = os.environ.get("SPACE_SECRET_KEY", "")

# Backend gcs (service account JSON)
GCS_SCOPES = ["https://www.googleapis.com/auth/devstorage.read_write"]

LOCAL_DB_HOST = os.environ.get("LOCAL_DB_HOST", "postgres")
LOCAL_DB_PORT = os.environ.get("LOCAL_DB_PORT", "5432")
LOCAL_DB_USER = os.environ.get("LOCAL_DB_USER", "smarthydro_user")
LOCAL_DB_PASSWORD = os.environ.get("LOCAL_DB_PASSWORD", "")
LOCAL_DB_NAME = os.environ.get("LOCAL_DB_NAME", "smarthydro_prod")

TELEMETRY_EVERY_HOURS = int(os.environ.get("SPACE_TELEMETRY_EVERY_HOURS", "6"))

_LEGACY_RETENTION = os.environ.get("SPACE_RETENTION_DAYS")
CONFIG_RETENTION_DAYS = int(
    os.environ.get("SPACE_CONFIG_RETENTION_DAYS", _LEGACY_RETENTION or "30")
)
TELEMETRY_RETENTION_DAYS = int(
    os.environ.get("SPACE_TELEMETRY_RETENTION_DAYS", _LEGACY_RETENTION or "14")
)

CONFIG_SUFFIX = "config.dump"
TELEMETRY_SUFFIX = "telemetry.dump"

OPERATIONAL_TABLES = [
    "core_client", "core_user", "core_user_groups", "core_user_user_permissions",
    "core_typefilecatchment", "core_registerpersons", "core_projectcatchments",
    "core_schemescatchment", "core_variable", "core_catchmentpoint",
    "core_dgadataconfigcatchment", "core_profiledataconfigcatchment",
    "core_profileikolucatchment", "core_filecatchment",
    "core_catchmentpoint_users_viewers", "core_schemescatchment_points_catchment",
    "core_notificationscatchment", "core_responsenotificationscatchment",
]


def _gcs_credentials_path() -> str:
    """Ruta al JSON del service account para GCS."""
    p = os.environ.get("SPACE_GCS_CREDENTIALS", "").strip()
    if not p:
        p = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if not p:
        p = "credentials/google_service_account_key.json"
    if not os.path.isabs(p):
        p = os.path.join("/app", p)
    return p


# ---------------------------------------------------------------
# Backends de almacenamiento
# ---------------------------------------------------------------
class S3Backend:
    """Storage S3-compatible (DO Spaces, etc.) vía boto3."""

    name = "s3"

    def __init__(self):
        if not SPACE_ACCESS_KEY or not SPACE_SECRET_KEY:
            raise RuntimeError("Faltan credenciales S3 (SPACE_ACCESS_KEY/SECRET)")
        import boto3
        from botocore.config import Config

        self._bucket = SPACE_BUCKET
        self._client = boto3.session.Session().client(
            "s3", region_name=SPACE_REGION, endpoint_url=SPACE_ENDPOINT,
            aws_access_key_id=SPACE_ACCESS_KEY, aws_secret_access_key=SPACE_SECRET_KEY,
            config=Config(signature_version="s3v4"),
        )

    def upload(self, local_path: str, key: str) -> None:
        self._client.upload_file(local_path, self._bucket, key)

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def iter_objects(self, prefix: str):
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"], obj["LastModified"].replace(tzinfo=None), obj["Size"]


class GCSBackend:
    """Google Cloud Storage vía REST (google-auth + requests)."""

    name = "gcs"
    _API = "https://storage.googleapis.com/storage/v1"
    _UPLOAD = "https://storage.googleapis.com/upload/storage/v1"

    def __init__(self):
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession

        cred_path = _gcs_credentials_path()
        if not os.path.exists(cred_path):
            raise RuntimeError(f"No existe el service account: {cred_path}")
        creds = service_account.Credentials.from_service_account_file(
            cred_path, scopes=GCS_SCOPES
        )
        self._session = AuthorizedSession(creds)
        self._bucket = SPACE_BUCKET

    def upload(self, local_path: str, key: str) -> None:
        # Subida resumible: inicia sesión y sube el archivo en un PUT.
        init = self._session.post(
            f"{self._UPLOAD}/b/{self._bucket}/o",
            params={"uploadType": "resumable", "name": key},
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "application/octet-stream",
            },
            json={},
        )
        init.raise_for_status()
        session_uri = init.headers["Location"]
        size = os.path.getsize(local_path)
        with open(local_path, "rb") as f:
            # El session_uri ya está autenticado: no re-enviar Authorization.
            put = self._session.put(
                session_uri, data=f,
                headers={
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(size),
                },
            )
        put.raise_for_status()

    def delete(self, key: str) -> None:
        r = self._session.delete(
            f"{self._API}/b/{self._bucket}/o/{quote(key, safe='')}"
        )
        if r.status_code not in (200, 204):
            r.raise_for_status()

    def iter_objects(self, prefix: str):
        params = {
            "prefix": prefix,
            "fields": "items(name,updated,size),nextPageToken",
            "maxResults": 1000,
        }
        while True:
            r = self._session.get(f"{self._API}/b/{self._bucket}/o", params=params)
            r.raise_for_status()
            data = r.json()
            for it in data.get("items", []):
                updated = datetime.fromisoformat(
                    it["updated"].replace("Z", "+00:00")
                ).replace(tzinfo=None)
                yield it["name"], updated, int(it.get("size", 0))
            token = data.get("nextPageToken")
            if not token:
                break
            params["pageToken"] = token


def _get_backend():
    if SPACE_BACKEND == "gcs":
        return GCSBackend()
    return S3Backend()


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


def _upload(local_path: str, key: str, backend) -> bool:
    try:
        print(f"  ☁️  Subiendo a {SPACE_BACKEND}://{SPACE_BUCKET}/{key} …")
        start = time.time()
        backend.upload(local_path, key)
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


def _safe_rmdir(path):
    try:
        os.rmdir(path)
    except Exception:
        pass


# ---------------------------------------------------------------
# Retención (por tipo, en una sola pasada)
# ---------------------------------------------------------------
def _cleanup_old_backups(backend):
    try:
        print("\n🧹 Limpiando backups antiguos …")
        now = datetime.utcnow()
        cutoffs = {
            CONFIG_SUFFIX: now - timedelta(days=CONFIG_RETENTION_DAYS),
            TELEMETRY_SUFFIX: now - timedelta(days=TELEMETRY_RETENTION_DAYS),
        }
        deleted = {"config": 0, "telemetry": 0}
        for name, updated, _size in backend.iter_objects(SPACE_PREFIX):
            kind = next((s for s in cutoffs if name.endswith("_" + s)), None)
            if not kind:
                continue
            if updated < cutoffs[kind]:
                backend.delete(name)
                deleted["config" if kind == CONFIG_SUFFIX else "telemetry"] += 1
        print(
            f"     🗑️  Borrados → config: {deleted['config']} (> {CONFIG_RETENTION_DAYS}d), "
            f"telemetry: {deleted['telemetry']} (> {TELEMETRY_RETENTION_DAYS}d)"
        )
    except Exception as e:
        print(f"     ⚠️  Error limpiando: {e}")


def _telemetry_due(now=None) -> bool:
    now = now or datetime.utcnow()
    if TELEMETRY_EVERY_HOURS <= 1:
        return True
    return now.hour % TELEMETRY_EVERY_HOURS == 0


# ---------------------------------------------------------------
# Backups individuales
# ---------------------------------------------------------------
def run_config_backup(backend) -> bool:
    """Dump de config operativa (core_*)."""
    print("\n🔄 BACKUP 1: Configuración operativa (core_*)")
    tmpdir = tempfile.mkdtemp(prefix="space_backup_")
    config_path = os.path.join(tmpdir, "config.dump")
    try:
        patterns = [f"public.{t}" for t in OPERATIONAL_TABLES]
        if _run_pg_dump(config_path, table_patterns=patterns):
            return _upload(config_path, _s3_key(CONFIG_SUFFIX), backend)
        return False
    finally:
        _cleanup(config_path)
        _safe_rmdir(tmpdir)


def run_telemetry_backup(backend) -> bool:
    """Dump de mediciones (InteractionDetail)."""
    print("\n🔄 BACKUP 2: Mediciones (InteractionDetail)")
    tmpdir = tempfile.mkdtemp(prefix="space_backup_")
    telemetry_path = os.path.join(tmpdir, "telemetry.dump")
    try:
        if _run_pg_dump(telemetry_path, single_table="public.core_interactiondetail"):
            return _upload(telemetry_path, _s3_key(TELEMETRY_SUFFIX), backend)
        return False
    finally:
        _cleanup(telemetry_path)
        _safe_rmdir(tmpdir)


# ---------------------------------------------------------------
# Flujo principal (llamado por el cron)
# ---------------------------------------------------------------
def run() -> bool:
    start_global = time.time()
    print(f"[{_ts()}] Iniciando backup ({SPACE_BACKEND}) …")

    if not SPACE_ENABLED:
        print("SPACE_BACKUP_ENABLED=false → abortando.")
        return False

    try:
        backend = _get_backend()
    except Exception as e:
        print(f"❌ No se pudo inicializar el backend ({SPACE_BACKEND}): {e}")
        return False

    ok_config = run_config_backup(backend)

    ok_telemetry = True
    skipped = False
    if _telemetry_due():
        ok_telemetry = run_telemetry_backup(backend)
    else:
        skipped = True
        print(
            f"\n⏭️  Telemetría omitida (cada {TELEMETRY_EVERY_HOURS}h; "
            f"hora UTC actual {datetime.utcnow().hour})"
        )

    _cleanup_old_backups(backend)

    elapsed = time.time() - start_global
    if ok_config and ok_telemetry:
        status = "exitoso"
    elif skipped and ok_config:
        status = "exitoso (telemetría omitida)"
    elif ok_config or ok_telemetry:
        status = "parcial"
    else:
        status = "fallido"
    print(f"\n[{_ts()}] Backup {status} en {elapsed:.1f}s")
    print(f"   Config:     {'✅' if ok_config else '❌'}")
    print(f"   Telemetry:  {'⏭️' if skipped else ('✅' if ok_telemetry else '❌')}")
    return ok_config and ok_telemetry


def _print_config():
    print("Configuración de respaldo:")
    print(f"  enabled:            {SPACE_ENABLED}")
    print(f"  backend:            {SPACE_BACKEND}")
    print(f"  bucket:             {SPACE_BUCKET}")
    print(f"  prefix:             {SPACE_PREFIX}")
    if SPACE_BACKEND == "gcs":
        print(f"  credenciales:       {_gcs_credentials_path()}")
    else:
        print(f"  endpoint:           {SPACE_ENDPOINT}")
        print(f"  region:             {SPACE_REGION}")
        print(f"  credenciales:       {'OK' if (SPACE_ACCESS_KEY and SPACE_SECRET_KEY) else 'FALTAN'}")
    print(f"  telemetry cada:     {TELEMETRY_EVERY_HOURS}h")
    print(f"  retención config:   {CONFIG_RETENTION_DAYS}d")
    print(f"  retención telemetry:{TELEMETRY_RETENTION_DAYS}d")
    print(f"  ¿telemetría ahora?: {'sí' if _telemetry_due() else 'no (omitida)'}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"

    if mode == "check":
        _print_config()
        sys.exit(0)
    if mode == "config":
        sys.exit(0 if run_config_backup(_get_backend()) else 1)
    if mode == "telemetry":
        sys.exit(0 if run_telemetry_backup(_get_backend()) else 1)
    sys.exit(0 if run() else 1)
