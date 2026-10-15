"""
Corrección retroactiva de conexión (auditoría 30-09-2026).

Fases (en este orden, por punto y ordenado por fecha de medición):
  B) Hora Nettra: TheThings.io entregaba UTC y se guardaba como hora de Chile.
     La fecha del logger se reinterpreta como UTC. Solo registros ANTERIORES al
     despliegue del fix (--until obligatorio para esta fase).
  A) Conexión falsa: registros donde la fecha del logger es exactamente la hora
     de medición y el totalizado no llegó (firma del fallback antiguo). Se
     arrastra la última fecha real, pulsos y total del registro válido anterior,
     total_diff=0 e is_error=True. Luego se recalcula total_diff del primer
     registro real posterior y total_today_diff de los días afectados.
  C) Días sin conexión: se recalculan con la fecha del logger guardada, SOLO si
     el resultado es menor al guardado (el logger demuestra contacto reciente).
     Nunca se aumentan días con esta fase.

Seguridad:
  - Por defecto es simulación (no escribe). Usar --apply para guardar.
  - Nunca modifica registros con n_voucher (ya enviados a la DGA): los lista.
  - Exporta un CSV con valores antes/después de cada cambio (--csv).

Uso:
  python manage.py fix_connection_history --since 2026-06-01 --until "2026-10-01T10:00" \\
      --csv /tmp/fix_conn.csv [--points 209,211,47] [--phases A,B,C] [--apply]
"""
import csv
from collections import defaultdict
from datetime import datetime

import pytz
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime

from api.core.models import CatchmentPoint, InteractionDetail

CL = pytz.timezone("America/Santiago")


def _aware(value, label):
    if not value:
        return None
    dt = parse_datetime(value) or (datetime.fromisoformat(value) if "T" not in value else None)
    if dt is None:
        try:
            dt = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise CommandError(f"Fecha inválida en {label}: {value}")
    if dt.tzinfo is None:
        dt = CL.localize(dt)
    return dt


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _totalizado_ok(rec):
    for d in rec.variable_details or []:
        if (d.get("type_variable") or "").upper() == "TOTALIZADO":
            return bool(d.get("success"))
    return None  # sin detalle: no se puede afirmar


def _is_fake(rec):
    if not rec.date_time_last_logger or not rec.date_time_medition:
        return False
    if rec.date_time_last_logger != rec.date_time_medition:
        return False
    ok = _totalizado_ok(rec)
    return ok is False or (ok is None and not rec.pulses)


def _nettra_point_ids():
    ids = set(CatchmentPoint.objects.filter(is_thethings=True).values_list("id", flat=True))
    ids |= set(
        CatchmentPoint.objects.filter(telemetry_provider__handler_name="thethings").values_list("id", flat=True)
    )
    return ids


