#!/usr/bin/env bash
#
# install_cd.sh — instala/desinstala el timer de CD (smarthydro-cd.timer)
#
#   sudo scripts/install_cd.sh            instala y activa (cada 5 min)
#   sudo scripts/install_cd.sh status     estado del timer
#   sudo scripts/install_cd.sh uninstall  desinstala
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SVC="smarthydro-cd"
ACTION="${1:-install}"

[ "$(id -u)" -eq 0 ] || { echo "hay que correr como root"; exit 1; }

case "$ACTION" in
  install)
    for f in service timer; do
      sed "s#@REPO@#$REPO#g" "$REPO/deploy/systemd/$SVC.$f" >"/etc/systemd/system/$SVC.$f"
    done
    systemctl daemon-reload
    systemctl enable --now "$SVC.timer"
    echo "✓ timer instalado y activo"
    systemctl list-timers "$SVC.timer" --no-pager
    ;;
  status)
    systemctl status "$SVC.timer" --no-pager || true
    systemctl list-timers "$SVC.timer" --no-pager || true
    echo "── últimas corridas ──"
    journalctl -u "$SVC.service" -n 20 --no-pager || true
    ;;
  uninstall|stop)
    systemctl disable --now "$SVC.timer" 2>/dev/null || true
    rm -f "/etc/systemd/system/$SVC.service" "/etc/systemd/system/$SVC.timer"
    systemctl daemon-reload
    echo "✓ timer desinstalado (el CD manual sigue disponible: scripts/deploy.sh)"
    ;;
  *)
    echo "uso: $0 [install|status|uninstall]"; exit 1
    ;;
esac
