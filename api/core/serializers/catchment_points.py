from rest_framework import serializers
from django.utils import timezone
from api.core.models.catchment_points import (
    Client,
    ProjectCatchments,
    CatchmentPoint,
    ProfileIkoluCatchment,
    NotificationsCatchment,
    ResponseNotificationsCatchment,
    TypeFileCatchment,
    FileCatchment,
    ProfileDataConfigCatchment,
    DgaDataConfigCatchment,
    SchemesCatchment,
    Variable,
    RegisterPersons
)
from api.core.models.interaction_detail import InteractionDetail
from api.core.models.telemetry_providers import TelemetryProvider
from datetime import datetime, timedelta
import pytz
from .interaction_detail import InteractionDetailModelSerializerNoProcessing, InteractionDetailModelSerializer
from django.db.models import Case, When, IntegerField, Sum


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__'


class ProjectCatchmentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectCatchments
        fields = '__all__'


class ProjectMiniSerializer(serializers.ModelSerializer):
    """Serializer ligero para proyectos dentro del árbol de clientes."""
    class Meta:
        model = ProjectCatchments
        fields = ['id', 'name', 'code_internal', 'client']


class ClientWithProjectsSerializer(serializers.ModelSerializer):
    """Serializer que anida los proyectos dentro de cada cliente."""
    projects = ProjectMiniSerializer(source='projectcatchments_set', many=True)

    class Meta:
        model = Client
        fields = ['id', 'name', 'rut', 'address', 'phone', 'email', 'projects']


class CatchmentPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatchmentPoint
        fields = '__all__'


class ProfileIkoluCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileIkoluCatchment
        fields = '__all__'


class NotificationsCatchmentSerializer(serializers.ModelSerializer):
    emails = serializers.ListField(
        child=serializers.EmailField(),
        allow_empty=True,
        required=False,
        help_text="Lista de emails destinatarios. Ej: ['correo1@x.com', 'correo2@x.com']"
    )

    class Meta:
        model = NotificationsCatchment
        fields = '__all__'


