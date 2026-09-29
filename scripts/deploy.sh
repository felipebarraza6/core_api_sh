#!/usr/bin/env bash
#
# deploy.sh — despliegue seguro de core_api_sh (CD)
#
# Orden:  preflight → gate CI verde → backup BD → git ff → migrate
#         → restart → health check → si algo falla: ROLLBACK automático
#
# Uso:
#   scripts/deploy.sh                     despliega origin/production
#   scripts/deploy.sh --dry-run           solo analiza, no toca nada
#   scripts/deploy.sh --ref <tag|sha>     despliega un commit concreto
#   scripts/deploy.sh --force             salta el gate de CI (solo emergencias)
#   scripts/deploy.sh --simulate-failure  prueba el mecanismo de rollback
#   scripts/deploy.sh --no-migrate        sin migrate (solo código)
#
# Códigos de salida: 0 ok · 1 abortado · 2 crítico (API caída) · 3 rollback ok
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="production"
APP_CONTAINER="django_api_secure"
CRON_CONTAINER="cron_jobs_secure"
EDGE_HOST="api.smarthydro.app"
HEALTH_PATH="/health/"
DUMP_DIR="$REPO/backups/deploy"
LOG_DIR="$DUMP_DIR/logs"
LAST_SHA_FILE="$DUMP_DIR/.last_deployed_sha"
LOCK_FILE="/var/lock/smarthydro-deploy.lock"
KEEP_DUMPS=10
HEALTH_RETRIES=12
HEALTH_SLEEP=5

DRY_RUN=0
FORCE=0
NO_MIGRATE=0
SIMULATE_FAILURE=0
REF_GIVEN=0
REF=""

usage() {
  sed -n '3,17p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --force) FORCE=1 ;;
    --no-migrate) NO_MIGRATE=1 ;;
    --simulate-failure) SIMULATE_FAILURE=1 ;;
    --ref) shift; REF="${1:-}"; REF_GIVEN=1 ;;
    --ref=*) REF="${1#--ref=}"; REF_GIVEN=1 ;;
    -h|--help) usage 0 ;;
    *) echo "opción desconocida: $1" >&2; usage 1 ;;
  esac
  shift
done

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/deploy-$(date +%Y%m%d-%H%M%S).log"

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG_FILE"; }
die() {
  log "✗ ERROR: $*"
  log "  deploy abortado: la BD y el código quedan como estaban"
  exit 1
}

# ── lock: nunca dos deploys a la vez ─────────────────────────────────────────
exec 9>"$LOCK_FILE"
flock -n 9 || die "ya hay un deploy en curso (lock: $LOCK_FILE)"

[ "$(id -u)" -eq 0 ] || die "hay que correr como root (docker + git)"

# ── preflight ────────────────────────────────────────────────────────────────
cd "$REPO"
[ -d .git ] || die "no es un repo git: $REPO"
[ -n "$(git status --porcelain --untracked-files=no)" ] && die "hay cambios locales sin commitear"
if [ "$(git rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]; then
  log "estoy en '$(git rev-parse --abbrev-ref HEAD)', cambiando a $BRANCH"
  git checkout "$BRANCH" >/dev/null 2>&1 || die "no se pudo cambiar a $BRANCH"
fi
git fetch --prune origin "$BRANCH" >/dev/null 2>&1 || die "falló el fetch de origin/$BRANCH"
git fetch --tags --force >/dev/null 2>&1 || true

if [ -n "$REF" ]; then
  TARGET=$(git rev-parse --verify "$REF^{commit}" 2>/dev/null) || die "ref desconocido: $REF"
else
  TARGET=$(git rev-parse --verify "origin/$BRANCH^{commit}") || die "no existe origin/$BRANCH"
fi
git merge-base --is-ancestor "$TARGET" "origin/$BRANCH" ||
  die "$TARGET no está en la historia de origin/$BRANCH (solo se despliega lo que ya está en production)"

PREV=$(git rev-parse HEAD)

# ── gate: CI verde en GitHub para ese SHA ───────────────────────────────────
ci_gate() {
  local sha="$1" slug tmp out rc=0
  slug=$(git remote get-url origin | sed -E 's#^git@github\.com:##; s#^https://github\.com/##; s#\.git$##')
  tmp=$(mktemp)
  if ! curl -fsS --max-time 20 -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/$slug/actions/runs?head_sha=$sha" -o "$tmp" 2>>"$LOG_FILE"; then
    rm -f "$tmp"
    return 2
  fi
  out=$(python3 - "$tmp" "$sha" <<'PY'
import json, sys
runs = [r for r in json.load(open(sys.argv[1])).get("workflow_runs", [])
        if r.get("head_sha") == sys.argv[2]]
if not runs:
    sys.exit(3)
if any(r.get("status") != "completed" for r in runs):
    sys.exit(4)
bad = [r for r in runs if r.get("conclusion") not in ("success", "neutral", "skipped")]
for r in bad:
    print(f"  ✗ {r['name']}: {r['conclusion']}  {r['html_url']}")
if bad:
    sys.exit(1)
print(f"  ✓ {len(runs)} corrida(s) de CI en verde para {sys.argv[2][:7]}")
PY
) || rc=$?
  rm -f "$tmp"
  [ -n "$out" ] && printf '%s\n' "$out" | tee -a "$LOG_FILE"
  return $rc
}

if [ "$FORCE" -eq 1 ]; then
  log "gate CI saltado por --force"
else
  log "gate CI: verificando corridas de GitHub para ${TARGET:0:7}"
  if ci_gate "$TARGET"; then :; else
    case $? in
      1) die "CI rojo para ${TARGET:0:7} — no despliego" ;;
      2) die "GitHub API inaccesible — no despliego a ciegas (--force solo en emergencias)" ;;
      3) die "CI nunca corrió para ${TARGET:0:7} — espera a Actions" ;;
      4) die "CI aún corriendo para ${TARGET:0:7} — reintenta en unos minutos" ;;
      *) die "gate CI falló" ;;
    esac
  fi
