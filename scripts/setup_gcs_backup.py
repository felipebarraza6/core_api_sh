#!/usr/bin/env python3
"""
Aprovisiona el bucket de respaldo en Google Cloud Storage.

Usa el service account (JSON) y la API REST de GCS. Idempotente: si el bucket
ya existe, solo ajusta lifecycle/IAM y verifica.

Requisitos:
- Un proyecto GCP con **billing habilitado**.
- El service account con permisos para administrar storage en el bucket.

Uso (recomendado dentro del contenedor cron, que ya trae google-auth):
    docker exec cron_jobs_secure python /app/scripts/setup_gcs_backup.py \
        --project <PROJECT_ID> --bucket smarthydro-backup --location US-EAST1

Opciones:
    --key PATH        JSON del service account (default: GOOGLE_SERVICE_ACCOUNT_FILE)
    --lifecycle-days  Borra objetos más antiguos que N días (default 35)
    --no-iam          No intentar otorgar roles al SA (hazlo tú en la consola)
"""

import argparse
import json
import os
import sys
from datetime import datetime

import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/devstorage.full_control"]
GCS_API = "https://storage.googleapis.com/storage/v1"
GCS_UPLOAD = "https://storage.googleapis.com/upload/storage/v1"


def _default_key_path() -> str:
    p = os.environ.get("SPACE_GCS_CREDENTIALS") or os.environ.get(
        "GOOGLE_SERVICE_ACCOUNT_FILE", "credentials/google_service_account_key.json"
    )
    if not os.path.isabs(p):
        p = os.path.join("/app", p)
    return p


def session_for(key_path: str) -> AuthorizedSession:
    creds = service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)
    return AuthorizedSession(creds)


def get_bucket(s, bucket):
    return s.get(f"{GCS_API}/b/{bucket}")


def create_bucket(s, project, bucket, location):
    body = {
        "name": bucket,
        "location": location,
        "storageClass": "STANDARD",
        "iamConfiguration": {"uniformBucketLevelAccess": {"enabled": True}},
    }
    r = s.post(f"{GCS_API}/b", params={"project": project}, json=body)
    if r.status_code >= 300:
        print(f"❌ No se pudo crear el bucket: {r.status_code}")
        print("   ", r.text[:400].replace("\n", " "))
        if "billing" in r.text.lower():
            print("   → Habilita billing en el proyecto (o usa otro con billing).")
        return False
    print(f"✅ Bucket creado: gs://{bucket} ({location})")
    return True


def set_lifecycle(s, bucket, days):
    body = {
        "lifecycle": {
            "rule": [
                {"action": {"type": "Delete"}, "condition": {"age": days}},
            ]
        }
    }
    r = s.patch(f"{GCS_API}/b/{bucket}", params={"fields": "lifecycle"}, json=body)
    if r.status_code >= 300:
        print(f"⚠️  No se pudo fijar lifecycle: {r.status_code} {r.text[:200]}")
        return
    print(f"✅ Lifecycle: borrar objetos con más de {days} días (red de seguridad).")


def grant_sa(s, bucket, email):
    """Otorga roles/storage.objectAdmin al SA sobre el bucket."""
    url = f"{GCS_API}/b/{bucket}/iam"
    r = s.get(url, params={"optionsRequestedPolicyVersion": 3})
    if r.status_code >= 300:
        print(f"⚠️  No se pudo leer IAM: {r.status_code} {r.text[:200]}")
        return
    policy = r.json()
    role = "roles/storage.objectAdmin"
    member = f"serviceAccount:{email}"
    bindings = policy.setdefault("bindings", [])
    for b in bindings:
        if b.get("role") == role:
            if member not in b.get("members", []):
                b.setdefault("members", []).append(member)
            break
    else:
        bindings.append({"role": role, "members": [member]})
    policy["version"] = 3
    r = s.put(url, json=policy)
    if r.status_code >= 300:
        print(f"⚠️  No se pudo otorgar IAM (hazlo en la consola): {r.status_code} {r.text[:200]}")
        return
    print(f"✅ IAM: {email} → {role} sobre gs://{bucket}")


def verify_roundtrip(s, bucket):
    key = f"_setup_check/{datetime.utcnow():%Y%m%d_%H%M%S}.txt"
    init = s.post(
        f"{GCS_UPLOAD}/b/{bucket}/o",
        params={"uploadType": "resumable", "name": key},
        headers={"Content-Type": "application/json; charset=UTF-8"},
        json={},
    )
    if init.status_code >= 300:
        print(f"❌ Verificación: no se pudo iniciar subida: {init.status_code} {init.text[:200]}")
        return False
    put = s.put(
        init.headers["Location"], data=b"ok",
        headers={"Content-Type": "text/plain", "Content-Length": "2"},
    )
    if put.status_code >= 300:
        print(f"❌ Verificación: subida falló: {put.status_code} {put.text[:200]}")
        return False
    s.delete(f"{GCS_API}/b/{bucket}/o/{requests.utils.quote(key, safe='')}")
    print("✅ Verificación: subida y borrado de un objeto de prueba OK.")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default=_default_key_path())
    ap.add_argument("--project", default=None)
    ap.add_argument("--bucket", default="smarthydro-backup")
    ap.add_argument("--location", default="US-EAST1")
    ap.add_argument("--lifecycle-days", type=int, default=35)
    ap.add_argument("--no-iam", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.key):
        print(f"❌ No existe el service account: {args.key}")
        sys.exit(1)

    info = json.load(open(args.key))
    project = args.project or info.get("project_id")
    email = info["client_email"]
    print(f"Service account: {email}")
    print(f"Proyecto:        {project}")

    s = session_for(args.key)

    r = get_bucket(s, args.bucket)
    if r.status_code == 404:
        print(f"Bucket gs://{args.bucket} no existe → creando …")
        if not create_bucket(s, project, args.bucket, args.location):
            sys.exit(1)
    elif r.status_code == 200:
        print(f"✅ Bucket ya existe: gs://{args.bucket} ({r.json().get('location')})")
    else:
        print(f"❌ Error consultando bucket: {r.status_code} {r.text[:300]}")
        sys.exit(1)

    set_lifecycle(s, args.bucket, args.lifecycle_days)
    if not args.no_iam:
        grant_sa(s, args.bucket, email)
    ok = verify_roundtrip(s, args.bucket)

    print("\n--- Variables para el .env ---")
    print("SPACE_BACKEND=gcs")
    print(f"SPACE_BUCKET={args.bucket}")
    print("SPACE_GCS_CREDENTIALS=credentials/google_service_account_key.json")
    print("\nLuego: docker compose up -d cron_jobs_secure  (para recargar el .env)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
