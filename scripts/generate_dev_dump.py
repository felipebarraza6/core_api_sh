#!/usr/bin/env python3
"""
Genera un dump de desarrollo (dev_database.sql.gz) con:

- Esquema completo de la base de datos (todas las tablas, índices y FKs)
- Toda la configuración (tablas de catálogo, clientes, puntos, tickets, etc.)
- Solo el último mes de `core_interactiondetail` y `django_admin_log`
  (las tablas grandes de medición no se vuelcan completas)

El dump se restaura con:
    gunzip -c dev_database.sql.gz | psql -U <user> -d <db>

Requiere:
    psycopg2        (pip install psycopg2-binary)
    pg_dump         (PostgreSQL client)

Configuración por variables de entorno (mismas que api/settings.py):
    LOCAL_DB_NAME, LOCAL_DB_USER, LOCAL_DB_PASSWORD, LOCAL_DB_HOST, LOCAL_DB_PORT
"""

import gzip
import os
import subprocess
import sys
import tempfile

import psycopg2

DEFAULT_DAYS = 31

# Tablas que se excluyen del dump de configuración y se vuelcan filtradas aparte
FILTERED_TABLES = {
    "core_interactiondetail": "date_time_medition",
    "django_admin_log": "action_time",
}


def env(name, default=""):
    return os.environ.get(name, default)


def run_pg_dump(base_name, host, port, user, dbname, password, days):
    excludes = ["--exclude-table-data=public.%s" % t for t in FILTERED_TABLES]
    env_pg = dict(os.environ, PGPASSWORD=password)
    cmd = [
        "pg_dump",
        "--no-owner",
        "--no-privileges",
        "-h", host,
        "-p", str(port),
        "-U", user,
        "-d", dbname,
    ] + excludes
    print("Ejecutando pg_dump (esquema + configuración)...")
    with open(base_name, "w") as f:
        subprocess.run(cmd, stdout=f, check=True, env=env_pg)
    print("  OK -> %s" % base_name)


def write_filtered_blocks(conn, out, days):
    cur = conn.cursor()
    for table, date_col in FILTERED_TABLES.items():
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        cols = [r[0] for r in cur.fetchall()]
        col_list = ", ".join('"%s"' % c for c in cols)
        where = "%s >= now() - interval '%d days'" % (date_col, days)
        query = "COPY (SELECT * FROM public.%s WHERE %s) TO STDOUT" % (table, where)
        out.write(("COPY public.%s (%s) FROM stdin;\n" % (table, col_list)).encode())
        cur.copy_expert(query, out)
        out.write(b"\\.\n")
        print("  FILTRADO %s: %d filas (%d días)" % (table, cur.rowcount, days))


def main():
    host = env("LOCAL_DB_HOST", "127.0.0.1")
    port = env("LOCAL_DB_PORT", "5432")
    user = env("LOCAL_DB_USER", "smarthydro_user")
    dbname = env("LOCAL_DB_NAME", "smarthydro_prod")
    password = env("LOCAL_DB_PASSWORD", "")
    days = int(env("DEV_DUMP_DAYS", str(DEFAULT_DAYS)))
    output = env("DEV_DUMP_OUTPUT", "dev_database.sql.gz")

    if not password:
        print("Falta LOCAL_DB_PASSWORD. Cargue .env o exporte las variables.", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(
        host=host, port=int(port), user=user, password=password, dbname=dbname
    )

    with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp:
        base_name = tmp.name

    try:
        run_pg_dump(base_name, host, port, user, dbname, password, days)

        with open(base_name, "rb") as base_f, gzip.open(output, "wb") as out:
            print("Volcando esquema + configuración...")
            for chunk in iter(lambda: base_f.read(1024 * 1024), b""):
                out.write(chunk)
            print("Agregando bloques COPY filtrados (último mes)...")
            write_filtered_blocks(conn, out, days)
    finally:
        conn.close()
        os.unlink(base_name)

    print("Dump generado: %s" % output)


if __name__ == "__main__":
    main()
