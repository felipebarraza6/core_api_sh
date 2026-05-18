import sys
from typing import List, Optional
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from api.core.models import InteractionDetail, CatchmentPoint
from api.core.models.catchment_points import SchemesCatchment, Variable, ProfileDataConfigCatchment


def get_pulses_factor_for_point(point_id: int) -> int:
    """Fetch pulses_factor from the Variable TOTALIZADO of the point's scheme.

    Fallback to 1000 if not found or invalid.
    """
    try:
        scheme = SchemesCatchment.objects.filter(points_catchment__id=point_id).first()
        if not scheme:
            return 1000
        var = Variable.objects.filter(
            scheme_catchment=scheme, type_variable="TOTALIZADO"
        ).first()
        if not var or not var.pulses_factor or var.pulses_factor <= 0:
            return 1000
        return int(var.pulses_factor)
    except Exception:
        return 1000


def recalc_for_point(point_id: int, dry_run: bool = True, use_created: bool = True,
                     start_datetime: Optional[datetime] = None,
                     end_datetime: Optional[datetime] = None) -> dict:
    """Recalculate totals for a given point.

    - total = (pulses * pulses_factor) / 1000 + addition
    - total_diff = max(0, total - total_prev)
      (if reset detected because total < total_prev, uses total as diff)
    - total_today_diff = total - first_total_of_day

    Args:
        point_id: CatchmentPoint id
        dry_run: If True, do not persist changes
        use_created: If True, order by created; else by date_time_medition
        start_datetime: Filter from this datetime (inclusive)
        end_datetime: Filter to this datetime (inclusive)
    Returns:
        Summary dict with counts
    """
    ordering = "created" if use_created else "date_time_medition"
    pf = get_pulses_factor_for_point(point_id)

    # Obtener addition (offset por resets acumulados) del perfil
    profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=point_id).first()
    addition = int(profile.addition or 0) if profile else 0

    # Base queryset
    qs = InteractionDetail.objects.filter(catchment_point_id=point_id)

    # Apply date filters
    date_field = ordering
    if start_datetime:
        qs = qs.filter(**{f"{date_field}__gte": start_datetime})
    if end_datetime:
        qs = qs.filter(**{f"{date_field}__lte": end_datetime})

    qs = qs.order_by(ordering, "id")

    # If we have date filters, we need to get the previous total to calculate diffs correctly
    prev_total: Optional[float] = None
    if start_datetime:
        # Get the last record before start_datetime to use as baseline
        prev_record = (
            InteractionDetail.objects.filter(catchment_point_id=point_id)
            .filter(**{f"{date_field}__lt": start_datetime})
            .exclude(total__isnull=True)
            .exclude(total="")
            .order_by(f"-{date_field}", "-id")
            .first()
        )
        if prev_record:
            try:
                prev_total = float(prev_record.total)
            except (ValueError, TypeError):
                prev_total = 0.0

    processed = 0
    updated = 0
    first_total_of_day = {}  # date -> first total value of the day

    def day_for_row(row):
        from django.utils import timezone
        if use_created:
            dt = row.created
        else:
            dt = row.date_time_medition or row.created
        # Normalize to local timezone to avoid intraday resets by TZ mismatches
        dt_local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
        return dt_local.date()

    with transaction.atomic():
        for row in qs.iterator(chunk_size=1000):
            processed += 1

            pulses = int(row.pulses or 0)
            # Compute total as int: (pulses * factor) / 1000 + addition
            total_val = int(round((float(pulses) * float(pf)) / 1000.0 + addition))

            # Compute diff against previous total (from recomputed sequence)
            if prev_total is None:
                diff_val = total_val
            else:
                if total_val < prev_total:
                    # probable reset
                    diff_val = total_val
                else:
                    diff_val = total_val - prev_total

            if diff_val < 0:
                diff_val = 0

            # Calculate today diff: total - first_total_of_day
            # Consistent with the live cron's total_day() logic
            d = day_for_row(row)
            if d not in first_total_of_day:
                first_total_of_day[d] = total_val

            today_diff_val = max(0, total_val - first_total_of_day[d])

            # Cap extreme daily values
            if today_diff_val > 10000:
                today_diff_val = 0

            # Determine if row needs update
            try:
                cur_total_int = int(float(row.total)) if row.total not in (None, "") else 0
            except (ValueError, TypeError):
                cur_total_int = 0

            needs = (
                cur_total_int != total_val
                or int(row.total_diff or 0) != int(diff_val)
                or int(row.total_today_diff or 0) != int(today_diff_val)
            )

            if needs and not dry_run:
                row.total = str(total_val)
                row.total_diff = int(diff_val)
                row.total_today_diff = int(today_diff_val)
                row.save(update_fields=["total", "total_diff", "total_today_diff"])
                updated += 1
            elif needs:
                updated += 1

            prev_total = float(total_val)

        if dry_run:
            transaction.set_rollback(True)

    return {
        "point": point_id,
        "pulses_factor": pf,
        "addition": addition,
        "processed": processed,
        "would_update": updated if dry_run else None,
        "updated": None if dry_run else updated,
        "ordered_by": ordering,
        "date_range": f"{start_datetime or 'inicio'} - {end_datetime or 'fin'}",
    }