class Command(BaseCommand):
    help = "Corrige históricamente fecha del logger, conexión falsa y días sin conexión."

    def add_arguments(self, parser):
        parser.add_argument("--since", required=True, help="Desde (fecha de medición, hora Chile)")
        parser.add_argument("--until", help="Hasta: momento del despliegue del fix (obligatorio para fase B)")
        parser.add_argument("--points", help="IDs separados por coma (default: todos)")
        parser.add_argument("--phases", default="B,A,C", help="Fases a ejecutar: A,B,C")
        parser.add_argument("--csv", help="Ruta del CSV de cambios")
        parser.add_argument("--apply", action="store_true", help="Guardar cambios (default: simulación)")

    def handle(self, *args, **opts):
        since = _aware(opts["since"], "--since")
        until = _aware(opts.get("until"), "--until")
        phases = {p.strip().upper() for p in opts["phases"].split(",") if p.strip()}
        if "B" in phases and not until:
            raise CommandError("La fase B requiere --until (momento del despliegue del fix).")
        apply = opts["apply"]

        qs = InteractionDetail.objects.filter(date_time_medition__gte=since)
        if until:
            qs = qs.filter(date_time_medition__lt=until)
        if opts.get("points"):
            qs = qs.filter(catchment_point_id__in=[int(x) for x in opts["points"].split(",")])
        point_ids = sorted(set(qs.values_list("catchment_point_id", flat=True)))
        nettra = _nettra_point_ids()

        changes = []  # (point, record_id, medicion, fase, campo, antes, despues)
        skipped_dga = []
        stats = defaultdict(int)

        for pid in point_ids:
            recs = list(qs.filter(catchment_point_id=pid).order_by("date_time_medition", "id"))
            dirty = {}

            def setf(rec, phase, field, new):
                old = getattr(rec, field)
                if old == new:
                    return
                if rec.n_voucher:
                    skipped_dga.append((pid, rec.id, rec.date_time_medition, phase, field, old, new))
                    return
                setattr(rec, field, new)
                dirty[rec.id] = rec
                changes.append((pid, rec.id, rec.date_time_medition, phase, field, old, new))
                stats[f"{phase}:{field}"] += 1

            # --- Fase B: hora Nettra (UTC guardado como hora de Chile)
            if "B" in phases and pid in nettra:
                for rec in recs:
                    if not rec.date_time_last_logger or _is_fake(rec):
                        continue
                    wall = rec.date_time_last_logger.astimezone(CL).replace(tzinfo=None)
                    setf(rec, "B", "date_time_last_logger", pytz.utc.localize(wall))

            # --- Fase A: conexión falsa
            if "A" in phases:
                prev_valid = (
                    InteractionDetail.objects.filter(catchment_point_id=pid, date_time_medition__lt=since)
                    .exclude(date_time_last_logger__isnull=True)
                    .order_by("-date_time_medition")
                    .first()
                )
                if prev_valid is not None and _is_fake(prev_valid):
                    prev_valid = None
                affected_days = set()
                after_window = False
                for rec in recs:
                    if _is_fake(rec):
                        stats["A:registros_falsos"] += 1
                        affected_days.add(rec.date_time_medition.astimezone(CL).date())
                        if prev_valid is not None:
                            setf(rec, "A", "date_time_last_logger", prev_valid.date_time_last_logger)
                            setf(rec, "A", "pulses", prev_valid.pulses)
                            setf(rec, "A", "total", prev_valid.total)
                            dias = max(0, (rec.date_time_medition - prev_valid.date_time_last_logger).days)
                            setf(rec, "A", "days_not_conection", dias)
                        else:
                            setf(rec, "A", "date_time_last_logger", None)
                        setf(rec, "A", "total_diff", 0)
                        setf(rec, "A", "is_error", True)
                        after_window = True
                        continue
                    if after_window and prev_valid is not None:
                        t_now, t_prev = _num(rec.total), _num(prev_valid.total)
                        if t_now is not None and t_prev is not None:
                            setf(rec, "A", "total_diff", int(max(0, round(t_now - t_prev))))
                        affected_days.add(rec.date_time_medition.astimezone(CL).date())
                    after_window = False
                    if rec.date_time_last_logger and not rec.is_error:
                        prev_valid = rec
                # total_today_diff de los días afectados
                for day in affected_days:
                    day_recs = [r for r in recs if r.date_time_medition.astimezone(CL).date() == day]
                    base = next((_num(r.total) for r in day_recs if not r.is_error and _num(r.total) is not None), None)
                    if base is None:
                        continue
                    for r in day_recs:
                        t = _num(r.total)
                        if t is not None:
                            setf(r, "A", "total_today_diff", int(max(0, round(t - base))))

            # --- Fase C: días sin conexión (solo reducir)
            if "C" in phases:
                for rec in recs:
                    if not rec.date_time_last_logger or rec.days_not_conection is None:
                        continue
                    dias = max(0, (rec.date_time_medition - rec.date_time_last_logger).days)
                    if dias < rec.days_not_conection:
                        setf(rec, "C", "days_not_conection", dias)

            if apply and dirty:
                fields = ["date_time_last_logger", "pulses", "total", "total_diff",
                          "total_today_diff", "days_not_conection", "is_error"]
                with transaction.atomic():
                    InteractionDetail.objects.bulk_update(list(dirty.values()), fields, batch_size=500)
            stats["puntos_revisados"] += 1

        if opts.get("csv"):
            with open(opts["csv"], "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["punto", "registro", "medicion", "fase", "campo", "antes", "despues", "estado"])
                for row in changes:
                    w.writerow(list(row) + ["aplicado" if apply else "simulado"])
                for row in skipped_dga:
                    w.writerow(list(row) + ["omitido_enviado_dga"])

        modo = "APLICADO" if apply else "SIMULACIÓN (sin cambios)"
        self.stdout.write(f"Modo: {modo}")
        for k in sorted(stats):
            self.stdout.write(f"  {k}: {stats[k]}")
        self.stdout.write(f"  cambios: {len(changes)} | omitidos por envío DGA: {len(skipped_dga)}")