class NotificationsCatchmentDetailSerializer(serializers.ModelSerializer):
    """
    Serializer extendido para retrieve (GET /api/notifications/{id}/).
    Incluye objeto 'stats' con métricas analíticas de la alerta.
    """
    emails = serializers.ListField(
        child=serializers.EmailField(),
        allow_empty=True,
        required=False,
        help_text="Lista de emails destinatarios. Ej: ['correo1@x.com', 'correo2@x.com']"
    )
    stats = serializers.SerializerMethodField()

    class Meta:
        model = NotificationsCatchment
        fields = '__all__'

    def get_stats(self, obj):
        """
        Calcular estadísticas analíticas de la alerta umbral.
        Basado en las ResponseNotificationsCatchment asociadas (disparos históricos).
        Incluye historial de mediciones de telemetría asociadas a cada disparo.
        """
        responses = obj.responses.all().order_by('created')
        total = responses.count()

        if total == 0:
            return {
                'total_triggers': 0,
                'first_trigger': None,
                'last_trigger': None,
                'triggers_last_24h': 0,
                'triggers_last_7d': 0,
                'triggers_last_30d': 0,
                'active_days': 0,
                'avg_hours_between_triggers': None,
                'peak_hour': None,
                'trigger_history': [],
            }

        chile = pytz.timezone('America/Santiago')
        now = timezone.now().astimezone(chile)
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)

        first = responses.first()
        last = responses.last()

        # Conteos por período
        triggers_24h = responses.filter(created__gte=last_24h).count()
        triggers_7d = responses.filter(created__gte=last_7d).count()
        triggers_30d = responses.filter(created__gte=last_30d).count()

        # Días distintos con disparos
        active_days = responses.datetimes('created', 'day', order='ASC').distinct().count()

        # Promedio de horas entre disparos consecutivos
        avg_hours = None
        if total >= 2:
            deltas = []
            prev = None
            for r in responses:
                if prev:
                    delta = (r.created - prev.created).total_seconds() / 3600
                    deltas.append(delta)
                prev = r
            if deltas:
                avg_hours = round(sum(deltas) / len(deltas), 2)

        # Hora pico (hora del día con más disparos)
        peak_hour = None
        from django.db.models.functions import ExtractHour
        from django.db.models import Count
        hour_counts = (
            obj.responses.annotate(hour=ExtractHour('created'))
            .values('hour')
            .annotate(count=Count('id'))
            .order_by('-count')
            .first()
        )
        if hour_counts:
            peak_hour = {
                'hour': hour_counts['hour'],
                'count': hour_counts['count'],
            }

        # Extraer valor medido del último disparo (parsear texto de response)
        last_value = None
        if last and last.response:
            import re
            match = re.search(r'Valor medido:\s*([0-9.]+)', last.response)
            if match:
                last_value = float(match.group(1))

        # ============================================================
        # HISTORIAL DE MEDICIONES (últimos 30 días):
        # Para cada disparo reciente, buscar el InteractionDetail más
        # cercano en tiempo para mostrar la línea completa de telemetría
        # ============================================================
        trigger_history = []
        history_limit_days = 30
        history_cutoff = now - timedelta(days=history_limit_days)

        recent_responses = list(responses.filter(created__gte=history_cutoff)[:50])

        if obj.point_catchment and recent_responses:
            first_recent = recent_responses[0]
            last_recent = recent_responses[-1]

            # Ventana de búsqueda: 2 horas antes del primer disparo reciente
            search_start = first_recent.created - timedelta(hours=2)
            search_end = last_recent.created + timedelta(hours=1)

            interactions = list(
                InteractionDetail.objects.filter(
                    catchment_point=obj.point_catchment,
                    date_time_medition__gte=search_start,
                    date_time_medition__lte=search_end,
                ).order_by('date_time_medition').values(
                    'id', 'date_time_medition', 'date_time_last_logger',
                    'nivel', 'flow', 'total', 'pulses', 'total_diff',
                    'total_today_diff', 'days_not_conection', 'is_error',
                    'created'
                )
            )

            import re
            for resp in recent_responses:
                # Extraer valor medido del texto de la respuesta
                measured_value = None
                if resp.response:
                    match = re.search(r'Valor medido:\s*([0-9.]+)', resp.response)
                    if match:
                        measured_value = float(match.group(1))

                # Buscar el InteractionDetail más cercano en tiempo
                closest = None
                closest_diff = None
                for interaction in interactions:
                    dt = interaction.get('date_time_medition')
                    if dt:
                        diff = abs((dt - resp.created).total_seconds())
                        if closest_diff is None or diff < closest_diff:
                            closest_diff = diff
                            closest = interaction

                trigger_history.append({
                    'triggered_at': resp.created.isoformat(),
                    'response_text': resp.response,
                    'measured_value': measured_value,
                    'matched_interaction': closest,
                })

        return {
            'total_triggers': total,
            'first_trigger': first.created.isoformat() if first else None,
            'last_trigger': last.created.isoformat() if last else None,
            'triggers_last_24h': triggers_24h,
            'triggers_last_7d': triggers_7d,
            'triggers_last_30d': triggers_30d,
            'active_days': active_days,
            'avg_hours_between_triggers': avg_hours,
            'peak_hour': peak_hour,
            'last_measured_value': last_value,
            'history_limit_days': history_limit_days,
            'history_limit_records': 50,
            'trigger_history': trigger_history,
        }


class ResponseDepthNotificationsCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResponseNotificationsCatchment
        fields = '__all__'
        depth=1

class ResponseNotificationsCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResponseNotificationsCatchment
        fields = '__all__'


class TypeFileCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeFileCatchment
        fields = '__all__'


class FileCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileCatchment
        fields = '__all__'


class ProfileDataConfigCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileDataConfigCatchment
        fields = '__all__'


class DgaCronSerializer(serializers.ModelSerializer):
    class Meta:
        model = DgaDataConfigCatchment
        fields = ('send_dga', 'standard', 'type_dga', 'code_dga', 'flow_granted_dga',
                  'total_granted_dga', 'shac', 'date_start_compliance', 'date_created_code',)


class TelemetryProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelemetryProvider
        fields = (
            'id', 'name', 'handler_name', 'protocol', 'base_url', 'endpoint_template',
            'auth_type', 'auth_username', 'auth_password', 'auth_token', 'auth_header_name',
            'parser_config', 'timeout_seconds', 'retry_attempts', 'is_active',
        )


class VariableCronSerializer(serializers.ModelSerializer):
    provider = TelemetryProviderSerializer(read_only=True)

    class Meta:
        model = Variable
        fields = ('id', 'str_variable', 'type_variable', 'token_service', 'service',
                  'pulses_factor', 'convert_to_lt', 'calculate_nivel', 'store_average_flow',
                  'min_value', 'max_value', 'display_key', 'provider',)


