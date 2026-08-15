"""
Reporte Semanal por Cliente - Telemetría y Cumplimiento DGA
============================================================
Resumen semanal del estado de telemetría y cumplimiento DGA de los puntos
pertenecientes a un usuario owner. EXCLUSIVO para clientes con cumplimiento
DGA (puntos con send_dga activo).

Contenido:
1. Resumen global del cliente (puntos, mediciones, cobertura, envíos DGA, lagunas)
2. Resumen por PROYECTO
3. Tabla por punto:
   - Mediciones esperadas vs reales + % cobertura
   - Envíos DGA (con voucher / en cola / con error)
   - Total acumulado y caudal máximo vs caudal autorizado (exceso)
   - Última medición recibida
4. Detalle de lagunas (buckets faltantes) si existen
5. Alertas de exceso de caudal

Adjuntos:
- PDF con el reporte visual (reportlab)
- Excel con SOLO las mediciones enviadas a DGA: Fecha medición + N° voucher
  (una hoja por proyecto)

Uso (envío manual de validación):
    docker exec cron_jobs_secure python -c "
    from api.cronjobs.reports.weekly_client_report import run
    run(user_id=35, to='felipebarraza@smarthydro.cl', preview=True)"

Envío automático (CRONJOBS, Viernes 16:00 Chile / 20:00 UTC):
    run_weekly() envía el reporte a todos los usuarios con
    User.recibir_reporte activo, usando su email como destinatario y
    User.reporte_cc_emails como copia (CC). El reporte incluye todos los
    puntos del owner.

Genera HTML con CSS inline (compatible Gmail/Outlook).
"""

import io
import logging
import re
from datetime import timedelta
from collections import defaultdict
from django.utils import timezone
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Count, Max, Min, Q

from api.core.models import (
    CatchmentPoint,
    InteractionDetail,
    DgaDataConfigCatchment,
    User,
)

logger = logging.getLogger(__name__)

# Zona horaria Chile
import pytz

CHILE_TZ = pytz.timezone("America/Santiago")

DIAS_ES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
MESES_ES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

# Orden de estándares para ordenamiento
STANDARD_ORDER = {
    'MAYOR': 1, 'MEDIO': 2, 'MENOR': 3,
    'CAUDALES_MUY_PEQUENOS': 4, 'SIN_ESTANDAR': 5, 'FORMULARIO': 6,
}


