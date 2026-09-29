#!/usr/bin/env bash
# Aplica los overrides de conf/nginx-conf.d/ al contenedor nginx_proxy
# (edge real: nginx-proxy 1.6) y recarga nginx sin reiniciar el proxy.
#
# El volumen /etc/nginx/conf.d pertenece al contenedor, no al repo: hay que
# re-ejecutar este script si se recrea el contenedor nginx_proxy.
#
# Uso: conf/apply_nginx_proxy_conf.sh

set -euo pipefail

CONTAINER="${NGINX_PROXY_CONTAINER:-nginx_proxy}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/nginx-conf.d"

if [[ ! -d "$SRC_DIR" ]]; then
    echo "ERROR: no existe ${SRC_DIR}" >&2
    exit 1
fi

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    echo "ERROR: no existe el contenedor ${CONTAINER}" >&2
    exit 1
fi

for f in "$SRC_DIR"/*.conf; do
    name="$(basename "$f")"
    echo "[1/4] Copiando ${name} -> ${CONTAINER}:/etc/nginx/conf.d/${name}"
    docker cp "$f" "${CONTAINER}:/etc/nginx/conf.d/${name}"
done

echo "[2/4] Validando configuración (nginx -t)"
docker exec "$CONTAINER" nginx -t

echo "[3/4] Recargando nginx"
docker exec "$CONTAINER" nginx -s reload

echo "[4/4] Verificando límite activo"
docker exec "$CONTAINER" sh -c 'grep -H client_max_body_size /etc/nginx/conf.d/*.conf'

echo "OK: overrides aplicados y recargados."