class Command(BaseCommand):
    help = "Recalcula total, total_diff y total_today_diff para InteractionDetail por punto(s) en rango de fechas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--points",
            type=str,
            required=True,
            help="Lista de IDs de puntos separada por comas, e.g., 12,34,56",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="No persiste cambios, solo reporta",
        )
        parser.add_argument(
            "--use-medicion",
            action="store_true",
            help="Ordena por date_time_medition en vez de created",
        )
        parser.add_argument(
            "--from-datetime",
            type=str,
            help="Fecha/hora inicio en formato ISO: 2024-08-20T10:00:00 o 2024-08-20",
        )
        parser.add_argument(
            "--to-datetime",
            type=str,
            help="Fecha/hora fin en formato ISO: 2024-08-25T18:00:00 o 2024-08-25",
        )

    def handle(self, *args, **options):
        points_arg = options["points"].strip()
        dry_run = options["dry_run"]
        use_medicion = options["use_medicion"]
        from_dt_str = options.get("from_datetime")
        to_dt_str = options.get("to_datetime")

        try:
            points: List[int] = [int(x) for x in points_arg.split(",") if x.strip()]
        except ValueError:
            raise CommandError("--points debe contener IDs numéricos separados por comas")

        # Parse datetime filters
        start_datetime = None
        end_datetime = None

        if from_dt_str:
            # Try with time first, then date only
            start_datetime = parse_datetime(from_dt_str)
            if not start_datetime:
                try:
                    start_datetime = timezone.make_aware(
                        datetime.strptime(from_dt_str, "%Y-%m-%d")
                    )
                except ValueError:
                    raise CommandError(f"Formato de fecha inválido en --from-datetime: {from_dt_str}")

        if to_dt_str:
            end_datetime = parse_datetime(to_dt_str)
            if not end_datetime:
                try:
                    # If only date provided, set to end of day
                    end_datetime = timezone.make_aware(
                        datetime.strptime(to_dt_str + " 23:59:59", "%Y-%m-%d %H:%M:%S")
                    )
                except ValueError:
                    raise CommandError(f"Formato de fecha inválido en --to-datetime: {to_dt_str}")

        summaries = []
        for pid in points:
            # Validar existencia del punto
            if not CatchmentPoint.objects.filter(id=pid).exists():
                self.stderr.write(self.style.WARNING(f"Punto {pid} no existe, se omite"))
                continue

            self.stdout.write(f"Recalculando punto {pid}...")
            if start_datetime or end_datetime:
                self.stdout.write(f"  Rango: {start_datetime or 'inicio'} - {end_datetime or 'fin'}")

            summary = recalc_for_point(
                pid,
                dry_run=dry_run,
                use_created=not use_medicion,
                start_datetime=start_datetime,
                end_datetime=end_datetime
            )
            summaries.append(summary)

        # Mostrar resumen
        for s in summaries:
            if dry_run:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[DRY-RUN] Punto {s['point']}: registros={s['processed']}, cambios={s['would_update']}, "
                        f"factor={s['pulses_factor']}, orden={s['ordered_by']}, rango={s['date_range']}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Punto {s['point']}: registros={s['processed']}, actualizados={s['updated']}, "
                        f"factor={s['pulses_factor']}, orden={s['ordered_by']}, rango={s['date_range']}"
                    )
                )