def to_chile_tz(dt):
    """Convertir datetime a hora Chile."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(CHILE_TZ)


def format_dt_chile(dt, fmt='%d/%m/%y %H:%M'):
    """Formatear datetime a string en hora Chile."""
    if dt is None:
        return 'N/A'
    return to_chile_tz(dt).strftime(fmt)


def format_number(num):
    """Formatear número con punto como separador de miles."""
    if num is None:
        return "0"
    try:
        val = float(num)
        return f"{int(val):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "0"


def format_float(num, decimals=2):
    """Formatear float con comas en decimales."""
    if num is None:
        return "-"
    try:
        return f"{float(num):.{decimals}f}".replace(".", ",")
    except (ValueError, TypeError):
        return "-"


def get_week_window():
    """Última semana completa Lunes 00:00 CLT → Domingo 23:59 CLT."""
    now = timezone.now().astimezone(CHILE_TZ)
    days_since_monday = now.weekday()
    # Si hoy es lunes, la semana cerrada fue la pasada
    offset = days_since_monday + 7
    end = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=offset % 7)
    start = end - timedelta(days=6)
    end_day = end + timedelta(days=1) - timedelta(seconds=1)
    return start, end_day


def expected_slots_per_day(standard, frequency):
    """Nº de slots esperados por día según estándar DGA y frecuencia."""
    freq = int(frequency or 60)
    if standard == 'MAYOR' or standard == 'SIN_ESTANDAR':
        return 24 * 60 // freq
    elif standard == 'MEDIO':
        return 1
    elif standard == 'MENOR':
        return 1 / 30.0  # 1 al mes (se maneja como fracción)
    elif standard == 'CAUDALES_MUY_PEQUENOS':
        return 1 / 30.0
    return 24 * 60 // freq


def is_slot_expected(standard, dt):
    """True si el slot debe tener medición según el estándar."""
    if standard == 'MAYOR' or standard == 'SIN_ESTANDAR':
        return dt.minute == 0
    elif standard == 'MEDIO':
        return dt.hour == 0 and dt.minute == 0
    elif standard == 'MENOR':
        return dt.day == 1 and dt.hour == 0 and dt.minute == 0
    elif standard == 'CAUDALES_MUY_PEQUENOS':
        return dt.month in [1, 7] and dt.day == 1 and dt.hour == 0 and dt.minute == 0
    return dt.minute == 0


def get_provider_name(point):
    if point.is_tdata:
        return 'TWIN'
    if point.is_novus:
        return 'NOVUS'
    if point.is_thethings:
        return 'NETTRA'
    return 'N/A'


def parse_email_list(raw):
    """Dividir string de emails (separados por coma o punto y coma) y limpiar duplicados."""
    if not raw:
        return []
    emails = []
    for part in re.split(r'[;,]', raw):
        e = part.strip()
        if e and e not in emails:
            emails.append(e)
    return emails


def get_report_recipients():
    """Usuarios (owners) habilitados para recibir el reporte semanal (recibir_reporte activo).

    El reporte se envía con todos los puntos del owner; reporte_cc_emails se
    agrega como CC del correo.
    """
    users = User.objects.filter(recibir_reporte=True).order_by('id')
    return [
        {'user_id': u.id, 'owner_email': u.email or '', 'cc': parse_email_list(u.reporte_cc_emails)}
        for u in users
    ]


def get_client_points(user_id):
    """Puntos donde el usuario es owner, con proyecto/cliente/config DGA/frecuencia."""
    points = CatchmentPoint.objects.filter(
        owner_user_id=user_id
    ).select_related('project', 'project__client').order_by('id')

    result = []
    for p in points:
        dga = DgaDataConfigCatchment.objects.filter(point_catchment_id=p.id).first()
        profile = p.data_config_profiles.filter(is_telemetry=True).first()
        result.append({
            'id': p.id,
            'title': p.title or 'Sin nombre',
            'project': p.project.name if p.project else 'Sin proyecto',
            'client': p.project.client.name if (p.project and p.project.client) else 'N/A',
            'standard': dga.standard if dga else 'SIN_ESTANDAR',
            'code_dga': dga.code_dga or '' if dga else '',
            'send_dga': dga.send_dga if dga else False,
            'flow_granted': float(dga.flow_granted_dga) if dga and dga.flow_granted_dga else None,
            'total_granted': dga.total_granted_dga if dga else None,
            'frequency': p.frecuency or '60',
            'provider': get_provider_name(p),
        })
    return result


def compute_point_stats(pt, start, end):
    """Métricas de la semana para un punto."""
    pid = pt['id']

    records = list(InteractionDetail.objects.filter(
        catchment_point_id=pid,
        date_time_medition__gte=start,
        date_time_medition__lte=end,
    ).order_by('date_time_medition'))

    # Buckets esperados (slots que deben existir según estándar)
    expected_slots = []
    cur = start.replace(minute=0, second=0, microsecond=0) - timedelta(minutes=start.minute % 60)
    while cur <= end:
        if is_slot_expected(pt['standard'], cur):
            expected_slots.append(cur)
        cur += timedelta(minutes=int(pt['frequency'] or 60))

    actual_dts = {r.date_time_medition.astimezone(CHILE_TZ).replace(minute=0, second=0, microsecond=0)
                  for r in records}

    # Lagunas: slots esperados sin registro
    missing = [s for s in expected_slots if s not in actual_dts]

    total_records = len(records)
    expected_count = len(expected_slots)
    coverage = round(total_records / expected_count * 100, 1) if expected_count else 0

    vouchers = sum(1 for r in records if r.n_voucher)
    in_queue = sum(1 for r in records if r.send_dga)
    errors = sum(1 for r in records if r.is_error)

    # Última medición y última con voucher
    last_record = records[-1] if records else None
    last_voucher = None
    for r in reversed(records):
        if r.n_voucher:
            last_voucher = r
            break

    # Totales y caudal
    total_final = None
    total_max = None
    flow_max = None
    if records:
        totals = []
        flows = []
        for r in records:
            try:
                if r.total:
                    totals.append(float(r.total))
            except (ValueError, TypeError):
                pass
            try:
                if r.flow is not None:
                    flows.append(float(r.flow))
            except (ValueError, TypeError):
                pass
        total_final = totals[-1] if totals else None
        total_max = max(totals) if totals else None
        flow_max = max(flows) if flows else None

    # Exceso de caudal
    exceeds_flow = False
    if flow_max is not None and pt['flow_granted'] is not None:
        exceeds_flow = flow_max > pt['flow_granted']

    # Mediciones enviadas a DGA (con voucher)
    dga_sent = [{'date': r.date_time_medition, 'voucher': r.n_voucher}
                for r in records if r.n_voucher]

    return {
        'total_records': total_records,
        'expected_count': expected_count,
        'coverage': coverage,
        'vouchers': vouchers,
        'in_queue': in_queue,
        'errors': errors,
        'missing_count': len(missing),
        'missing': missing,
        'dga_sent': dga_sent,
        'last_date': last_record.date_time_medition if last_record else None,
        'last_voucher_date': last_voucher.date_time_medition if last_voucher else None,
        'total_final': total_final,
        'total_max': total_max,
        'flow_max': flow_max,
        'flow_granted': pt['flow_granted'],
        'exceeds_flow': exceeds_flow,
        'health': 'ok' if coverage >= 100 and not errors and not missing else (
            'warn' if coverage >= 95 else 'bad'),
    }


def build_report(user_id):
    """Construir estructura de datos del reporte."""
    start, end = get_week_window()
    user = User.objects.filter(id=user_id).first()
    if not user:
        raise ValueError(f"Usuario {user_id} no existe")

    points = get_client_points(user_id)
    for pt in points:
        pt['stats'] = compute_point_stats(pt, start, end)

    # Agrupar por proyecto
    projects = defaultdict(list)
    for pt in points:
        projects[pt['project']].append(pt)

    total_mediciones = sum(pt['stats']['total_records'] for pt in points)
    total_esperadas = sum(pt['stats']['expected_count'] for pt in points)
    total_vouchers = sum(pt['stats']['vouchers'] for pt in points)
    total_cola = sum(pt['stats']['in_queue'] for pt in points)
    total_errores = sum(pt['stats']['errors'] for pt in points)
    total_lagunas = sum(pt['stats']['missing_count'] for pt in points)
    total_excesos = sum(1 for pt in points if pt['stats']['exceeds_flow'])

    global_coverage = round(total_mediciones / total_esperadas * 100, 1) if total_esperadas else 0

    return {
        'user': user,
        'start': start,
        'end': end,
        'points': points,
        'projects': dict(projects),
        'total_points': len(points),
        'total_mediciones': total_mediciones,
        'total_esperadas': total_esperadas,
        'global_coverage': global_coverage,
        'total_vouchers': total_vouchers,
        'total_cola': total_cola,
        'total_errores': total_errores,
        'total_lagunas': total_lagunas,
        'total_excesos': total_excesos,
        'has_dga_compliance': any(pt['send_dga'] for pt in points),
        'health': 'ok' if (global_coverage >= 100 and not total_errores and not total_lagunas) else (
            'warn' if global_coverage >= 95 else 'bad'),
    }


# ============================================================
# GENERACIÓN HTML (CSS inline, compatible Gmail/Outlook)
# ============================================================

def badge(health):
    """Indicador de estado minimal (punto de color + texto, sin pill)."""
    styles = {
        'ok': ('#16a34a', 'OK'),
        'warn': ('#d97706', 'ATENCIÓN'),
        'bad': ('#dc2626', 'CRÍTICO'),
    }
    color, label = styles.get(health, styles['warn'])
    return (
        f'<span style="font-size:12px;font-weight:700;color:{color};white-space:nowrap;">'
        f'<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:{color};'
        f'box-shadow:0 0 0 3px {color}22;vertical-align:1px;margin-right:6px;"></span>{label}</span>'
    )


def coverage_bar(pct):
    pct = max(0, min(100, pct))
    color = '#16a34a' if pct >= 100 else ('#d97706' if pct >= 95 else '#dc2626')
    return (
        f'<div style="text-align:center;">'
        f'<div style="width:86px;height:6px;background:#eef1f7;border-radius:9999px;overflow:hidden;display:inline-block;vertical-align:middle;">'
        f'<div style="width:{pct}%;height:6px;background:{color};border-radius:9999px;"></div></div>'
        f'<div style="font-size:11px;color:#94a3b8;margin-top:4px;font-variant-numeric:tabular-nums;">{pct:.1f}%</div></div>'
    )


def generate_html(data):
    """Generar HTML del reporte semanal (múltiples cards, responsive móvil)."""
    user = data['user']
    start, end = data['start'], data['end']
    fecha_inicio = format_dt_chile(start, '%d/%m/%Y')
    fecha_fin = format_dt_chile(end, '%d/%m/%Y')

    health_color = '#16a34a' if data['health'] == 'ok' else ('#d97706' if data['health'] == 'warn' else '#dc2626')
    health_text = 'OPTIMO' if data['health'] == 'ok' else ('ATENCIÓN' if data['health'] == 'warn' else 'CRÍTICO')

    nombre = f"{user.first_name} {user.last_name}".strip() or user.email
    cliente = data['points'][0]['client'] if data['points'] else 'N/A'

    col_cola = '#d97706' if data['total_cola'] else '#334155'
    col_err = '#dc2626' if data['total_errores'] else '#334155'
    col_lag = '#d97706' if data['total_lagunas'] else '#334155'
    col_exc = '#dc2626' if data['total_excesos'] else '#334155'

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  @media only screen and (max-width:600px){{
    body {{ padding:6px !important; }}
    .card {{ border-radius:16px !important; }}
    .pad-hdr {{ padding:26px 20px 20px !important; }}
    .pad-main {{ padding:22px 18px 0 !important; }}
    .pad-sec {{ padding:10px 10px 18px !important; }}
    .kpi-wrap {{ width:48% !important; padding:4px !important; }}
    .hide-mobile {{ display:none !important; }}
    .cell, .th {{ padding:10px 6px !important; }}
    .hdr-title {{ font-size:22px !important; }}
    .hdr-period {{ font-size:13px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:#eef1f7;font-family:Inter,'Segoe UI',-apple-system,BlinkMacSystemFont,Roboto,Arial,sans-serif;">

<!-- CARD: HEADER -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:12px 12px 4px;">
<table role="presentation" width="100%" class="card" style="max-width:900px;background:linear-gradient(160deg,#24407a 0%,#16294f 55%,#102040 100%);border-radius:22px;overflow:hidden;box-shadow:0 14px 40px rgba(15,34,71,0.18);">
<tr><td class="pad-hdr" style="padding:40px 42px 32px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td valign="top" style="padding-right:24px;">
        <div style="font-size:11px;color:#8fb0e0;letter-spacing:2px;font-weight:600;">SMARTHYDRO TELEMETRÍA</div>
        <div class="hdr-title" style="font-size:28px;color:#ffffff;font-weight:800;margin-top:16px;line-height:1.25;letter-spacing:-0.3px;">Reporte Semanal de Puntos</div>
        <div style="font-size:14px;color:#b9cdf0;margin-top:10px;">{cliente} · {nombre}</div>
      </td>
      <td valign="top" align="right" style="white-space:nowrap;">
        <table role="presentation" cellpadding="0" cellspacing="0" align="right">
          <tr><td style="background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.16);box-shadow:inset 0 1px 0 rgba(255,255,255,0.12);border-radius:14px;padding:12px 18px;text-align:right;">
            <div style="font-size:10px;color:#8fb0e0;letter-spacing:1px;font-weight:600;text-transform:uppercase;">Período</div>
            <div class="hdr-period" style="font-size:15px;color:#ffffff;font-weight:700;margin-top:4px;font-variant-numeric:tabular-nums;">{fecha_inicio} – {fecha_fin}</div>
            <div style="font-size:10px;color:#b9cdf0;margin-top:2px;">Semana Lunes a Domingo</div>
          </td></tr>
        </table>
      </td>
    </tr>
  </table>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:28px;">
    <tr>
      <td style="background:rgba(255,255,255,0.10);border:1px solid rgba(255,255,255,0.18);box-shadow:inset 0 1px 0 rgba(255,255,255,0.15);border-radius:14px;padding:16px 22px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="font-size:13px;color:#dbe7fb;">Estado general de la semana</td>
            <td align="right" style="color:{health_color};font-weight:800;font-size:20px;letter-spacing:-0.2px;">{health_text}</td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</td></tr>
</table>
</td></tr></table>

<!-- CARD: KPIs + SUB-STATS -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:12px 12px 4px;">
<table role="presentation" width="100%" class="card" style="max-width:900px;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 8px 26px rgba(15,34,71,0.07);">
<tr><td class="pad-main" style="padding:28px 26px 0;">
  <div class="kpi-wrap" style="width:23%;display:inline-block;vertical-align:top;padding:0 5px;">
    <div style="background:linear-gradient(180deg,#ffffff 0%,#f7f9fd 100%);border-radius:16px;padding:18px 8px;text-align:center;box-shadow:0 6px 18px rgba(15,34,71,0.06);">
      <div style="font-size:26px;font-weight:800;color:#16294F;letter-spacing:-0.5px;font-variant-numeric:tabular-nums;">{data['total_points']}</div>
      <div style="font-size:10px;color:#94a3b8;margin-top:5px;letter-spacing:0.8px;text-transform:uppercase;">Puntos</div>
    </div>
  </div>
  <div class="kpi-wrap" style="width:23%;display:inline-block;vertical-align:top;padding:0 5px;">
    <div style="background:linear-gradient(180deg,#ffffff 0%,#f7f9fd 100%);border-radius:16px;padding:18px 8px;text-align:center;box-shadow:0 6px 18px rgba(15,34,71,0.06);">
      <div style="font-size:26px;font-weight:800;color:#16294F;letter-spacing:-0.5px;font-variant-numeric:tabular-nums;">{format_number(data['total_mediciones'])}</div>
      <div style="font-size:10px;color:#94a3b8;margin-top:5px;letter-spacing:0.8px;text-transform:uppercase;">Mediciones</div>
    </div>
  </div>
  <div class="kpi-wrap" style="width:23%;display:inline-block;vertical-align:top;padding:0 5px;">
    <div style="background:linear-gradient(180deg,#ffffff 0%,#f7f9fd 100%);border-radius:16px;padding:18px 8px;text-align:center;box-shadow:0 6px 18px rgba(15,34,71,0.06);">
      <div style="font-size:26px;font-weight:800;color:#16294F;letter-spacing:-0.5px;font-variant-numeric:tabular-nums;">{format_number(data['total_vouchers'])}</div>
      <div style="font-size:10px;color:#94a3b8;margin-top:5px;letter-spacing:0.8px;text-transform:uppercase;">Envíos DGA</div>
    </div>
  </div>
  <div class="kpi-wrap" style="width:23%;display:inline-block;vertical-align:top;padding:0 5px;">
    <div style="background:linear-gradient(180deg,#ffffff 0%,#f7f9fd 100%);border-radius:16px;padding:18px 8px;text-align:center;box-shadow:0 6px 18px rgba(15,34,71,0.06);">
      <div style="font-size:26px;font-weight:800;color:#16294F;letter-spacing:-0.5px;font-variant-numeric:tabular-nums;">{data['global_coverage']:.1f}%</div>
      <div style="font-size:10px;color:#94a3b8;margin-top:5px;letter-spacing:0.8px;text-transform:uppercase;">Cobertura</div>
    </div>
  </div>
</td></tr>
<tr><td class="pad-sec" style="padding:6px 26px 28px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td style="background:#f8fafc;border-radius:14px;padding:14px 6px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr>
  <td width="20%" style="padding:6px;text-align:center;"><div style="font-size:16px;font-weight:700;color:#334155;font-variant-numeric:tabular-nums;">{format_number(data['total_esperadas'])}</div><div style="font-size:9px;color:#94a3b8;letter-spacing:0.8px;text-transform:uppercase;margin-top:3px;">Esperadas</div></td>
  <td width="20%" style="padding:6px;text-align:center;"><div style="font-size:16px;font-weight:700;color:{col_cola};">{data['total_cola']}</div><div style="font-size:9px;color:#94a3b8;letter-spacing:0.8px;text-transform:uppercase;margin-top:3px;">En cola</div></td>
  <td width="20%" style="padding:6px;text-align:center;"><div style="font-size:16px;font-weight:700;color:{col_err};">{data['total_errores']}</div><div style="font-size:9px;color:#94a3b8;letter-spacing:0.8px;text-transform:uppercase;margin-top:3px;">Errores</div></td>
  <td width="20%" style="padding:6px;text-align:center;"><div style="font-size:16px;font-weight:700;color:{col_lag};">{data['total_lagunas']}</div><div style="font-size:9px;color:#94a3b8;letter-spacing:0.8px;text-transform:uppercase;margin-top:3px;">Lagunas</div></td>
  <td width="20%" style="padding:6px;text-align:center;"><div style="font-size:16px;font-weight:700;color:{col_exc};">{data['total_excesos']}</div><div style="font-size:9px;color:#94a3b8;letter-spacing:0.8px;text-transform:uppercase;margin-top:3px;">Exceso caudal</div></td>
</tr>
</table>
</td></tr></table>
</td></tr>
</table>
</td></tr></table>
"""

    # SECCIONES POR PROYECTO (una card por proyecto)
    for project_name, pts in sorted(data['projects'].items()):
        proj_med = sum(p['stats']['total_records'] for p in pts)
        proj_esp = sum(p['stats']['expected_count'] for p in pts)
        proj_cov = round(proj_med / proj_esp * 100, 1) if proj_esp else 0
        proj_vou = sum(p['stats']['vouchers'] for p in pts)
        proj_lag = sum(p['stats']['missing_count'] for p in pts)

        lag_part = f'<span style="color:#dc2626;"> · {proj_lag} lagunas</span>' if proj_lag else ''
        html += f"""
<!-- CARD: PROYECTO {project_name} -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:12px 12px 4px;">
<table role="presentation" width="100%" class="card" style="max-width:900px;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 8px 26px rgba(15,34,71,0.07);">
<tr><td class="pad-main" style="padding:26px 30px 0;">
  <div style="font-size:17px;font-weight:700;color:#16294F;letter-spacing:-0.2px;">{project_name}</div>
  <div style="font-size:12px;color:#64748b;margin-top:6px;">{len(pts)} puntos · {format_number(proj_med)} mediciones · {format_number(proj_vou)} envíos DGA · cobertura {proj_cov:.1f}%{lag_part}</div>
</td></tr>
<tr><td class="pad-sec" style="padding:8px 20px 22px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr style="background:#f8fafc;">
    <th class="th" style="padding:14px 12px;text-align:left;font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.8px;">Punto</th>
    <th class="th" style="padding:14px 12px;text-align:left;font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.8px;">Código / Estándar</th>
    <th class="th" style="padding:14px 12px;text-align:center;font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.8px;">Mediciones<br>esp/real</th>
    <th class="th" style="padding:14px 12px;text-align:center;font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.8px;">Cobertura</th>
    <th class="th" style="padding:14px 12px;text-align:center;font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.8px;">DGA<br>enviados</th>
    <th class="th hide-mobile" style="padding:14px 12px;text-align:center;font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.8px;">Total m³</th>
    <th class="th hide-mobile" style="padding:14px 12px;text-align:center;font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.8px;">Caudal máx<br>L/s</th>
    <th class="th hide-mobile" style="padding:14px 12px;text-align:center;font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.8px;">Últ. medición</th>
    <th class="th" style="padding:14px 12px;text-align:center;font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.8px;">Estado</th>
  </tr>
"""
        for i, p in enumerate(sorted(pts, key=lambda x: (x['code_dga'] == '', x['code_dga']))):
            s = p['stats']
            row_bg = '#ffffff' if i % 2 == 0 else '#fbfcfe'
            std_short = p['standard'][:3] if p['standard'] else ''
            flow_cell = format_float(s['flow_max'])
            if s['exceeds_flow']:
                flow_cell = (f'<span style="color:#dc2626;font-weight:700;">{flow_cell}</span>'
                             f'<br><span style="font-size:9px;color:#dc2626;font-weight:700;letter-spacing:0.5px;">EXCESO</span>')
            lag_cell = f'<span style="color:#dc2626;">{s["missing_count"]}</span>' if s['missing_count'] else '0'
            dga_cell = f'<span style="font-weight:700;color:#16a34a;">{s["vouchers"]}</span>'
            if s['in_queue']:
                dga_cell += f' <span style="color:#d97706;">· {s["in_queue"]} cola</span>'
            last_date = format_dt_chile(s['last_date'], '%d/%m %H:%M') if s['last_date'] else '<span style="color:#dc2626;">SIN DATOS</span>'

            html += f"""
  <tr style="background:{row_bg};">
    <td class="cell" style="padding:14px 12px;font-size:13.5px;font-weight:600;color:#16294F;">{p['title']}<br><span style="font-size:10px;color:#94a3b8;font-weight:400;">{p['provider']} · P#{p['id']}</span></td>
    <td class="cell" style="padding:14px 12px;font-size:12px;color:#475569;">{p['code_dga'] or 'N/A'}<br><span style="font-size:9px;color:#94a3b8;letter-spacing:0.8px;text-transform:uppercase;">{std_short}</span></td>
    <td class="cell" style="padding:14px 12px;text-align:center;font-size:12px;color:#94a3b8;font-variant-numeric:tabular-nums;">{s['expected_count']} / <b style="color:#334155;">{s['total_records']}</b></td>
    <td class="cell" style="padding:14px 12px;text-align:center;">{coverage_bar(s['coverage'])}</td>
    <td class="cell" style="padding:14px 12px;text-align:center;font-size:12px;">{dga_cell}<br><span style="font-size:10px;color:#94a3b8;">{lag_cell} lag.</span></td>
    <td class="cell hide-mobile" style="padding:14px 12px;text-align:right;font-size:12px;color:#334155;font-variant-numeric:tabular-nums;">{format_number(s['total_final'])}</td>
    <td class="cell hide-mobile" style="padding:14px 12px;text-align:center;font-size:12px;color:#334155;font-variant-numeric:tabular-nums;">{flow_cell}<br><span style="font-size:10px;color:#94a3b8;">aut. {format_float(s['flow_granted'])}</span></td>
    <td class="cell hide-mobile" style="padding:14px 12px;text-align:center;font-size:11px;color:#475569;">{last_date}</td>
    <td class="cell" style="padding:14px 12px;text-align:center;">{badge(s['health'])}</td>
  </tr>
"""
        html += "</table></td></tr></table></td></tr></table>"

    # LAGUNAS DETALLE
    has_gaps = any(s['missing_count'] for p in data['points'] for s in [p['stats']])
    if has_gaps:
        html += """
<!-- CARD: LAGUNAS -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:12px 12px 4px;">
<table role="presentation" width="100%" class="card" style="max-width:900px;background:linear-gradient(180deg,#fffbeb 0%,#fff7ed 100%);border-radius:20px;overflow:hidden;box-shadow:0 8px 26px rgba(245,158,11,0.10);">
<tr><td class="pad-main" style="padding:26px 30px 4px;">
  <div style="font-size:17px;font-weight:700;color:#16294F;letter-spacing:-0.2px;">Detalle de Lagunas</div>
  <div style="font-size:12px;color:#64748b;margin-top:6px;">Mediciones esperadas que no llegaron en el período</div>
</td></tr>
<tr><td class="pad-sec" style="padding:10px 20px 22px;">
"""
        for p in data['points']:
            s = p['stats']
            if s['missing_count']:
                missing_str = ', '.join(format_dt_chile(m, '%d/%m %H:%M') for m in sorted(s['missing'])[:12])
                if len(s['missing']) > 12:
                    missing_str += f' ... (+{len(s["missing"]) - 12} más)'
                html += f"""
  <div style="background:rgba(255,255,255,0.75);border-left:3px solid #f59e0b;border-radius:12px;padding:14px 18px;margin-bottom:10px;">
    <b style="font-size:13px;color:#7c2d12;">{p['title']}</b> <span style="font-size:11px;color:#9a3412;">({p['code_dga']})</span> —
    <span style="font-size:12px;color:#7c2d12;">{s['missing_count']} lagunas</span>
    <div style="font-size:11px;color:#9a3412;margin-top:5px;">{missing_str}</div>
  </div>
"""
        html += "</td></tr></table></td></tr></table>"

    # EXCESO DE CAUDAL
    has_excess = any(p['stats']['exceeds_flow'] for p in data['points'])
    if has_excess:
        html += """
<!-- CARD: EXCESO -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:12px 12px 4px;">
<table role="presentation" width="100%" class="card" style="max-width:900px;background:linear-gradient(180deg,#fef2f2 0%,#fee2e2 100%);border-radius:20px;overflow:hidden;box-shadow:0 8px 26px rgba(239,68,68,0.10);">
<tr><td class="pad-main" style="padding:26px 30px 4px;">
  <div style="font-size:17px;font-weight:700;color:#16294F;letter-spacing:-0.2px;">Exceso de Caudal</div>
  <div style="font-size:12px;color:#64748b;margin-top:6px;">Puntos que superaron el caudal autorizado en el período</div>
</td></tr>
<tr><td class="pad-sec" style="padding:10px 20px 22px;">
"""
        for p in data['points']:
            s = p['stats']
            if s['exceeds_flow']:
                html += f"""
  <div style="background:rgba(255,255,255,0.75);border-left:3px solid #ef4444;border-radius:12px;padding:14px 18px;margin-bottom:10px;">
    <b style="font-size:13px;color:#7f1d1d;">{p['title']}</b> <span style="font-size:11px;color:#991b1b;">({p['code_dga']})</span> —
    Caudal máx <b>{format_float(s['flow_max'])} L/s</b> vs autorizado <b>{format_float(s['flow_granted'])} L/s</b>
  </div>
"""
        html += "</td></tr></table></td></tr></table>"

    # FOOTER
    html += """
<!-- FOOTER -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td align="center" style="padding:18px 12px 26px;">
<table role="presentation" width="100%" style="max-width:900px;"><tr><td style="text-align:center;font-size:11px;color:#94a3b8;line-height:1.7;">
  Sistema de Telemetría SmartHydro · Reporte automático semanal<br>
  Ante dudas o anomalías, contacta a soporte@smarthydro.cl
</td></tr></table>
</td></tr></table>
</body>
</html>
"""
    return html


