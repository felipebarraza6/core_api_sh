from django.db.models import Sum
from rest_framework import serializers
import pytz
from datetime import datetime, time

from api.core.models import InteractionDetail, ProfileDataConfigCatchment, Variable


def parse_total(val):
    if not val:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    try:
        # Limpiar puntos de miles si vienen en el string (ej: 1.130.840)
        # y manejar decimales si existen
        clean_val = str(val).replace('.', '')
        if ',' in clean_val:
            clean_val = clean_val.replace(',', '.')
        return int(float(clean_val))
    except (ValueError, TypeError):
        return 0


class InteractionDetailModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = InteractionDetail
        fields = "__all__"

    def to_representation(self, instance):
        # 1. Inicializar caché de solicitud si no existe
        if 'request_cache' not in self.context:
            self.context['request_cache'] = {
                'points_config': {},
                'daily_data': {}, # [cp_id][date] = { id: { total_diff, total_today_diff } }
                'prev_record_totals': {} # [cp_id][curr_id] = prev_total
            }
        
        request_cache = self.context['request_cache']
        representation = super().to_representation(instance)
        catchment_point = instance.catchment_point
        cp_id = catchment_point.id

        # 2. Obtener configuración del punto
        if cp_id not in request_cache['points_config']:
            from api.core.models import DgaDataConfigCatchment
            if hasattr(catchment_point, '_prefetched_objects_cache') and 'data_config_profiles' in catchment_point._prefetched_objects_cache:
                profiles = catchment_point._prefetched_objects_cache['data_config_profiles']
                total_d6 = sum(int(profile.d6) if profile.d6 is not None else 0 for profile in profiles)
            else:
                total_d6 = ProfileDataConfigCatchment.objects.filter(point_catchment=catchment_point).aggregate(total=Sum("d6"))["total"] or 0
            
            has_avg_flow = Variable.objects.filter(type_variable="CAUDAL_PROMEDIO", scheme_catchment__points_catchment=catchment_point).exists()
            dga_config = DgaDataConfigCatchment.objects.filter(point_catchment=catchment_point).first()
            request_cache['points_config'][cp_id] = {'total_d6': total_d6, 'has_avg_flow': has_avg_flow, 'dga_config': dga_config}

        config = request_cache['points_config'][cp_id]
        total_d6 = config['total_d6']

        # Aplicar d6 al total
        current_total = representation.get("total", 0) or 0
        total_d6_int = int(float(total_d6))
        current_total_int = int(float(current_total))
        actual_total = total_d6_int + current_total_int
        representation["total"] = actual_total

        # ✅ OPTIMIZACIÓN CRÍTICA: Procesar día completo en batch para evitar N+1
        try:
            if instance.date_time_medition:
                from django.utils import timezone
                record_dt = instance.date_time_medition
                record_date = timezone.localtime(record_dt).date()
                
                if 'prev_day_totals' not in request_cache:
                    request_cache['prev_day_totals'] = {} # [cp_id][date] = last_total
                
                if cp_id not in request_cache['daily_data']:
                    request_cache['daily_data'][cp_id] = {}
                    request_cache['prev_day_totals'][cp_id] = {}
                
                if record_date not in request_cache['daily_data'][cp_id]:
                    # Batch fetch: todos los registros del día para este punto
                    day_records = list(InteractionDetail.objects.filter(
                        catchment_point_id=cp_id,
                        date_time_medition__date=record_date
                    ).order_by('date_time_medition').only('id', 'total', 'date_time_medition', 'date_time_last_logger'))
                    
                    # Intentar obtener el total del día anterior desde el caché si ya procesamos el día anterior
                    from datetime import timedelta
                    yesterday = record_date - timedelta(days=1)
                    
                    if yesterday in request_cache['prev_day_totals'].get(cp_id, {}):
                        last_total_val = request_cache['prev_day_totals'][cp_id][yesterday]
                        yesterday_data = request_cache['daily_data'][cp_id].get(yesterday, {})
                        if yesterday_data:
                            last_id = list(yesterday_data.keys())[-1]
                            try:
                                last_rec = InteractionDetail.objects.only('date_time_medition').get(id=last_id)
                                last_date_val = last_rec.date_time_medition
                            except:
                                last_date_val = datetime.combine(yesterday, time(23, 59, 59)).replace(tzinfo=pytz.timezone("America/Santiago"))
                        else:
                            last_date_val = None
                    else:
                        # Si no está en caché, buscar el último registro válido de días anteriores
                        prev_day_last = InteractionDetail.objects.filter(
                            catchment_point_id=cp_id,
                            date_time_medition__date__lt=record_date
                        ).exclude(total__in=[0, '0', None, '']).order_by('-date_time_medition').only('id', 'total', 'date_time_medition').first()
                        
                        last_total_val = parse_total(prev_day_last.total) if prev_day_last else 0
                        last_date_val = prev_day_last.date_time_medition if prev_day_last else None
                    
                    first_date_of_day_interval = last_date_val 
                    
                    batch_map = {}
                    running_today = 0
                    
                    view = self.context.get('view')
                    view_name = view.__class__.__name__ if view else ""
                    is_monthly_view = "Month" in view_name
                    
                    for idx, rec in enumerate(day_records):
                        curr_rec_total = parse_total(rec.total)
                        curr_date = rec.date_time_medition
                        
                        dt = 0
                        is_duplicate_ts = False
                        if last_date_val and curr_date:
                            dt = (curr_date - last_date_val).total_seconds()
                            if dt <= 0:
                                is_duplicate_ts = True
                        
                        if is_duplicate_ts:
                            diff = 0 
                            calc_flow = 0.0
                            if idx > 0:
                                prev_rec = day_records[idx-1]
                                if prev_rec.id in batch_map:
                                    diff = batch_map[prev_rec.id]['total_diff']
                                    calc_flow = batch_map[prev_rec.id]['calc_flow']
                        else:
                            diff = curr_rec_total - last_total_val
                            if diff < 0: diff = curr_rec_total 
                            
                            # ✅ ANTI-RESET RULE: Clamp spikes > 500 to 0 (Same as backend)
                            if diff > 500: diff = 0
                            
                            diff = max(0, diff)
                            
                            calc_flow = 0.0
                            if config.get('has_avg_flow') and dt > 0:
                                calc_flow = round((diff / dt) * 1000.0, 2)
                            
                            running_today += diff

                        batch_map[rec.id] = {
                            'total_diff': diff,
                            'total_today_diff': running_today,
                            'calc_flow': calc_flow
                        }
                        
                        if not is_duplicate_ts:
                            # Puente de telemetría: si cae a 0, no movemos el baseline
                            if curr_rec_total > 0 or last_total_val == 0:
                                last_total_val = curr_rec_total
                                last_date_val = curr_date

                    if is_monthly_view and day_records and config.get('has_avg_flow'):
                        last_rec = day_records[-1]
                        total_day_vol = running_today
                        total_day_seconds = (last_date_val - first_date_of_day_interval).total_seconds() if last_date_val and first_date_of_day_interval else 0
                        if total_day_seconds > 0:
                            daily_avg_flow = round((total_day_vol / total_day_seconds) * 1000.0, 2)
                            daily_avg_m3h = round(total_day_vol / (total_day_seconds / 3600.0), 2)
                            if last_rec.id in batch_map:
                                batch_map[last_rec.id]['calc_flow'] = daily_avg_flow
                                batch_map[last_rec.id]['total_diff'] = daily_avg_m3h
                    
                    request_cache['daily_data'][cp_id][record_date] = batch_map
                    request_cache['prev_day_totals'][cp_id][record_date] = last_total_val

                day_cache = request_cache['daily_data'][cp_id][record_date]
                if instance.id in day_cache:
                    res = day_cache[instance.id]
                    representation["total_diff"] = res['total_diff']
                    representation["total_today_diff"] = res['total_today_diff']
                    
                    # ✅ ENFORCE: If average flow is enabled, use the calculated value ALWAYS (even if 0)
                    if config.get('has_avg_flow'):
                        representation["flow"] = res.get('calc_flow', 0.0)
                        representation["flow_type"] = "MEDIO"
                        representation["is_average"] = True
                    else:
                        try:
                            from api.core.utils.flow_display import get_interaction_flow_display_data
                            flow_data = get_interaction_flow_display_data(instance, cached_config=config)
                            representation["flow"] = flow_data["value"]
                            representation["flow_type"] = flow_data["type"]
                            representation["is_average"] = (flow_data["type"] != "INSTANTANEO")
                        except Exception:
                            pass
                else:
                    representation["total_diff"] = 0
                    representation["total_today_diff"] = 0
        except Exception:
            pass

        if not representation.get('n_voucher') or representation.get('n_voucher') == '':
            representation['n_voucher'] = '-'

        return representation


