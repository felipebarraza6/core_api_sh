#!/usr/bin/env python3
"""
Decomisión del bucket de respaldo en DigitalOcean Spaces.

SEGURO POR DEFECTO: no borra nada salvo que se pase `--confirm`, y aun así
verifica primero que el destino nuevo (GCS) tenga respaldos recientes.

Precheck: exige que existan objetos `*_config.dump` (<= 6h) y `*_telemetry.dump`
(<= 12h) en el bucket GCS configurado.

Credenciales DO (por variable de entorno; si ya migraste el .env a GCS, defínelas):
    DO_SPACE_ENDPOINT, DO_SPACE_REGION, DO_SPACE_BUCKET,
    DO_SPACE_ACCESS_KEY, DO_SPACE_SECRET_KEY

Uso:
    # solo verifica y muestra el plan (no borra)
    docker exec cron_jobs_secure python /app/scripts/decommission_do_spaces.py

    # ejecuta el borrado
    docker exec cron_jobs_secure python /app/scripts/decommission_do_spaces.py --confirm
"""

import argparse
import os
import sys

sys.path.insert(0, "/app")

from api.cronjobs import space_backup as sb


def do_credentials():
    ep = os.environ.get("DO_SPACE_ENDPOINT")
    bucket = os.environ.get("DO_SPACE_BUCKET")
    ak = os.environ.get("DO_SPACE_ACCESS_KEY")
    sk = os.environ.get("DO_SPACE_SECRET_KEY")
    region = os.environ.get("DO_SPACE_REGION", "nyc3")
    # Fallback: si el .env todavía apunta a S3 (DO), usamos eso.
    if not (ep and bucket and ak and sk) and sb.SPACE_BACKEND == "s3":
        ep, bucket, ak, sk = sb.SPACE_ENDPOINT, sb.SPACE_BUCKET, sb.SPACE_ACCESS_KEY, sb.SPACE_SECRET_KEY
        region = sb.SPACE_REGION
    return ep, region, bucket, ak, sk


def gcs_has_fresh_backups():
    """Verifica que GCS tenga config (<6h) y telemetry (<12h)."""
    if sb.SPACE_BACKEND != "gcs":
        print("⚠️  SPACE_BACKEND no es 'gcs'. Cambia el .env y recrea el contenedor antes de decomisionar.")
        return False
    try:
        backend = sb.GCSBackend()
    except Exception as e:
        print(f"❌ No se pudo inicializar GCS: {e}")
        return False

    from datetime import datetime, timedelta

    now = datetime.utcnow()
    newest = {"config": None, "telemetry": None}
    for name, updated, _ in backend.iter_objects(sb.SPACE_PREFIX):
        if name.endswith("_" + sb.CONFIG_SUFFIX):
            if newest["config"] is None or updated > newest["config"]:
                newest["config"] = updated
        elif name.endswith("_" + sb.TELEMETRY_SUFFIX):
            if newest["telemetry"] is None or updated > newest["telemetry"]:
                newest["telemetry"] = updated

    ok = True
    for kind, max_age in (("config", 6), ("telemetry", 12)):
        ts = newest[kind]
        if ts is None:
            print(f"❌ GCS: no hay respaldos de {kind}.")
            ok = False
        elif now - ts > timedelta(hours=max_age):
            print(f"❌ GCS: el {kind} más reciente es de {ts} (>{max_age}h).")
            ok = False
        else:
            print(f"✅ GCS: {kind} más reciente {ts} (OK).")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="Ejecuta el borrado (destructivo).")
    args = ap.parse_args()

    print("== Verificación previa: destino nuevo (GCS) ==")
    if not gcs_has_fresh_backups():
        print("\n⛔ Abortado: el destino nuevo no está sano. NO borres DigitalOcean todavía.")
        sys.exit(1)

    ep, region, bucket, ak, sk = do_credentials()
    if not all([ep, bucket, ak, sk]):
        print("❌ Faltan credenciales de DigitalOcean (DO_SPACE_*).")
        sys.exit(1)

    print("\n== Bucket DigitalOcean a eliminar ==")
    print(f"  endpoint: {ep}")
    print(f"  bucket:   {bucket}")

    import boto3
    from botocore.config import Config

    client = boto3.session.Session().client(
        "s3", region_name=region, endpoint_url=ep,
        aws_access_key_id=ak, aws_secret_access_key=sk,
        config=Config(signature_version="s3v4"),
    )

    total = 0
    objs = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for o in page.get("Contents", []):
            objs.append(o["Key"])
    total = len(objs)
    print(f"  objetos:  {total}")

    if not args.confirm:
        print("\n(Modo dry-run) Nada borrado. Vuelve a ejecutar con --confirm para eliminar.")
        sys.exit(0)

    print("\n🗑️  Borrando objetos …")
    for i in range(0, len(objs), 1000):
        batch = objs[i:i + 1000]
        resp = client.delete_objects(
            Bucket=bucket, Delete={"Objects": [{"Key": k} for k in batch]}
        )
        errs = resp.get("Errors", [])
        if errs:
            print(f"   ⚠️  {len(errs)} errores en lote {i // 1000}")
    print(f"   ✅ {total} objetos borrados.")

    client.delete_bucket(Bucket=bucket)
    print(f"✅ Bucket '{bucket}' eliminado en DigitalOcean.")

    print(
        "\nRecordatorio: revoca la Access Key de Spaces en el panel de DigitalOcean "
        "(API > Spaces keys) para que el gasto quede en $0."
    )


if __name__ == "__main__":
    main()
