# DEPLOY — despliegues con CD seguro (backup + rollback)

Servidor: `telemetry-smarthydro` · repo `/root/core_api_sh` · rama desplegada: **production**

## Flujo

```
dev  →  PR a main (CI verde)  →  PR a production (CI verde)
                                   │
                                   ▼  en ≤5 min, solo si CI está en verde:
                        smarthydro-cd.timer (systemd, cada 5 min)
                                   │
                                   ▼
                        scripts/deploy.sh
```

**Nada se despliega si el CI de ese SHA no está en verde.**

## Qué hace `scripts/deploy.sh`

1. **Preflight** — rama `production`, árbol limpio, `fetch`, lock (nunca dos a la vez).
2. **Gate CI** — consulta GitHub Actions del SHA objetivo; si está rojo, incompleto o
   nunca corrió → **aborta** (sin `--force` no hay forma de saltárselo).
3. **Backup BD** — `pg_dump -Fc` antes de tocar nada → `backups/deploy/<ts>_pre_<sha>.dump`
   (176 MB ≈ 1 min; se conservan los últimos 10). Si el dump sale vacío → aborta.
4. **Código** — `git merge --ff-only origin/production`.
5. **Migrate** — `manage.py migrate --noinput`.
6. **Restart** — `django_api_secure` (y `cron_jobs_secure` si cambiaron cron/config).
7. **Health check** — app (`:8000/health/`) + borde nginx (443 con SNI local), hasta 60 s.
8. **Si algo falla** → **ROLLBACK automático**: `git reset --hard` al commit anterior,
   restart, health de nuevo. La BD **no** se revierte; el dump queda listo por si hay que
   restaurarlo a mano.

Códigos de salida: `0` ok · `1` abortado · `2` crítico (API caída) · `3` rollback OK.

## Comandos

```bash
scripts/deploy.sh --dry-run          # analiza, no toca nada
scripts/deploy.sh                    # despliegue normal (lo hace el timer)
scripts/deploy.sh --ref <tag|sha>    # despliega un commit concreto
scripts/deploy.sh --simulate-failure # prueba el rollback sin riesgo
scripts/deploy.sh --force            # salta el gate CI (solo emergencias)

scripts/install_cd.sh [install|status|uninstall]   # timer cada 5 min
```

### Interruptores de emergencia

```bash
touch backups/deploy/.cd_disabled    # el CD se apaga (ni manual lo activa vía timer)
touch backups/deploy/.cd_dry_run     # el timer solo analiza, no despliega
rm backups/deploy/.cd_disabled       # vuelve a la normalidad
```

## Rollback de código a mano

```bash
# último deploy bueno conocido:
cat backups/deploy/.last_deployed_sha

git log --oneline -5 production
scripts/deploy.sh --ref <sha-anterior>   # gate CI + backup + health incluidos
```

## Restaurar la BD (destructivo, solo manual)

```bash
docker exec -i -e PGPASSWORD='…' <contenedor_postgres> \
  pg_restore -U smarthydro_user -d smarthydro_prod --clean --if-exists \
  < backups/deploy/<ts>_pre_<sha>.dump
```

> Una migración fallida **no** se revierte sola: el script vuelve al código anterior y
> deja el dump indicado en el log. Restaurar la BD es decisión humana.

## Logs y archivos

| Qué | Dónde |
|---|---|
| Log de cada deploy | `backups/deploy/logs/deploy-<ts>.log` |
| Log del watcher | `backups/deploy/logs/cd-watch.log` |
| Último SHA desplegado | `backups/deploy/.last_deployed_sha` |
| Dumps previos | `backups/deploy/*_pre_*.dump` (últimos 10) |
| Journal systemd | `journalctl -u smarthydro-cd.service -n 50` |

`backups/` está en `.gitignore`: los dumps nunca suben a GitHub.
