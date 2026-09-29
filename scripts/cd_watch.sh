#!/usr/bin/env bash
#
# cd_watch.sh — corre cada 5 min por systemd (smarthydro-cd.timer).
# Si origin/production avanzó respecto de lo desplegado, lanza deploy.sh
# (que a su vez exige CI verde + backup + health + rollback).
#
# Interruptores (archivos en backups/deploy/):
#   .cd_disabled   → el CD no hace nada
#   .cd_dry_run    → analiza y no despliega
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
D="$REPO/backups/deploy"
LOG="$D/logs/cd-watch.log"
LAST_SHA_FILE="$D/.last_deployed_sha"

mkdir -p "$D/logs"
say() { printf '[%s] %s\n' "$(date '+%F %T')" "$*" >>"$LOG"; }

if [ -f "$D/.cd_disabled" ]; then exit 0; fi
cd "$REPO"

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  say "CD en pausa: cambios sin commitear en $REPO"
  exit 0
fi
if [ "$(git rev-parse --abbrev-ref HEAD)" != "production" ]; then
  git checkout production >>"$LOG" 2>&1 || { say "no pude cambiarme a production"; exit 0; }
fi
if ! git fetch --prune origin production >>"$LOG" 2>&1; then
  say "fetch de origin/production falló (red?); reintento en 5 min"
  exit 0
fi

TARGET=$(git rev-parse origin/production)
HEAD=$(git rev-parse HEAD)
LAST=$(cat "$LAST_SHA_FILE" 2>/dev/null || true)

if [ -z "$LAST" ]; then
  if [ "$TARGET" = "$HEAD" ]; then
    printf '%s\n' "$TARGET" >"$LAST_SHA_FILE"
    say "primera corrida: ${TARGET:0:7} ya está desplegado, lo registro"
    exit 0
  fi
fi
if [ "$TARGET" = "${LAST:-}" ]; then exit 0; fi   # nada nuevo → silencio

say "origin/production avanzó (${LAST:-sin-registro} → ${TARGET:0:7})"

if [ -f "$D/.cd_dry_run" ]; then
  say "dry-run activo (.cd_dry_run): NO despliego"
  exit 0
fi

exec "$REPO/scripts/deploy.sh"