fi

# ── salud actual (para saber si hay algo que recuperar) ──────────────────────
PGC=$(docker ps -qf name=postgres_secure | head -1 || true)
PG_ENV=""; PG_USER=""; PG_DB=""; PG_PASS=""
if [ -n "$PGC" ]; then
  PG_ENV=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$PGC")
  PG_USER=$(printf '%s\n' "$PG_ENV" | sed -n 's/^POSTGRES_USER=//p')
  PG_DB=$(printf '%s\n' "$PG_ENV" | sed -n 's/^POSTGRES_DB=//p')
  PG_PASS=$(printf '%s\n' "$PG_ENV" | sed -n 's/^POSTGRES_PASSWORD=//p')
fi

app_healthy() {
  docker exec "$APP_CONTAINER" python -c \
    "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/',timeout=5).status==200 else 1)" \
    >/dev/null 2>&1
}
edge_healthy() {
  curl -fsSk --max-time 10 --resolve "$EDGE_HOST:443:127.0.0.1" \
    "https://$EDGE_HOST$HEALTH_PATH" >/dev/null 2>&1
}
wait_healthy() {
  local n="${1:-$HEALTH_RETRIES}" i
  for i in $(seq 1 "$n"); do
    if app_healthy && edge_healthy; then
      log "  ✓ salud OK (intento $i/$n): app + borde nginx"
      return 0
    fi
    log "  … esperando salud ($i/$n)"
    sleep "$HEALTH_SLEEP"
  done
  return 1
}

# ── dry-run: termina aquí, sin tocar nada ───────────────────────────────────
if [ "$DRY_RUN" -eq 1 ]; then
  log "DRY RUN — no se modifica nada"
  log "  HEAD actual : $PREV"
  log "  objetivo    : $TARGET"
  if [ "$PREV" = "$TARGET" ]; then
    log "  diff        : sin cambios de código"
  else
    log "  diff        : $(git diff --shortstat "$PREV" "$TARGET" || true)"
    log "  archivos    :"
    git diff --name-status "$PREV" "$TARGET" | head -30 | sed 's/^/      /' | tee -a "$LOG_FILE"
    [ "$(git diff --name-only "$PREV" "$TARGET" | wc -l)" -gt 30 ] && log "      … y $(($(git diff --name-only "$PREV" "$TARGET" | wc -l) - 30)) más"
  fi
  log "  gate CI     : $( [ "$FORCE" -eq 1 ] && echo 'saltado (--force)' || echo 'ya verificado en verde' )"
  log "  backup      : se haría en $DUMP_DIR"
  exit 0
fi

# ── ¿ya está desplegado y sano? (atajo sin backup ni restart) ───────────────
if [ "$PREV" = "$TARGET" ] && [ "$REF_GIVEN" -eq 0 ]; then
  if wait_healthy 3; then
    printf '%s\n' "$TARGET" >"$LAST_SHA_FILE"
    log "nada que hacer: $BRANCH ya está en ${TARGET:0:7} y la API está sana"
    exit 0
  fi
  log "el SHA ya estaba pero la API NO está sana → intento de recuperación completa"
fi

# ── 1) backup de la BD (antes de tocar nada) ────────────────────────────────
TS=$(date +%Y%m%d-%H%M%S)
SHORT=$(git rev-parse --short "$TARGET")
DUMP="$DUMP_DIR/${TS}_pre_${SHORT}.dump"
DUMP_OK=0

restore_cmd() {
  log "  restaurar dump (SOLO manual, destructivo):"
  log "    docker exec -i -e PGPASSWORD='***' $PGC pg_restore -U $PG_USER -d $PG_DB --clean --if-exists < $DUMP"
}