class SchemesCatchmentCronSerializer(serializers.ModelSerializer):
    """
    Serializer for SchemesCatchment with variables.
    """
    variables = serializers.SerializerMethodField()

    def get_variables(self, obj):
        """
        Retrieve and serialize variables for the given scheme catchment.
        """
        get_data = Variable.objects.filter(
            scheme_catchment=obj).select_related('provider').order_by(
            Case(
                When(type_variable='TOTALIZADO', then=0),
                When(token_service__isnull=True, then=2),
                default=1,
                output_field=IntegerField()
            ),
            'type_variable',
            'token_service'
        )
        return VariableCronSerializer(get_data, many=True).data

    class Meta:
        model = SchemesCatchment
        fields = ('name', 'variables')


class ProfileDataConfigCatchmentRetrieveCronSerializer(serializers.ModelSerializer):
    scheme = serializers.SerializerMethodField('get_scheme')

    def get_scheme(self, obj):
        get_data = SchemesCatchment.objects.filter(
            points_catchment=obj.point_catchment).first()
        return SchemesCatchmentCronSerializer(get_data).data

    class Meta:
        model = ProfileDataConfigCatchment
        fields = ('token_service', 'd3', 'nivel_offset', 'replicate_on_missing', 'use_transaction_atomic', 'scheme',)


class DgaDataConfigCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DgaDataConfigCatchment
        fields = '__all__'


class SchemesCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchemesCatchment
        fields = '__all__'


class VariableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variable
        fields = '__all__'


class RegisterPersonsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegisterPersons
        fields = '__all__'


class CatchmentPointSerializerDetailCron(serializers.ModelSerializer):
    profile_data_config = serializers.SerializerMethodField(
        'get_profile_data_config')

    project_info = serializers.SerializerMethodField()

    def get_project_info(self, obj):
        try:
            if obj.project and obj.project.client:
                return {
                    'project_name': obj.project.name,
                    'client_name': obj.project.client.name
                }
        except:
            pass
        return {'project_name': 'N/A', 'client_name': 'N/A'}

    def get_profile_data_config(self, obj):
        get_data = ProfileDataConfigCatchment.objects.filter(
            point_catchment=obj).first()
        return ProfileDataConfigCatchmentRetrieveCronSerializer(get_data).data

    class Meta:
        model = CatchmentPoint
        fields = ('id', 'title', 'frecuency',
                  'profile_data_config', 'project_info')


class ProfileIkoluCatchmentRetrieveSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileIkoluCatchment
        fields = ('entry_by_form', 'm1', 'm2', 'm3', 'm4', 'm5', 'm6')


class VariableConfigSerializer(serializers.ModelSerializer):
    """
    Serializer para mostrar la configuración de variables en config_data.
    Incluye información de escala, factores de conversión, etc.
    """
    class Meta:
        model = Variable
        fields = (
            'id', 'str_variable', 'label', 'type_variable', 'service',
            'pulses_factor', 'convert_to_lt', 'calculate_nivel',
            'token_service'
        )