def generate_pdf(data):
    """Generar PDF del reporte (reportlab platypus). Retorna bytes."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    user = data['user']
    nombre = f"{user.first_name} {user.last_name}".strip() or user.email
    cliente = data['points'][0]['client'] if data['points'] else 'N/A'

    NAVY = colors.HexColor('#16294F')
    INK = colors.HexColor('#1e293b')
    MUTED = colors.HexColor('#94a3b8')
    ROW_ALT = colors.HexColor('#f8fafc')
    HEADER_BG = colors.HexColor('#eef2f9')
    GRID = colors.HexColor('#e2e8f0')
    GREEN = colors.HexColor('#16a34a')
    AMBER = colors.HexColor('#d97706')
    RED = colors.HexColor('#dc2626')
    COL_FRAC = [0.13, 0.13, 0.10, 0.10, 0.10, 0.11, 0.11, 0.12, 0.10]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=14 * mm, bottomMargin=12 * mm,
        title=f"Reporte Semanal SmartHydro - {nombre}",
    )

    st_title = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=17,
                              textColor=colors.white)
    st_sub = ParagraphStyle('sub', fontName='Helvetica', fontSize=9,
                            textColor=colors.HexColor('#b9cdf0'), leading=13)
    st_h2 = ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=11.5,
                           textColor=NAVY, spaceBefore=12, spaceAfter=4)
    st_th = ParagraphStyle('th', fontName='Helvetica-Bold', fontSize=7.5,
                           textColor=MUTED, alignment=TA_CENTER)
    st_td = ParagraphStyle('td', fontName='Helvetica', fontSize=8,
                           textColor=INK, leading=11)
    st_td_c = ParagraphStyle('tdc', parent=st_td, alignment=TA_CENTER)
    st_td_r = ParagraphStyle('tdr', parent=st_td, alignment=TA_RIGHT)
    st_note = ParagraphStyle('note', fontName='Helvetica', fontSize=7.5,
                             textColor=MUTED, alignment=TA_CENTER, leading=10)
    st_alert = ParagraphStyle('alert', parent=st_td, fontSize=8, leading=12)

    story = []

    # Header
    header = Table(
        [[Paragraph("REPORTE SEMANAL DE PUNTOS", st_title)],
         [Paragraph(f"{cliente} · {nombre}  |  Período: "
                    f"{format_dt_chile(data['start'], '%d/%m/%Y')} – "
                    f"{format_dt_chile(data['end'], '%d/%m/%Y')}  |  "
                    f"Estado: {data['health']}", st_sub)]],
        colWidths=[doc.width])
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('LEFTPADDING', (0, 0), (-1, -1), 14),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    story.append(header)
    story.append(Spacer(1, 7))

    # KPIs
    kpi = Table(
        [[Paragraph('PUNTOS', st_th), Paragraph('MEDICIONES', st_th),
          Paragraph('ENVÍOS DGA', st_th), Paragraph('COBERTURA', st_th)],
         [Paragraph(str(data['total_points']), st_td_c),
          Paragraph(format_number(data['total_mediciones']), st_td_c),
          Paragraph(format_number(data['total_vouchers']), st_td_c),
          Paragraph(f"{data['global_coverage']:.1f}%", st_td_c)]],
        colWidths=[doc.width / 4] * 4)
    kpi.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('GRID', (0, 0), (-1, -1), 0.4, GRID),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(kpi)
    story.append(Spacer(1, 6))

    # Tablas por proyecto
    for project_name, pts in sorted(data['projects'].items()):
        story.append(Paragraph(project_name, st_h2))
        headers = ['PUNTO', 'CÓDIGO / EST.', 'MED. ESP/REAL', 'COBERTURA',
                   'DGA ENVIADOS', 'TOTAL m³', 'CAUDAL MÁX L/s',
                   'ÚLT. MEDICIÓN', 'ESTADO']
        rows = [[Paragraph(h, st_th) for h in headers]]
        for p in sorted(pts, key=lambda x: (x['code_dga'] == '', x['code_dga'])):
            s = p['stats']
            std_short = p['standard'][:3] if p['standard'] else ''
            estado = ('OK' if s['health'] == 'ok'
                      else ('ATENCIÓN' if s['health'] == 'warn' else 'CRÍTICO'))
            e_color = GREEN if s['health'] == 'ok' else (AMBER if s['health'] == 'warn' else RED)
            flow = format_float(s['flow_max'])
            if s['exceeds_flow']:
                flow = f"{flow} (EXCESO)"
            dga = str(s['vouchers'])
            if s['in_queue']:
                dga += f" ({s['in_queue']} cola)"
            last = format_dt_chile(s['last_date'], '%d/%m %H:%M') if s['last_date'] else 'SIN DATOS'
            rows.append([
                Paragraph(f"<b>{p['title']}</b><br/><font size='6' color='#94a3b8'>"
                          f"{p['provider']} · P#{p['id']}</font>", st_td),
                Paragraph(f"{p['code_dga'] or 'N/A'}<br/><font size='6' color='#94a3b8'>"
                          f"{std_short}</font>", st_td),
                Paragraph(f"{s['expected_count']} / {s['total_records']}", st_td_c),
                Paragraph(f"{s['coverage']:.1f}%", st_td_c),
                Paragraph(dga, st_td_c),
                Paragraph(format_number(s['total_final']), st_td_r),
                Paragraph(flow, st_td_c),
                Paragraph(last, st_td_c),
                Paragraph(f"<font color='{e_color.hexval()}'>• {estado}</font>", st_td_c),
            ])
        tbl = Table(rows, colWidths=[doc.width * f for f in COL_FRAC], repeatRows=1)
        tstyle = [
            ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.4, GRID),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]
        for i in range(1, len(rows)):
            if i % 2 == 0:
                tstyle.append(('BACKGROUND', (0, i), (-1, i), ROW_ALT))
        tbl.setStyle(TableStyle(tstyle))
        story.append(tbl)

    # Lagunas
    if any(s['missing_count'] for p in data['points'] for s in [p['stats']]):
        story.append(Paragraph("Detalle de Lagunas", st_h2))
        for p in data['points']:
            s = p['stats']
            if s['missing_count']:
                missing_str = ', '.join(
                    format_dt_chile(m, '%d/%m %H:%M') for m in sorted(s['missing'])[:12])
                if len(s['missing']) > 12:
                    missing_str += f' ... (+{len(s["missing"]) - 12} más)'
                story.append(Paragraph(
                    f"<b>{p['title']}</b> ({p['code_dga']}) — {s['missing_count']} lagunas: "
                    f"<font color='#9a3412'>{missing_str}</font>", st_alert))

    # Exceso de caudal
    if any(p['stats']['exceeds_flow'] for p in data['points']):
        story.append(Paragraph("Exceso de Caudal", st_h2))
        for p in data['points']:
            s = p['stats']
            if s['exceeds_flow']:
                story.append(Paragraph(
                    f"<b>{p['title']}</b> ({p['code_dga']}) — Caudal máx "
                    f"<b>{format_float(s['flow_max'])} L/s</b> vs autorizado "
                    f"<b>{format_float(s['flow_granted'])} L/s</b>", st_alert))

    story.append(Spacer(1, 8))
    story.append(Paragraph("Sistema de Telemetría SmartHydro · Reporte automático semanal", st_note))

    doc.build(story)
    return buf.getvalue()


def generate_excel(data):
    """Excel con SOLO las mediciones enviadas a DGA (fecha medición + voucher).

    Una hoja por proyecto con las mediciones que tienen voucher DGA.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    NAVY = '16294F'
    HEADER_FILL = PatternFill('solid', fgColor=NAVY)
    HEADER_FONT = Font(name='Calibri', bold=True, color='FFFFFF', size=11)
    THIN = Side(style='thin', color='D9E2F0')
    BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
    WRAP = Alignment(horizontal='left', vertical='center')

    user = data['user']
    nombre = f"{user.first_name} {user.last_name}".strip() or user.email
    cliente = data['points'][0]['client'] if data['points'] else 'N/A'

    def fill_header(ws, row, headers):
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=row, column=c, value=h)
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.border = BORDER
            cell.alignment = Alignment(horizontal='center', vertical='center')

    def naive_clt(dt):
        if dt is None:
            return None
        return to_chile_tz(dt).replace(tzinfo=None)

    wb = Workbook()

    # ---- Hoja Resumen ----
    ws = wb.active
    ws.title = 'Resumen'
    ws['A1'] = f"REPORTE SEMANAL SMARTHYDRO — {cliente}"
    ws['A1'].font = Font(bold=True, size=14, color=NAVY)
    ws['A2'] = f"{nombre}  |  Período: {format_dt_chile(data['start'], '%d/%m/%Y')} – {format_dt_chile(data['end'], '%d/%m/%Y')}"
    ws['A2'].font = Font(size=10, color='64748B')

    headers_r = ['Puntos', 'Mediciones', 'Envíos DGA', 'Cobertura', 'En cola', 'Errores', 'Lagunas', 'Exceso caudal']
    values_r = [data['total_points'], data['total_mediciones'], data['total_vouchers'],
                f"{data['global_coverage']:.1f}%", data['total_cola'], data['total_errores'],
                data['total_lagunas'], data['total_excesos']]
    for c, (h, v) in enumerate(zip(headers_r, values_r), 1):
        ws.cell(row=4, column=c, value=v).font = Font(bold=True, size=13, color=NAVY)
        ws.cell(row=5, column=c, value=h).font = Font(size=9, color='94A3B8')

    summary_headers = ['Punto', 'Código DGA', 'Proyecto', 'Mediciones', 'DGA enviados', 'Lagunas', 'Estado']
    ws.cell(row=7, column=1, value='Detalle por punto').font = Font(bold=True, size=11, color=NAVY)
    fill_header(ws, 8, summary_headers)
    r = 9
    for pt in data['points']:
        s = pt['stats']
        estado = 'OK' if s['health'] == 'ok' else ('ATENCIÓN' if s['health'] == 'warn' else 'CRÍTICO')
        row_vals = [pt['title'], pt['code_dga'] or 'N/A', pt['project'],
                    s['total_records'], s['vouchers'], s['missing_count'], estado]
        for c, v in enumerate(row_vals, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.border = BORDER
            cell.alignment = WRAP
        r += 1
    for col in range(1, len(summary_headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 16

    # ---- Hojas por proyecto con mediciones DGA ----
    for project_name, pts in sorted(data['projects'].items()):
        sheet_title = project_name[:31]
        wsb = wb.create_sheet(title=sheet_title)
        headers_b = ['Punto', 'Código DGA', 'Fecha medición', 'N° voucher']
        fill_header(wsb, 1, headers_b)
        rr = 2
        for p in sorted(pts, key=lambda x: (x['code_dga'] == '', x['code_dga'])):
            for rec in p['stats']['dga_sent']:
                dt = naive_clt(rec['date'])
                vals = [p['title'], p['code_dga'] or 'N/A', dt, rec['voucher']]
                for c, v in enumerate(vals, 1):
                    cell = wsb.cell(row=rr, column=c, value=v)
                    cell.border = BORDER
                    cell.alignment = WRAP
                if dt is not None:
                    wsb.cell(row=rr, column=3).number_format = 'DD/MM/YYYY HH:MM'
                rr += 1
        wsb.column_dimensions['A'].width = 22
        wsb.column_dimensions['B'].width = 16
        wsb.column_dimensions['C'].width = 20
        wsb.column_dimensions['D'].width = 22
        wsb.freeze_panes = 'A2'

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def generate_text(data):
    """Versión texto plano del reporte (fallback email)."""
    user = data['user']
    nombre = f"{user.first_name} {user.last_name}".strip() or user.email
    lines = []
    lines.append(f"REPORTE SEMANAL DE PUNTOS - {nombre}")
    lines.append(f"Periodo: {format_dt_chile(data['start'], '%d/%m/%Y')} - {format_dt_chile(data['end'], '%d/%m/%Y')}")
    lines.append("=" * 50)
    lines.append(f"Puntos: {data['total_points']} | Mediciones: {data['total_mediciones']} | "
                 f"DGA: {data['total_vouchers']} | Cobertura: {data['global_coverage']}%")
    lines.append(f"En cola: {data['total_cola']} | Errores: {data['total_errores']} | "
                 f"Lagunas: {data['total_lagunas']} | Exceso caudal: {data['total_excesos']}")
    lines.append("")

    for project_name, pts in sorted(data['projects'].items()):
        lines.append(f"--- {project_name} ---")
        for p in pts:
            s = p['stats']
            estado = 'OK' if s['health'] == 'ok' else ('ATENCION' if s['health'] == 'warn' else 'CRITICO')
            extra = f" CAUDAL EXCESO!" if s['exceeds_flow'] else ""
            lines.append(f"* {p['title']} ({p['code_dga']}) [{estado}]"
                         f" mediciones {s['total_records']}/{s['expected_count']} ({s['coverage']}%)"
                         f" DGA {s['vouchers']} lagunas {s['missing_count']}"
                         f" total {s['total_final']} caudal_max {s['flow_max']}{extra}")
        lines.append("")

    lines.append("Sistema SmartHydro")
    return "\n".join(lines)


def run(user_id=35, to=None, cc=None, preview=False):
    """
    Generar y enviar reporte semanal de un usuario owner (solo clientes DGA).

    Adjunta:
      - PDF con el reporte visual
      - Excel con SOLO las mediciones enviadas a DGA (fecha medición + voucher)

    Args:
        user_id: id del usuario owner (default: Constanza, id=35)
        to: destinatario (default: email del usuario)
        cc: lista de emails en copia (se omiten en modo preview)
        preview: True = envío de validación a un destinatario de prueba
    """
    logger.info(f"Generando reporte semanal para user_id={user_id}...")

    try:
        data = build_report(user_id)

        # Reporte exclusivo para clientes con cumplimiento DGA
        if not data['has_dga_compliance']:
            logger.warning(
                f"Usuario {user_id} sin cumplimiento DGA: reporte exclusivo para clientes DGA. Abortado.")
            print(f"⚠️ Usuario {user_id} sin cumplimiento DGA: reporte exclusivo para clientes DGA. Abortado.")
            return

        html_content = generate_html(data)
        text_content = generate_text(data)
        pdf_bytes = generate_pdf(data)
        excel_bytes = generate_excel(data)

        user = data['user']
        nombre = f"{user.first_name} {user.last_name}".strip() or user.email
        semana = f"{format_dt_chile(data['start'], '%d-%m-%Y')}_{format_dt_chile(data['end'], '%d-%m-%Y')}"

        if preview:
            recipients = [to] if to else []
            cc_list = []
            subject = (f"[PREVIEW] Reporte Semanal {nombre} - "
                       f"Semana {format_dt_chile(data['start'], '%d/%m')}-{format_dt_chile(data['end'], '%d/%m')}")
        else:
            recipients = [to] if to else [user.email]
            cc_list = cc or []
            subject = (f"Reporte Semanal de Puntos - {nombre} - "
                       f"Semana {format_dt_chile(data['start'], '%d/%m')}-{format_dt_chile(data['end'], '%d/%m')}")

        if not recipients:
            logger.warning("No hay destinatarios")
            return

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
            to=recipients,
            cc=cc_list,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.attach(f"Reporte_Semanal_{semana}.pdf", pdf_bytes,
                   "application/pdf")
        msg.attach(f"Mediciones_DGA_{semana}.xlsx", excel_bytes,
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        msg.send()

        logger.info(f"Reporte enviado a {', '.join(recipients)}"
                    + (f" (CC: {', '.join(cc_list)})" if cc_list else ""))
        print(f"✅ Reporte semanal enviado a: {', '.join(recipients)}"
              + (f" | CC: {', '.join(cc_list)}" if cc_list else ""))
        print(f"   Asunto: {subject}")
        print(f"   Puntos: {data['total_points']} | Mediciones: {data['total_mediciones']} | "
              f"Cobertura: {data['global_coverage']}%")
        print(f"   Adjuntos: PDF + Excel (mediciones DGA: {data['total_vouchers']})")

    except Exception as e:
        logger.error(f"Error generando reporte semanal: {e}", exc_info=True)
        raise


def run_weekly():
    """Enviar reporte semanal a todos los owners con recibir_reporte activo.

    Usado por CRONJOBS (Viernes 16:00 Chile / 20:00 UTC). Por cada owner
    habilitado envía el reporte a su email con los CCs configurados.
    """
    recipients = get_report_recipients()
    if not recipients:
        logger.info("run_weekly: ningún owner con recibir_reporte activo.")
        print("ℹ️ Ningún owner con recibir_reporte activo.")
        return

    for rec in recipients:
        try:
            run(user_id=rec['user_id'], to=rec['owner_email'] or None,
                cc=rec['cc'], preview=False)
        except Exception as e:
            logger.error(f"run_weekly: fallo para user_id={rec['user_id']}: {e}", exc_info=True)
            print(f"❌ Fallo para user_id={rec['user_id']}: {e}")