if [ -z "$PGC" ]; then
  die "contenedor de postgres no encontrado — no hay backup, no despliego"
fi
log "1/5 backup BD → $(basename "$DUMP")"
docker exec -e PGPASSWORD="$PG_PASS" "$PGC" \
  pg_dump -U "$PG_USER" -d "$PG_DB" -Fc --no-owner --no-privileges >"$DUMP" 2>>"$LOG_FILE" ||
  die "pg_dump falló — no despliego sin backup"
SIZE=$(stat -c%s "$DUMP")
[ "$SIZE" -gt 100000 ] || die "el backup quedó sospechosamente vacío ($SIZE bytes)"
DUMP_OK=1
log "  ✓ $(du -h "$DUMP" | cut -f1)"

# ── 2) código ───────────────────────────────────────────────────────────────
log "2/5 código: ${PREV:0:7} → ${SHORT}"
if [ "$PREV" != "$TARGET" ]; then
  if ! git merge --ff-only "$TARGET" >/dev/null 2>&1; then
    if git merge-base --is-ancestor "$TARGET" "$PREV"; then
      log "  objetivo más antiguo que HEAD → reset --hard (rollback de código pedido)"
      git reset --hard "$TARGET" >/dev/null
    else
      die "no se puede avanzar a ${TARGET:0:7} desde ${PREV:0:7} (historias divergentes)"
    fi
  fi
  log "  ✓ $(git diff --name-only "$PREV" "$TARGET" | wc -l) archivo(s) cambiado(s)"
else
  log "  sin cambios de código (recuperación/redeploy)"
fi

# ── 3) migraciones ──────────────────────────────────────────────────────────
ROLLBACK_REASON=""
if [ "$NO_MIGRATE" -eq 1 ]; then
  log "3/5 migraciones: omitidas (--no-migrate)"
else
  log "3/5 migraciones"
  if docker exec "$APP_CONTAINER" python manage.py migrate --noinput >>"$LOG_FILE" 2>&1; then
    log "  ✓ migrate OK"
  else
    ROLLBACK_REASON="migrate --noinput falló (revisar $LOG_FILE)"
  fi
fi

# ── 4) restart ──────────────────────────────────────────────────────────────
log "4/5 restart contenedores"
if [ -z "$ROLLBACK_REASON" ]; then
  docker restart "$APP_CONTAINER" >/dev/null
  log "  ✓ $APP_CONTAINER reiniciado"
  CHANGED=$(git diff --name-only "$PREV" "$TARGET" 2>/dev/null || true)
  if printf '%s\n' "$CHANGED" | grep -qE '^(api/cronjobs/|manage\.py$|api/settings\.py$)'; then
    docker restart "$CRON_CONTAINER" >/dev/null
    log "  ✓ $CRON_CONTAINER reiniciado (cambió cron/config)"
  fi
else
  docker restart "$APP_CONTAINER" >/dev/null
fi

# ── 5) health check → ¿rollback? ────────────────────────────────────────────
rollback() {
  local why="$1"
  log "✗ $why"
  log "→ ROLLBACK automático al código anterior (${PREV:0:7})"
  git reset --hard "$PREV" >/dev/null 2>&1 || true
  docker restart "$APP_CONTAINER" >/dev/null
  if wait_healthy; then
    log "✓ rollback COMPLETO: API sana con el código anterior (${PREV:0:7})"
    log "  la BD NO se revirtió. Dump previo por si hay que restaurarlo:"
    log "    $DUMP"
    [ "$DUMP_OK" -eq 1 ] && restore_cmd
    exit 3
  fi
  log "✗✗ CRÍTICO: ni con el código anterior levanta la API"
  log "  1) docker logs --tail 100 $APP_CONTAINER"
  log "  2) docker restart $APP_CONTAINER"
  [ "$DUMP_OK" -eq 1 ] && { log "  3) restaurar BD:"; restore_cmd; }
  exit 2
}

if [ -n "$ROLLBACK_REASON" ]; then
  rollback "$ROLLBACK_REASON"
fi

log "5/5 health check"
if [ "$SIMULATE_FAILURE" -eq 1 ]; then
  rollback "fallo simulado (--simulate-failure): probando el mecanismo"
fi
wait_healthy || rollback "la API no pasó el health check tras desplegar (${TARGET:0:7})"

# ── éxito ───────────────────────────────────────────────────────────────────
printf '%s\n' "$TARGET" >"$LAST_SHA_FILE"
ls -1t "$DUMP_DIR"/*_pre_*.dump 2>/dev/null | tail -n +$((KEEP_DUMPS + 1)) | xargs -r rm -f
log "✓ DEPLOY OK: ${PREV:0:7} → ${TARGET:0:7}"
log "  logs: $LOG_FILE"
[ "$DUMP_OK" -eq 1 ] && log "  backup: $DUMP"
exit 0
