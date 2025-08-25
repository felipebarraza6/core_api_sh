#!/usr/bin/env bash
set -euo pipefail
LOGDIR="/var/log/smarthydro"
KEEP=7
cd "$LOGDIR" || exit 0
for f in *.log; do [ -f "$f" ] || continue; ts=$(date +%Y%m%d); gzip -c "$f" > "$f.$ts.gz" || true; : > "$f"; done
ls *.log.*.gz 2>/dev/null | sed "s/\.log\..*\.gz$//" | sort -u | while read base; do ls "${base}.log".*.gz 2>/dev/null | sort -r | tail -n +$((KEEP+1)) | xargs -r rm -f; done