class InteractionDetailDgaXlsxSerializer(serializers.ModelSerializer):
    """
    Serializer específico para exportación Excel DGA.
    Solo expone los campos necesarios en el orden correcto para alinear con column_header.
    """
    class Meta:
        model = InteractionDetail
        fields = [
            'date_time_medition',
            'flow',
            'total',
            'water_table',
            'n_voucher',
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        # Asegurar que flow nunca sea None (mostrar 0.00 en vez de vacío)
        if representation.get('flow') is None:
            representation['flow'] = 0.0

        # Formatear comprobante: '-' si no tiene voucher
        n_voucher = representation.get('n_voucher')
        if not n_voucher or n_voucher == '':
            representation['n_voucher'] = '-'

        return representation


class InteractionDetailModelSerializerNoProcessing(serializers.ModelSerializer):
    class Meta:
        model = InteractionDetail
        fields = "__all__"

    def to_representation(self, instance):
        if 'request_cache' not in self.context:
            self.context['request_cache'] = {
                'points_config': {},
                'daily_data': {},
                'prev_record_totals': {}
            }
        
        request_cache = self.context['request_cache']
        representation = super().to_representation(instance)
        catchment_point = instance.catchment_point
        cp_id = catchment_point.id

        if cp_id not in request_cache['points_config']:
            from api.core.models import DgaDataConfigCatchment
            has_avg_flow = Variable.objects.filter(type_variable="CAUDAL_PROMEDIO", scheme_catchment__points_catchment=catchment_point).exists()
            dga_config = DgaDataConfigCatchment.objects.filter(point_catchment=catchment_point).first()
            request_cache['points_config'][cp_id] = {'has_avg_flow': has_avg_flow, 'dga_config': dga_config, 'total_d6': 0}

        config = request_cache['points_config'][cp_id]

        try:
            if instance.date_time_medition:
                from django.utils import timezone
                record_dt = instance.date_time_medition
                record_date = timezone.localtime(record_dt).date()
                
                if 'prev_day_totals' not in request_cache:
                    request_cache['prev_day_totals'] = {} 
                if cp_id not in request_cache['daily_data']:
                    request_cache['daily_data'][cp_id] = {}
                    request_cache['prev_day_totals'][cp_id] = {}
                
                if record_date not in request_cache['daily_data'][cp_id]:
                    day_records = list(InteractionDetail.objects.filter(
                        catchment_point_id=cp_id,
                        date_time_medition__date=record_date
                    ).order_by('date_time_medition').only('id', 'total', 'date_time_medition', 'date_time_last_logger'))
                    
                    from datetime import timedelta
                    yesterday = record_date - timedelta(days=1)
                    if yesterday in request_cache['prev_day_totals'].get(cp_id, {}):
                        last_total_val = request_cache['prev_day_totals'][cp_id][yesterday]
                        yesterday_data = request_cache['daily_data'][cp_id].get(yesterday, {})
                        if yesterday_data:
                            last_id = list(yesterday_data.keys())[-1]
                            try:
                                last_rec = InteractionDetail.objects.only('date_time_medition').get(id=last_id)
                                last_date_val = last_rec.date_time_medition
                            except:
                                last_date_val = datetime.combine(yesterday, time(23, 59, 59)).replace(tzinfo=pytz.timezone("America/Santiago"))
                        else:
                            last_date_val = None
                    else:
                        prev_day_last = InteractionDetail.objects.filter(
                            catchment_point_id=cp_id,
                            date_time_medition__date__lt=record_date
                        ).exclude(total__in=[0, '0', None, '']).order_by('-date_time_medition').only('id', 'total', 'date_time_medition').first()
                        last_total_val = parse_total(prev_day_last.total) if prev_day_last else 0
                        last_date_val = prev_day_last.date_time_medition if prev_day_last else None

                    first_date_of_day_interval = last_date_val
                    batch_map = {}
                    running_today = 0
                    
                    view = self.context.get('view')
                    view_name = view.__class__.__name__ if view else ""
                    is_monthly_view = "Month" in view_name
                    
                    for idx, rec in enumerate(day_records):
                        curr_rec_total = parse_total(rec.total)
                        curr_date = rec.date_time_medition
                        dt = 0
                        is_duplicate_ts = False
                        if last_date_val and curr_date:
                            dt = (curr_date - last_date_val).total_seconds()
                            if dt <= 0: is_duplicate_ts = True
                            
                        if is_duplicate_ts:
                            diff = 0
                            calc_flow = 0.0
                            if idx > 0:
                                prev_rec = day_records[idx-1]
                                if prev_rec.id in batch_map:
                                    diff = batch_map[prev_rec.id]['total_diff']
                                    calc_flow = batch_map[prev_rec.id]['calc_flow']
                        else:
                            diff = curr_rec_total - last_total_val
                            if diff < 0: diff = curr_rec_total
                            diff = max(0, diff)
                            calc_flow = 0.0
                            if config.get('has_avg_flow') and dt > 0:
                                calc_flow = round((diff / dt) * 1000.0, 2)
                            running_today += diff
                        
                        batch_map[rec.id] = {'total_diff': diff, 'total_today_diff': running_today, 'calc_flow': calc_flow}
                        
                        if not is_duplicate_ts:
                            if curr_rec_total > 0 or last_total_val == 0:
                                last_total_val = curr_rec_total
                                last_date_val = curr_date

                    if is_monthly_view and day_records and config.get('has_avg_flow'):
                        last_rec = day_records[-1]
                        total_day_vol = running_today
                        total_day_seconds = (last_date_val - first_date_of_day_interval).total_seconds() if last_date_val and first_date_of_day_interval else 0
                        if total_day_seconds > 0:
                            daily_avg_flow = round((total_day_vol / total_day_seconds) * 1000.0, 2)
                            daily_avg_m3h = round(total_day_vol / (total_day_seconds / 3600.0), 2)
                            if last_rec.id in batch_map:
                                batch_map[last_rec.id]['calc_flow'] = daily_avg_flow
                                batch_map[last_rec.id]['total_diff'] = daily_avg_m3h
                        
                    request_cache['daily_data'][cp_id][record_date] = batch_map
                    request_cache['prev_day_totals'][cp_id][record_date] = last_total_val

                day_cache = request_cache['daily_data'][cp_id][record_date]
                if instance.id in day_cache:
                    res = day_cache[instance.id]
                    representation["total_diff"] = res['total_diff']
                    representation["total_today_diff"] = res['total_today_diff']
                    
                    # ✅ ENFORCE: If average flow is enabled, use the calculated value ALWAYS (even if 0)
                    # This ensures consistency: If total_diff (Consumption) is 0, Flow is 0.
                    if config.get('has_avg_flow'):
                        representation["flow"] = res.get('calc_flow', 0.0)
                        representation["flow_type"] = "MEDIO"
                        representation["is_average"] = True
                    else:
                        try:
                            from api.core.utils.flow_display import get_interaction_flow_display_data
                            flow_data = get_interaction_flow_display_data(instance, cached_config=config)
                            representation["flow"] = flow_data["value"]
                            representation["flow_type"] = flow_data["type"]
                            representation["is_average"] = (flow_data["type"] != "INSTANTANEO")
                        except Exception:
                            pass
                else:
                    representation["total_diff"] = 0
                    representation["total_today_diff"] = 0
        except Exception:
            pass

        if not representation.get('n_voucher') or representation.get('n_voucher') == '':
            representation['n_voucher'] = '-'

        return representation
