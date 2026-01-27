
import logging
from datetime import datetime, timedelta
import pytz
from django.db.models import Q
from api.core.models import InteractionDetail, CatchmentPoint, ProfileDataConfigCatchment

logger = logging.getLogger(__name__)

class TelemetryAnalysisService:
    @staticmethod
    def audit_active_points(days_back=30):
        """
        Audita puntos activos buscando incoherencias (Total=0 con Pulsos>0, Saltos, Caídas).
        Retorna un resumen en texto.
        """
        try:
            points = CatchmentPoint.objects.filter(
                data_config_profiles__is_telemetry=True
            ).distinct()
            
            chile_tz = pytz.timezone("America/Santiago")
            end_date = datetime.now(chile_tz)
            start_date = end_date - timedelta(days=days_back)
            
            report = [f"📊 **Auditoría de Telemetría (Últimos {days_back} días)**"]
            report.append(f"Puntos analizados: {points.count()}")
            
            issues_zeros = 0
            issues_drops = 0
            issues_jumps = 0
            points_with_issues = set()
            
            for point in points:
                records = InteractionDetail.objects.filter(
                    catchment_point_id=point.id,
                    date_time_medition__range=(start_date, end_date)
                ).order_by('date_time_medition')
                
                if not records.exists():
                    continue
                    
                # 1. Zero Totals with Pulses > 0
                zeros = records.filter(total__in=['0', '0.0', '0.00'], pulses__gt=0).count()
                if zeros > 0:
                    points_with_issues.add(point.title)
                    issues_zeros += zeros
                
                # 2. Jumps/Drops
                prev_total = -1
                for r in records:
                    try:
                        curr = float(r.total)
                        if prev_total != -1:
                            diff = curr - prev_total
                            if diff < -100:
                                issues_drops += 1
                                points_with_issues.add(point.title)
                            elif diff > 500:
                                issues_jumps += 1
                                # Jumps are often recoveries now, but still worth noting
                        prev_total = curr
                    except:
                        continue

            report.append(f"\n**Resultados:**")
            report.append(f"✅ Incoherencias Críticas (Total=0, Pulsos>0): {issues_zeros}")
            report.append(f"⚠️ Caídas Grandes (Drop to 0): {issues_drops}")
            report.append(f"📈 Saltos Masivos (Recuperaciones): {issues_jumps}")
            
            if points_with_issues:
                top_points = list(points_with_issues)[:5]
                report.append(f"\n**Puntos con anomalías recientes:**")
                for p in top_points:
                    report.append(f"- {p}")
                if len(points_with_issues) > 5:
                    report.append(f"... y {len(points_with_issues)-5} más.")
            else:
                report.append(f"\n✨ Sistema estable. No se detectaron anomalías críticas.")
                
            return "\n".join(report)
            
        except Exception as e:
            logger.error(f"Error in audit_active_points: {e}")
            return f"❌ Error ejecutando auditoría: {str(e)}"

    @staticmethod
    def analyze_additions():
        """
        Analiza adiciones (offsets) activas para detectar falsos resets.
        """
        try:
            # Puntos a excluir (solicitud explícita)
            excluded_titles = ["planta 1 p1", "planta 1 - p1"]
            
            profiles = ProfileDataConfigCatchment.objects.filter(addition__gt=0)
            
            report = ["🔍 **Análisis de Adiciones (Falsos Resets)**"]
            report.append(f"Puntos con adición activa: {profiles.count()}")
            
            suspicious_count = 0
            
            for p in profiles:
                point = p.point_catchment
                
                # Exclusion logic
                if any(ex in point.title.lower() for ex in excluded_titles):
                    continue
                    
                addition = p.addition
                last = InteractionDetail.objects.filter(catchment_point_id=point.id).order_by('-created').first()
                
                if not last or not last.pulses:
                    continue
                    
                try:
                    current_pulses = float(last.pulses)
                    
                    # Estimate Raw M3
                    factor = 1000
                    for scheme in point.schemes.all():
                        for var in scheme.variables.all():
                            if var.type_variable == 'TOTALIZADO' and var.pulses_factor:
                                factor = var.pulses_factor
                    
                    raw_m3 = (current_pulses * factor) / 1000.0
                    
                    if raw_m3 > 0:
                        ratio = addition / raw_m3
                        if 0.8 < ratio < 1.2:
                           report.append(f"\n⚠️ **{point.title}** (ID {point.id})")
                           report.append(f"   - Adición: {addition:,.0f} | Raw: {raw_m3:,.0f}")
                           report.append(f"   - Estado: **POSIBLE DOBLE CONTEO**")
                           suspicious_count += 1
                           
                except Exception:
                    continue
            
            if suspicious_count == 0:
                report.append("\n✅ Todas las adiciones parecen válidas (continuidad correcta).")
            else:
                report.append(f"\n⚠️ Se detectaron {suspicious_count} adiciones sospechosas.")
                
            return "\n".join(report)

        except Exception as e:
            logger.error(f"Error in analyze_additions: {e}")
            return f"❌ Error ejecutando análisis: {str(e)}"