class DataConfigUserSerializer(serializers.ModelSerializer):
    variables = serializers.SerializerMethodField('get_variables')

    def get_variables(self, obj):
        """
        Obtener las variables configuradas para el punto de captación.
        Las variables están asociadas al esquema (SchemesCatchment) del punto.
        ✅ MEJORADO: Usar datos prefetcheados si están disponibles para mejorar rendimiento.
        """
        if not obj or not obj.point_catchment:
            return []
        
        # ✅ Optimización: Intentar usar datos prefetcheados primero
        scheme = None
        prefetch_schemes_exists = False
        if hasattr(obj.point_catchment, '_prefetched_objects_cache') and 'schemes' in obj.point_catchment._prefetched_objects_cache:
            prefetch_schemes_exists = True
            schemes = obj.point_catchment._prefetched_objects_cache['schemes']
            if schemes:
                scheme = schemes[0]  # Tomar el primer esquema
        
        # ✅ CORREGIDO: Solo consultar BD si el prefetch NO existe
        # Si el prefetch existe pero está vacío, significa que ya se consultó y no hay schemes
        if not scheme and not prefetch_schemes_exists:
            scheme = SchemesCatchment.objects.filter(
                points_catchment=obj.point_catchment
            ).first()
        
        if not scheme:
            return []
        
        # ✅ Optimización: Usar variables prefetcheadas si están disponibles
        variables = None
        prefetch_variables_exists = False
        if hasattr(scheme, '_prefetched_objects_cache') and 'variables' in scheme._prefetched_objects_cache:
            prefetch_variables_exists = True
            variables = scheme._prefetched_objects_cache['variables']  # ✅ FIX: Cambiar variable_set por variables (related_name correcto)
            # ✅ CORREGIDO: Si el prefetch existe pero está vacío, retornar lista vacía sin consultar BD
            if not variables:
                return []
            # Ordenar en memoria si tenemos los datos prefetcheados
            from operator import attrgetter
            variables = sorted(
                variables,
                key=lambda v: (
                    0 if v.type_variable == 'TOTALIZADO' else (2 if v.token_service is None else 1),
                    v.type_variable or '',
                    v.token_service or ''
                )
            )
        else:
            # ✅ CORREGIDO: Solo consultar BD si el prefetch NO existe
            # Fallback: consulta directa con ordenamiento en BD
            variables = Variable.objects.filter(
                scheme_catchment=scheme
            ).order_by(
                Case(
                    When(type_variable='TOTALIZADO', then=0),
                    When(token_service__isnull=True, then=2),
                    default=1,
                    output_field=IntegerField()
                ),
                'type_variable',
                'token_service'
            )
        
        return VariableConfigSerializer(variables, many=True).data

    class Meta:
        model = ProfileDataConfigCatchment
        fields = ('d1', 'd2', 'd3', 'd4', 'd5','d6', 'addition',
                  'date_start_telemetry', 'date_delivery_act','is_telemetry',
                  'variables')


class InteractionDetailModuleSerializer(serializers.ModelSerializer):
    date_time_medition = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = InteractionDetail
        fields = ('date_time_medition', 'date_time_last_logger', 'flow', 'total', 'total_diff', 'total_today_diff',
                  'nivel', 'water_table', 'send_dga', 'return_dga', 'n_voucher')


class TypeFileCatchmentDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeFileCatchment
        fields = ('name',)


class FileCatchmentDetailSerializer(serializers.ModelSerializer):
    created = serializers.DateTimeField(format="%Y-%d-%m %H:%M")
    modified = serializers.DateTimeField(format="%Y-%d-%m %H:%M")
    type_file = serializers.SerializerMethodField('get_type_file')

    def get_type_file(self, obj):
        get_data = TypeFileCatchment.objects.filter(
            id=obj.type_file.id).first()
        return TypeFileCatchmentDetailSerializer(get_data).data

    class Meta:
        model = FileCatchment
        fields = ('id', 'file', 'name', 'description',
                  'type_file', 'created', 'modified')


class CatchmentPointIkoluSerializer(serializers.ModelSerializer):
    profile_ikolu = serializers.SerializerMethodField(
        'get_profile_ikolu')
    config_data = serializers.SerializerMethodField(
        'get_config_data')
    dga = serializers.SerializerMethodField(
        'get_dga')
    modules = serializers.SerializerMethodField('get_modules')

    def get_modules(self, obj):
        """
        Retrieve the latest InteractionDetail for the given catchment point.
        ✅ Optimización: Usar select_related y optimizar consultas para reducir tiempo de carga.
        ✅ MEJORADO: Eliminado límite de 50 registros para devolver todos los registros del día completo.
        ✅ MEJORADO: Optimizado con prefetch_related para evitar N+1 queries en serialización.
        """
        today = timezone.localtime(timezone.now()).date()
        yesterday = today - timedelta(days=1)
        
        
        # ✅ BATCH FETCHING CONSUMPTION
        batch_data = self.context.get('batch_data', {})
        
        # Si tenemos datos en batch, usamos la memoria (RÁPIDO)
        if batch_data and obj.id in batch_data.get('latest_records', {}):
            # 1. Latest Record
            get_data_m1 = batch_data['latest_records'].get(obj.id)
            
            # 2. Today Records (already ordered)
            today_list = batch_data.get('today_records', {}).get(obj.id, [])
            # today_list está ordenado por date_time_medition ASC (desde users.py)
            # pero aquí el código original espera DESC o manipulación específica.
            # En users.py hice: order_by('date_time_medition') -> ASC
            # Ajustemos para mantener lógica:
            # - get_data_m3 (today sorted DESC for display/list)
            today_list_desc = list(reversed(today_list))
            get_data_m3 = today_list_desc
            
            first_data_today = today_list[0] if today_list else None # oldest of today
            
            # 3. Yesterday Records
            yesterday_list = batch_data.get('yesterday_records', {}).get(obj.id, [])
            yesterday_list_desc = list(reversed(yesterday_list))
            
            last_data_yesterday = yesterday_list[-1] if yesterday_list else None # newest of yesterday
            get_data_m4 = yesterday_list_desc
            
            # 4. DGA (Filtered in memory)
            dga_list = batch_data.get('dga_records', {}).get(obj.id, [])
            # dga_list viene user-side order_by('-date_time_medition') -> DESC
            
            get_data_m2 = dga_list[:48] # Last 48 total
            
            # DGA Today (Last 24 of today)
            # Filtramos en memoria
            get_data_m22 = [r for r in dga_list if r.date_time_medition.date() >= today][:24]
            
            # 5. Files & Alerts
            get_files = batch_data.get('files', {}).get(obj.id, [])
            get_alerts = batch_data.get('alerts', {}).get(obj.id, [])

        else:
            # Fallback a lógica original (LENTO - N+1 Queries)
            # ... (código original que ya estaba) ...
            
            # ✅ Optimización: Usar select_related para evitar N+1 queries en relaciones
            # ✅ MEJORADO: Prefetch relacionado para optimizar serialización masiva
            # ✅ Usar only() para limitar campos cuando sea posible (reduce transferencia de datos)
            base_qs = InteractionDetail.objects.filter(
                catchment_point=obj.id
            ).select_related('catchment_point')
            
            # ✅ Optimización: Prefetch para optimizar serialización cuando hay muchos registros
            from django.db.models import Prefetch
            from django.db.models import Prefetch
            # from api.core.models import ProfileDataConfigCatchment, SchemesCatchment, Variable
            
            base_qs = base_qs.prefetch_related(
                Prefetch(
                    'catchment_point__data_config_profiles',
                    queryset=ProfileDataConfigCatchment.objects.only('point_catchment_id', 'd6')
                ),
                Prefetch(
                    'catchment_point__schemes',
                    queryset=SchemesCatchment.objects.prefetch_related(
                        Prefetch(
                            'variables',
                            queryset=Variable.objects.only('id', 'type_variable', 'scheme_catchment_id')
                        )
                    )
                )
            )
            
            # Último registro general
            get_data_m1 = base_qs.order_by('-date_time_medition', '-id').first()

            # Datos DGA (últimos 48 registros)
            get_data_m2 = base_qs.filter(
                return_dga__isnull=False,
            ).order_by('-date_time_medition').distinct('date_time_medition')[:48]

            # Datos DGA de hoy (últimos 24 registros)
            get_data_m22 = base_qs.filter(
                return_dga__isnull=False,
                date_time_medition__gte=today,
            ).order_by('-date_time_medition').distinct('date_time_medition')[:24]

            # Datos de ayer
            yesterday_qs = base_qs.filter(
                date_time_medition__gte=yesterday,
                date_time_medition__lt=today,
            ).order_by('-date_time_medition')
            
            last_data_yesterday = yesterday_qs.first()
            # first_data_yesterday = yesterday_qs.last() # Unused effectively in consumption calc below?
            get_data_m4 = yesterday_qs.distinct('date_time_medition')

            # Datos de hoy
            today_qs = base_qs.filter(
                date_time_medition__gte=today,
            ).order_by('-date_time_medition')
            
            first_data_today = today_qs.last()
            get_data_m3 = today_qs.distinct('date_time_medition')

            # Files & Alerts
            get_files = FileCatchment.objects.filter(
                point_catchment=obj.id
            ).select_related('point_catchment').all()
            
            get_alerts = NotificationsCatchment.objects.filter(
                point_catchment=obj.id, type_notification='ALERT'
            ).all()


            get_alerts = NotificationsCatchment.objects.filter(
                point_catchment=obj.id, type_notification='ALERT'
            ).all()

        # --- GET TOTAL CONSTANT (d6 + addition) ---
        total_constant = 0
        if hasattr(obj, '_prefetched_objects_cache') and 'data_config_profiles' in obj._prefetched_objects_cache:
            profiles = obj._prefetched_objects_cache['data_config_profiles']
            for p in profiles:
                 if p.d6 is not None: total_constant += int(p.d6)
                 if p.addition is not None: total_constant += int(p.addition)
        else:
            # Fallback if not prefetched - Sum is imported at module level
            aggr = ProfileDataConfigCatchment.objects.filter(point_catchment=obj).aggregate(
                d6_sum=Sum("d6"), 
                add_sum=Sum("addition")
            )
            total_constant = (aggr['d6_sum'] or 0) + (aggr['add_sum'] or 0)

        # --- CÁLCULO DE CONSUMOS (Común) ---
        
        total_consumed_yesterday = None
        if last_data_yesterday:
            try:
                if last_data_yesterday.total:
                    total_consumed_yesterday = int(last_data_yesterday.total_today_diff) 
                else:
                    total_consumed_yesterday = 0
            except ValueError:
                total_consumed_yesterday = 0

        total_consumed_today = None
        # Para cálculo de consumo hoy necesitamos último y primero del día
        # get_data_m3 es lista de registros del día. Si viene de Batch (lista) o Queryset.
        # En lógica batch get_data_m3 es DESC (reversed today_list).
        # last_data_today (mas reciente) -> index 0 de lista DESC
        # first_data_today (mas antiguo) -> calculado antes.
        
        # Unificamos acceso a last_data_today
        last_data_today = None
        # Convertir queryset a lista si es necesario para indexar
        get_data_m3_list = list(get_data_m3) if get_data_m3 is not None else []
        
        if first_data_today and get_data_m3_list:
            try:
                last_data_today = get_data_m3_list[0] # El más reciente (DESC)

                if last_data_today.total is not None and first_data_today.total is not None:
                    # Casteos seguros
                    t_last = float(last_data_today.total)
                    t_first = float(first_data_today.total)
                    total_consumed_today = int(t_last) - int(t_first)
                else:
                    total_consumed_today = 0
            except (ValueError, TypeError, IndexError, AttributeError):
                total_consumed_today = 0


        # --- CHECK HAS AVG FLOW ---
        has_avg_flow = False
        if hasattr(obj, '_prefetched_objects_cache') and 'schemes' in obj._prefetched_objects_cache:
            schemes = obj._prefetched_objects_cache['schemes']
            if schemes:
                scheme = schemes[0]
                has_avg_flow = any(v.type_variable == 'CAUDAL_PROMEDIO' for v in scheme.variables.all())
        else:
             has_avg_flow = Variable.objects.filter(type_variable="CAUDAL_PROMEDIO", scheme_catchment__points_catchment=obj).exists()

        # Prepare light serialization for heavy lists
        m2_data = self._serialize_light(get_data_m2, is_dga=True, constant=total_constant, has_avg_flow=has_avg_flow)
        m22_data = self._serialize_light(get_data_m22, is_dga=True, constant=total_constant, has_avg_flow=has_avg_flow)
        # get_data_m3_list comes reversed (DESC) from batch logic or query
        # We need to maintain that order
        today_data = self._serialize_light(get_data_m3_list, constant=total_constant, has_avg_flow=has_avg_flow)
        yesterday_data = self._serialize_light(get_data_m4, constant=total_constant, has_avg_flow=has_avg_flow)
        
        modules = {
            "m1": InteractionDetailModelSerializer(get_data_m1).data if get_data_m1 else None, # Handle None
            "m2": m2_data,
            "m22": m22_data,
            "first_data_today": InteractionDetailModelSerializer(
                first_data_today, many=False
            ).data if first_data_today else None,
            "first_actual_year": self._get_first_data_year(obj),
            "today": today_data,
            "yesterday": yesterday_data,
            "last_data_yesterday": InteractionDetailModelSerializer(
                last_data_yesterday, many=False
            ).data if last_data_yesterday else None,
            "total_consumed_yesterday": InteractionDetail.objects.filter(
                catchment_point=obj.id,
                date_time_medition__date=yesterday
            ).aggregate(sum_diff=Sum('total_diff'))['sum_diff'] or 0,
            "total_consumed_today": InteractionDetail.objects.filter(
                catchment_point=obj.id,
                date_time_medition__date=today
            ).aggregate(sum_diff=Sum('total_diff'))['sum_diff'] or 0,
            "total_consumed_year": InteractionDetail.objects.filter(
                catchment_point=obj.id,
                date_time_medition__year=today.year
            ).aggregate(sum_diff=Sum('total_diff'))['sum_diff'] or 0,
            "files": FileCatchmentDetailSerializer(get_files, many=True).data,
            "alerts": NotificationsCatchmentDetailSerializer(
                get_alerts,
                many=True
            ).data

        }

        return modules

    def _serialize_light(self, records, is_dga=False, constant=0, has_avg_flow=False):
        """
        Hyper-fast serialization bypassing DRF overhead for large lists.
        Matches strict format expected by frontend: "%Y-%d-%m %H:%M"
        Addeed has_avg_flow support.
        """
        if not records:
            return []
            
        data = []
        # Pre-resolve attribute names to avoid repeat lookups in loop
        fmt = "%Y-%m-%d %H:%M:%S"
        
        # Convert to list if it's a queryset to allow indexing
        record_list = list(records)
        len_records = len(record_list)

        for i, r in enumerate(record_list):
            # Safe attribute access with defaults - CONVERTING TO LOCAL TIME
            dt_med = timezone.localtime(r.date_time_medition).strftime(fmt) if r.date_time_medition else None
            dt_last = timezone.localtime(r.date_time_last_logger).strftime(fmt) if r.date_time_last_logger else None
            
            # --- Parse Total safetly ---
            final_total = 0
            if r.total:
                try:
                    clean_val = str(r.total).replace('.', '')
                    if ',' in clean_val:
                        clean_val = clean_val.replace(',', '.')
                    final_total = int(float(clean_val))
                except (ValueError, TypeError):
                    final_total = 0
            
            # Add constant
            final_total += int(constant)

            # --- CALCULATE AVG FLOW IF NEEDED ---
            # records are usually DESC (newest first).
            # To calc flow for current record (i), we need previous record (older).
            # If sorted DESC, older record is i + 1.
            flow_val = r.flow
            
            if has_avg_flow:
                # Default to 0 if we can't calculate
                flow_val = 0.0
                
                # CONSTANTES DE PROTECCIÓN
                MAX_FLOW_LS = 150.0
                MAX_TIME_GAP_SECONDS = 2 * 3600  # 2 horas
                MAX_DIFF_M3_PER_HOUR = 500
                
                # We need the 'next' item in the list (which is chronologically previous)
                if i + 1 < len_records:
                    prev_r = record_list[i+1]
                    
                    # Compute Deltas
                    if r.date_time_medition and prev_r.date_time_medition:
                        dt_seconds = (r.date_time_medition - prev_r.date_time_medition).total_seconds()
                        
                        # VALIDACIÓN 1: Gap de tiempo muy grande (reconexión)
                        if dt_seconds > MAX_TIME_GAP_SECONDS:
                            flow_val = 0.0  # No calcular
                        elif dt_seconds > 0:
                            # Parse prev total
                            prev_total = 0
                            if prev_r.total:
                                try:
                                    clean_prev = str(prev_r.total).replace('.', '')
                                    if ',' in clean_prev: clean_prev = clean_prev.replace(',', '.')
                                    prev_total = int(float(clean_prev))
                                except: pass
                            prev_total += int(constant)
                            
                            diff = final_total - prev_total
                            
                            # Handle negative diff (although reset logic should prevent this on Total, local noise might exist)
                            if diff < 0: diff = 0
                            
                            # VALIDACIÓN 2: Consumo por hora excesivo
                            consumption_per_hour = (diff / dt_seconds) * 3600
                            if consumption_per_hour > MAX_DIFF_M3_PER_HOUR:
                                flow_val = 0.0  # Consumo absurdo
                            else:
                                calc_flow = round((diff / dt_seconds) * 1000.0, 2)
                                
                                # VALIDACIÓN 3: Caudal máximo razonable
                                if calc_flow > MAX_FLOW_LS:
                                    flow_val = 0.0
                                else:
                                    flow_val = calc_flow
                else:
                     # Boundary condition (oldest record in list).
                     # We can't calculate flow without fetching one more record from DB.
                     # For the sake of "light" serialization, we accept 0 or check if r.flow has something?
                     # r.flow might be 0.
                     pass
            
            item = {
                'date_time_medition': dt_med,
                'date_time_last_logger': dt_last,
                'flow': flow_val,
                'total': final_total,
                'total_diff': r.total_diff,
                'total_today_diff': r.total_today_diff,
                'nivel': r.nivel,
                'water_table': r.water_table,
                'send_dga': r.send_dga,
                'return_dga': r.return_dga,
                'n_voucher': r.n_voucher or '-', # Match serializer logic
            }
            data.append(item)
            
        return data

    def _get_first_data_year(self, obj):
        """
        Obtener el primer registro del año actual.
        Optimización: Usar __gte en lugar de __year para aprovechar el índice.
        """
        from django.utils import timezone
        
        now = timezone.now()
        start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Usamos gte para que Postgres use el índice (catchment_point, date_time_medition)
        first_data_year = InteractionDetail.objects.filter(
            catchment_point=obj.id,
            date_time_medition__gte=start_of_year,
        ).exclude(date_time_medition__isnull=True).order_by('date_time_medition', 'id').first()
        
        
        if not first_data_year:
            # Fallback histórico (solo si no hay data este año)
            first_data_year = InteractionDetail.objects.filter(
                catchment_point=obj.id,
            ).exclude(date_time_medition__isnull=True).order_by('date_time_medition', 'id').first()
        
        return InteractionDetailModelSerializer(first_data_year, many=False).data if first_data_year else None

    def get_dga(self, obj):
        """
        ✅ MEJORADO: Usar datos prefetcheados si están disponibles para mejorar rendimiento.
        ✅ CORREGIDO: Distinguir entre prefetch vacío (ya consultado) y prefetch inexistente.
        """
        # ✅ Optimización: Usar datos prefetcheados si están disponibles
        if hasattr(obj, '_prefetched_objects_cache') and 'dga_data_config_profiles' in obj._prefetched_objects_cache:
            get_data = obj._prefetched_objects_cache['dga_data_config_profiles']
            # ✅ CORREGIDO: Si el prefetch existe (incluso si está vacío), no consultar de nuevo
            # Una lista vacía significa que ya se consultó y no hay objetos relacionados
            if get_data:
                return DgaCronSerializer(get_data[0]).data
            else:
                # Prefetch existe pero está vacío = ya consultado, no hay datos
                return {}
        # Fallback: consulta directa solo si NO hay prefetch en cache
        get_data = DgaDataConfigCatchment.objects.filter(
            point_catchment=obj).first()
        return DgaCronSerializer(get_data).data if get_data else {}

    def get_config_data(self, obj):
        """
        ✅ MEJORADO: Usar datos prefetcheados si están disponibles para mejorar rendimiento.
        ✅ CORREGIDO: Distinguir entre prefetch vacío (ya consultado) y prefetch inexistente.
        """
        # ✅ Optimización: Usar datos prefetcheados si están disponibles
        if hasattr(obj, '_prefetched_objects_cache') and 'data_config_profiles' in obj._prefetched_objects_cache:
            get_data = obj._prefetched_objects_cache['data_config_profiles']
            # ✅ CORREGIDO: Si el prefetch existe (incluso si está vacío), no consultar de nuevo
            # Una lista vacía significa que ya se consultó y no hay objetos relacionados
            if get_data:
                return DataConfigUserSerializer(get_data[0]).data
            else:
                # Prefetch existe pero está vacío = ya consultado, no hay datos
                return {}
        # Fallback: consulta directa solo si NO hay prefetch en cache
        get_data = ProfileDataConfigCatchment.objects.filter(
            point_catchment=obj).first()
        return DataConfigUserSerializer(get_data).data if get_data else {}

    def get_profile_ikolu(self, obj):
        """
        ✅ MEJORADO: Usar datos prefetcheados si están disponibles para mejorar rendimiento.
        ✅ CORREGIDO: Distinguir entre prefetch vacío (ya consultado) y prefetch inexistente.
        """
        # ✅ Optimización: Usar datos prefetcheados si están disponibles
        if hasattr(obj, '_prefetched_objects_cache') and 'ikolu_profiles' in obj._prefetched_objects_cache:
            get_data = obj._prefetched_objects_cache['ikolu_profiles']
            # ✅ CORREGIDO: Si el prefetch existe (incluso si está vacío), no consultar de nuevo
            # Una lista vacía significa que ya se consultó y no hay objetos relacionados
            if get_data:
                return ProfileIkoluCatchmentRetrieveSerializer(get_data[0]).data
            else:
                # Prefetch existe pero está vacío = ya consultado, no hay datos
                return {}
        # Fallback: consulta directa solo si NO hay prefetch en cache
        get_data = ProfileIkoluCatchment.objects.filter(
            point_catchment=obj).first()
        return ProfileIkoluCatchmentRetrieveSerializer(get_data).data if get_data else {}

    class Meta:
        model = CatchmentPoint
        fields = ('id', 'title','frecuency',
                  'profile_ikolu', 'config_data', 'dga', 'modules', 'lat','lon')
