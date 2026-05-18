import logging
from rest_framework.viewsets import ReadOnlyModelViewSet
from drf_excel.mixins import XLSXFileMixin
from drf_excel.renderers import XLSXRenderer
from rest_framework.renderers import JSONRenderer

from api.core.serializers import InteractionDetailModelSerializer, InteractionDetailModelSerializerNoProcessing
from api.core.models import InteractionDetail, CatchmentPoint
import django.db.models as models
from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated
)
from rest_framework.pagination import PageNumberPagination

logger = logging.getLogger(__name__)


class InteractionDetailViewSet(mixins.CreateModelMixin,
                               mixins.RetrieveModelMixin,
                               mixins.UpdateModelMixin,
                               mixins.ListModelMixin,
                               mixins.DestroyModelMixin,
                               viewsets.GenericViewSet):

    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    ordering = ('-date_time_medition', )
    # ✅ MEJORADO: Optimización con select_related y prefetch_related para mejorar rendimiento
    queryset = InteractionDetail.objects.select_related('catchment_point').order_by('-date_time_medition')
    serializer_class = InteractionDetailModelSerializer
    lookup_field = "id"
    
    def get_queryset(self):
        """
        ✅ MEJORADO: Optimización adicional con prefetch_related para evitar N+1 queries.
        """
        queryset = super().get_queryset()
        # ✅ Optimización: Prefetch para ProfileDataConfigCatchment y Schemes
        from django.db.models import Prefetch
        from api.core.models import ProfileDataConfigCatchment, SchemesCatchment, Variable
        
        queryset = queryset.prefetch_related(
            Prefetch(
                'catchment_point__data_config_profiles',
                queryset=ProfileDataConfigCatchment.objects.only('point_catchment_id', 'd6')
            ),
            Prefetch(
                'catchment_point__schemes',
                queryset=SchemesCatchment.objects.prefetch_related(
                    Prefetch(
                        'variables',  # ✅ FIX: Cambiar variable_set por variables (related_name correcto)
                        queryset=Variable.objects.only('id', 'type_variable', 'scheme_catchment_id')
                    )
                )
            )
        )
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # ✅ Optimización para grandes volúmenes de datos
        # Si NO se especifica un filtro de fecha, filtrar a las últimas 24h por defecto
        # para evitar traer cientos de miles de registros y mantener paginación funcional.
        date_param_keys = ['date_time_medition', 'hour', 'year', 'month', 'day', 'daily']
        has_date_filter = any(
            key.startswith('date_time_medition') or key in date_param_keys
            for key in request.query_params.keys()
        )

        if not has_date_filter:
            from django.utils import timezone
            from datetime import timedelta
            cutoff = timezone.now() - timedelta(hours=24)
            queryset = queryset.filter(date_time_medition__gte=cutoff)

        # ✅ Limit for high frequency points (1 or 5 min): filter to last 12h
        point_id = request.query_params.get('catchment_point')
        if point_id:
            try:
                point = CatchmentPoint.objects.only('frecuency').get(id=point_id)
                if point.frecuency in ['1', '5']:
                    from django.utils import timezone
                    from datetime import timedelta
                    cutoff = timezone.now() - timedelta(hours=12)
                    queryset = queryset.filter(date_time_medition__gte=cutoff)
            except Exception:
                pass

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    class InteractionFilter(filters.FilterSet):
        # Explicitly define hour to support ?hour=X mapping to date_time_medition__hour
        hour = filters.NumberFilter(field_name='date_time_medition', lookup_expr='hour')

        class Meta:
            model = InteractionDetail
            fields = {
                'catchment_point': ['exact'],
                'send_dga': ['exact'],
                'date_time_medition': ['contains', 'gte', 'lte', 'year', 'month', 'day', 'year__range', 'month__range', 'day__range', 'hour', 'date__range'],
                'created': ['contains', 'gte', 'hour', 'lte', 'year', 'month', 'day', 'year__range', 'month__range', 'day__range', 'date__range'],
            }

    filterset_class = InteractionFilter


class InteractionDetailOverrideViewSet(mixins.CreateModelMixin,
                               mixins.RetrieveModelMixin,
                               mixins.UpdateModelMixin,
                               mixins.ListModelMixin,
                               mixins.DestroyModelMixin,
                               viewsets.GenericViewSet):

    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    ordering = ('-date_time_medition', )
    # ✅ MEJORADO: Optimización con select_related para mejorar rendimiento
    queryset = InteractionDetail.objects.select_related('catchment_point').order_by('-date_time_medition')
    serializer_class = InteractionDetailModelSerializer
    lookup_field = "id"
    
    def get_queryset(self):
        """
        ✅ MEJORADO: Optimización adicional con prefetch_related para evitar N+1 queries.
        """
        queryset = super().get_queryset()
        # ✅ Optimización: Prefetch para ProfileDataConfigCatchment y Schemes
        from django.db.models import Prefetch
        from api.core.models import ProfileDataConfigCatchment, SchemesCatchment, Variable
        
        queryset = queryset.prefetch_related(
            Prefetch(
                'catchment_point__data_config_profiles',
                queryset=ProfileDataConfigCatchment.objects.only('point_catchment_id', 'd6')
            ),
            Prefetch(
                'catchment_point__schemes',
                queryset=SchemesCatchment.objects.prefetch_related(
                    Prefetch(
                        'variables',  # ✅ FIX: Cambiar variable_set por variables (related_name correcto)
                        queryset=Variable.objects.only('id', 'type_variable', 'scheme_catchment_id')
                    )
                )
            )
        )
        return queryset

    class NoPagination(PageNumberPagination):
        page_size = None

    pagination_class = NoPagination

    class InteractionFilter(filters.FilterSet):
        class Meta:
            model = InteractionDetail
            fields = {
                'catchment_point': ['exact'],
                'send_dga': ['exact'],
                'date_time_medition': ['contains', 'gte', 'lte', 'year', 'month', 'day', 'year__range', 'month__range', 'day__range', 'hour', 'date__range'],
                'created': ['contains', 'gte', 'hour', 'lte', 'year', 'month', 'day', 'year__range', 'month__range', 'day__range', 'date__range'],
            }

    filterset_class = InteractionFilter

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # ✅ Seguridad: si no hay filtro de fecha, limitar a últimos 7 días
        date_param_keys = ['date_time_medition', 'hour', 'year', 'month', 'day', 'daily']
        has_date_filter = any(
            key.startswith('date_time_medition') or key in date_param_keys
            for key in request.query_params.keys()
        )

        if not has_date_filter:
            from django.utils import timezone
            from datetime import timedelta
            cutoff = timezone.now() - timedelta(days=7)
            queryset = queryset.filter(date_time_medition__gte=cutoff)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class InteractionDetailOverrideMonthViewSet(mixins.CreateModelMixin,
                                            mixins.RetrieveModelMixin,
                                            mixins.UpdateModelMixin,
                                            mixins.ListModelMixin,
                                            mixins.DestroyModelMixin,
                                            viewsets.GenericViewSet):

    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    ordering = ('-date_time_medition', )
    # ✅ Optimización: Usar select_related para evitar N+1 queries en relaciones
    queryset = InteractionDetail.objects.select_related('catchment_point').filter().order_by('-date_time_medition')
    serializer_class = InteractionDetailModelSerializer
    lookup_field = "id"

    class NoPagination(PageNumberPagination):
        page_size = None

    pagination_class = NoPagination

    class InteractionFilter(filters.FilterSet):
        class Meta:
            model = InteractionDetail
            fields = {
                'catchment_point': ['exact'],
                'send_dga': ['exact'],
                'date_time_medition': ['contains', 'gte', 'lte', 'year', 'month', 'day', 'year__range', 'month__range', 'day__range', 'hour', 'date__range'],
                'created': ['contains', 'gte', 'hour', 'lte', 'year', 'month', 'day', 'year__range', 'month__range', 'day__range', 'date__range'],
            }

    filterset_class = InteractionFilter

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # ✅ Seguridad: si no hay filtro de fecha, limitar a últimos 90 días
        date_param_keys = ['date_time_medition', 'hour', 'year', 'month', 'day', 'daily']
        has_date_filter = any(
            key.startswith('date_time_medition') or key in date_param_keys
            for key in request.query_params.keys()
        )

        if not has_date_filter:
            from django.utils import timezone
            from datetime import timedelta
            cutoff = timezone.now() - timedelta(days=90)
            queryset = queryset.filter(date_time_medition__gte=cutoff)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def get_queryset(self):
        """
        Optimización: Obtener solo el último registro por día para cada punto de captación.
        MANTIENE LA MISMA LÓGICA ORIGINAL - Solo agrega optimizaciones de consultas.
        """
        queryset = super().get_queryset()
        
        # ✅ MANTENER LÓGICA ORIGINAL: Subquery idéntica al código original
        # Solo agregamos '-id' al order_by para mejor determinismo (no cambia resultados)
        subquery = InteractionDetail.objects.filter(
            catchment_point=models.OuterRef('catchment_point'),
            date_time_medition__date=models.OuterRef('date_time_medition__date')
        ).order_by('-date_time_medition', '-id').values('id')[:1]
        
        # ✅ MANTENER FORMATO ORIGINAL: id__in=subquery (compatible con Django)
        queryset = queryset.filter(id__in=subquery)
        
        # ✅ OPTIMIZACIÓN: Prefetch relacionado (NO cambia resultados, solo mejora rendimiento)
        # Esto evita N+1 queries en el serializer cuando accede a data_config_profiles
        from api.core.models import ProfileDataConfigCatchment
        from django.db.models import Prefetch
        
        queryset = queryset.prefetch_related(
            Prefetch(
                'catchment_point__data_config_profiles',
                queryset=ProfileDataConfigCatchment.objects.only('point_catchment_id', 'd6')
            ),
            # ✅ Prefetch schemes para optimizar consultas de Variable en el serializer
            'catchment_point__schemes'
        )
        
        return queryset
    
class InteractionXLSMonth(XLSXFileMixin, ReadOnlyModelViewSet):
    queryset = InteractionDetail.objects.all().order_by('-date_time_medition')
    serializer_class = InteractionDetailModelSerializer
    def get_filename(self, request=None, *args, **kwargs):
        """Construye nombre de archivo según punto y rango de fechas."""
        # Defaults
        point_name = 'catchment'
        start_date = None
        end_date = None
        qp = request.query_params if request is not None else {}
        try:
            cp = qp.get('catchment_point')
            if cp:
                try:
                    cp_obj = CatchmentPoint.objects.filter(id=cp).first()
                    if cp_obj and cp_obj.title:
                        point_name = str(cp_obj.title)
                    else:
                        point_name = f'catchment_{cp}'
                except Exception:
                    point_name = f'catchment_{cp}'
            dr = qp.get('date_time_medition__date__range')
            if dr and ',' in dr:
                start_date, end_date = [x.strip() for x in dr.split(',', 1)]
        except Exception:
            pass
        # Saneamos nombre
        import re as _re
        def clean(t):
            t = t or ''
            t = t.strip()
            t = t.replace(' ', '_')
            t = _re.sub(r'[^A-Za-z0-9_\-]+', '', t)
            return t
        pn = clean(point_name)
        sd = clean(start_date or '')
        ed = clean(end_date or '')
        # Armar nombre final
        parts = [pn]
        if sd:
            parts.append(sd)
        if ed:
            parts.append(ed)
        base = '_'.join(parts) if parts else 'export'
        return f"{base}.xlsx"
    def get_filename(self, request=None, *args, **kwargs):
        """Construye nombre de archivo según punto y rango de fechas."""
        # Defaults
        point_name = 'catchment'
        start_date = None
        end_date = None
        qp = request.query_params if request is not None else {}
        try:
            cp = qp.get('catchment_point')
            if cp:
                try:
                    cp_obj = CatchmentPoint.objects.filter(id=cp).first()
                    if cp_obj and cp_obj.title:
                        point_name = str(cp_obj.title)
                    else:
                        point_name = f'catchment_{cp}'
                except Exception:
                    point_name = f'catchment_{cp}'
            dr = qp.get('date_time_medition__date__range')
            if dr and ',' in dr:
                start_date, end_date = [x.strip() for x in dr.split(',', 1)]
        except Exception:
            pass
        # Saneamos nombre
        import re as _re
        def clean(t):
            t = t or ''
            t = t.strip()
            t = t.replace(' ', '_')
            t = _re.sub(r'[^A-Za-z0-9_\-]+', '', t)
            return t
        pn = clean(point_name)
        sd = clean(start_date or '')
        ed = clean(end_date or '')
        # Armar nombre final
        parts = [pn]
        if sd:
            parts.append(sd)
        if ed:
            parts.append(ed)
        base = '_'.join(parts) if parts else 'export'
        return f"{base}.xlsx"
    renderer_classes = (JSONRenderer, XLSXRenderer)
    filter_backends = (filters.DjangoFilterBackend,)
    class CustomPagination(PageNumberPagination):
        def paginate_queryset(self, queryset, request, view=None):
            if isinstance(request.accepted_renderer, XLSXRenderer):
                return None
            return super().paginate_queryset(queryset, request, view)
    pagination_class = CustomPagination 

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Optimize query for export
        queryset = queryset.select_related('catchment_point')
        queryset = queryset.prefetch_related(
            'catchment_point__data_config_profiles',
            'catchment_point__dga_data_config_profiles',
            'catchment_point__schemes__variables'
        )

        subquery = InteractionDetail.objects.filter(
            catchment_point=models.OuterRef('catchment_point'),
            date_time_medition__date=models.OuterRef('date_time_medition__date')
        ).order_by('-date_time_medition').values('id')[:1]
        
        queryset = queryset.filter(id__in=subquery)
        return queryset
    
   

    class InteractionFilter(filters.FilterSet):
        class Meta:
            model = InteractionDetail
            fields = {
                'catchment_point': ['exact'],
                'send_dga': ['exact'],
                'date_time_medition': ['contains', 'gte', 'lte', 'year', 'month', 'day', 'year__range', 'month__range', 'day__range', 'date__range'],
            }

    filterset_class = InteractionFilter

    xlsx_ignore_headers = [
        'modified', 
        'id', 
        'created',
        "nivel", 
        "days_not_conection",
        'catchment_point', 
        'send_dga', 
        'return_dga',
        "date_time_last_logger", 
        "pulses",
        "total_diff",
        'n_voucher',
        "is_error", 
        "notification"]
    
    
    column_header = {
        'titles': [
            "Fecha",
            "Caudal (l/s)",
            "Acumulado (m³)",
            "Consumo (m³)",
            "Nivel Freático (m)", 
            
        ],
        'column_width': [30, 14, 30, 30, 52],
        'height': 25,
        'style': {
            'fill': {
                'fill_type': 'solid',
                'start_color': '1F3461',
            },
            'alignment': {
                'horizontal': 'center',
                'vertical': 'center',
                'wrapText': True,
                'shrink_to_fit': True,
            },
            'border_side': {
                'border_style': 'thin',
                'color': 'FF000000',
            },
            'font': {
                'name': 'Arial',
                'size': 12,
                'bold': True,
                'color': 'FFFFFF',
            },
        },
        
        
    }
    
    body = {
        'style': {
            'fill': {
                'fill_type': 'solid',
                'start_color': 'FFFFFF',
            },
            'alignment': {
                'horizontal': 'center',
                'vertical': 'center',
                'wrapText': True,
                'shrink_to_fit': True,
            },
            'border_side': {
                'border_style': 'thin',
                'color': 'FF000000',
            },
            'font': {
                'name': 'Arial',
                'size': 12,
                'bold': False,
                'color': 'FF000000',
            }
        },
        'height': 20,
    }
    
        
class InteractionXLS(XLSXFileMixin, ReadOnlyModelViewSet):
    queryset = InteractionDetail.objects.all().order_by('-date_time_medition')
    serializer_class = InteractionDetailModelSerializer
    renderer_classes = (JSONRenderer, XLSXRenderer)
    filter_backends = (filters.DjangoFilterBackend,)
    class CustomPagination(PageNumberPagination):
        def paginate_queryset(self, queryset, request, view=None):
            if isinstance(request.accepted_renderer, XLSXRenderer):
                return None
            return super().paginate_queryset(queryset, request, view)
    pagination_class = CustomPagination 
    
   

    class InteractionFilter(filters.FilterSet):
        class Meta:
            model = InteractionDetail
            fields = {
                'catchment_point': ['exact'],
                'send_dga': ['exact'],
                'date_time_medition': ['contains', 'gte', 'lte', 'year', 'month', 'day', 'year__range', 'month__range', 'day__range', 'date__range'],
            }

    filterset_class = InteractionFilter

    xlsx_ignore_headers = [
        'modified', 
        'id', 
        'created',
        # "nivel",  <-- REMOVED from ignore list
        "days_not_conection",
        'catchment_point', 
        'send_dga', 
        'return_dga',
        "date_time_last_logger", 
        "n_voucher", 
        "pulses",
        "is_error", 
        "notification",
        "variable_details",
        "is_partial"]
    
    
    column_header = {
        'titles': [
            "Fecha",
            "Caudal (l/s)",
            "Acumulado (m³)",
            "Acumulado/hora (m³)",
            "Contador diario (m³)",
            "Nivel (m)",
            "Nivel Freático (m)"
        ],
        'column_width': [30, 14, 30, 30, 30, 22, 22],
        'height': 25,
        'style': {
            'fill': {
                'fill_type': 'solid',
                'start_color': '1F3461',
            },
            'alignment': {
                'horizontal': 'center',
                'vertical': 'center',
                'wrapText': True,
                'shrink_to_fit': True,
            },
            'border_side': {
                'border_style': 'thin',
                'color': 'FF000000',
            },
            'font': {
                'name': 'Arial',
                'size': 12,
                'bold': True,
                'color': 'FFFFFFFF',
            },
        },
    }

    def get_renderer_context(self):
        context = super().get_renderer_context()
        
        # Default Full Headers (Reference)
        # 0: Fecha
        # 1: Caudal (l/s)
        # 2: Acumulado (m³)
        # 3: Acumulado/hora (m³)
        # 4: Contador diario (m³)
        # 5: Nivel (m)
        # 6: Nivel Freático (m)
        
        # Default Ignore List (Fields to exclude from model)
        default_ignore = [
            'modified', 'id', 'created', "days_not_conection",
            'catchment_point', 'send_dga', 'return_dga',
            "date_time_last_logger", "n_voucher", "pulses",
            "is_error", "notification",
            "variable_details", "is_partial"
        ]

        if not self.request:
            return context

        catchment_point_id = self.request.query_params.get('catchment_point')
        
        if catchment_point_id:
            try:
                # Import here to avoid circular dependencies
                from api.core.models import CatchmentPoint, Variable
                
                point = CatchmentPoint.objects.get(id=catchment_point_id)
                # Get all variables associated with this point's schemes
                variables = Variable.objects.filter(scheme_catchment__points_catchment=point).values_list('type_variable', flat=True)
                variables_set = set(variables)

                # Determine which columns to KEEP based on variables
                # Always keep Fecha (Index 0)
                indices_to_keep = [0] 
                
                # Dynamic Logic
                has_caudal = "CAUDAL" in variables_set or "CAUDAL_PROMEDIO" in variables_set
                has_total = "TOTALIZADO" in variables_set
                has_nivel = "NIVEL" in variables_set

                # Caudal Columns: "Caudal (l/s)" (Index 1)
                if has_caudal:
                    indices_to_keep.append(1)
                
                # Totalizado Columns: "Acumulado", "Acumulado/hora", "Contador diario" (Indices 2, 3, 4)
                if has_total:
                    indices_to_keep.extend([2, 3, 4])
                
                # Nivel Columns: "Nivel (m)", "Nivel Freático (m)" (Indices 5, 6)
                if has_nivel:
                    indices_to_keep.extend([5, 6])
                
                # Filter Titles and Widths
                # Use class attribute as source to avoid mutation issues
                base_header = self.__class__.column_header
                full_titles = base_header['titles']
                full_widths = base_header['column_width']

                new_titles = [full_titles[i] for i in indices_to_keep]
                new_widths = [full_widths[i] for i in indices_to_keep]
                
                # Construct new dynamic header dictionary
                # We copy the style/height from base to preserve formatting
                dynamic_header = {
                    'titles': new_titles,
                    'column_width': new_widths,
                    'height': base_header.get('height', 25),
                    'style': base_header.get('style', {})
                }

                # CRITICAL Fix: Override the instance attribute so the renderer uses this instead of class attribute
                self.column_header = dynamic_header
                
                # Also update context for completeness (some renderers look here)
                if 'header' not in context:
                     context['header'] = {}
                context['header'] = dynamic_header


                # Update Ignore List to Hide Model Fields corresponding to missing columns
                new_ignore = default_ignore.copy()
                
                if not has_caudal:
                    new_ignore.append('flow')
                
                if not has_total:
                    new_ignore.extend(['total', 'total_diff', 'total_today_diff'])
                
                if not has_nivel:
                    new_ignore.extend(['nivel', 'water_table'])

                # Override ignore headers for this request
                self.xlsx_ignore_headers = new_ignore

            except Exception as e:
                logger.error(
                    "Error determining dynamic columns for Excel export",
                    extra={'error': str(e)},
                    exc_info=True
                )

        return context

    
    body = {
        'style': {
            'fill': {
                'fill_type': 'solid',
                'start_color': 'FFFFFF',
            },
            'alignment': {
                'horizontal': 'center',
                'vertical': 'center',
                'wrapText': True,
                'shrink_to_fit': True,
            },
            'border_side': {
                'border_style': 'thin',
                'color': 'FF000000',
            },
            'font': {
                'name': 'Arial',
                'size': 12,
                'bold': False,
                'color': 'FF000000',
            }
        },
        'height': 20,
    }
    

class InteractionXLSDga(XLSXFileMixin, ReadOnlyModelViewSet):
    queryset = InteractionDetail.objects.all().order_by('-date_time_medition')
    serializer_class = InteractionDetailModelSerializerNoProcessing
    def get_filename(self, request=None, *args, **kwargs):
        """Construye nombre de archivo según punto y rango de fechas."""
        # Defaults
        point_name = 'catchment'
        start_date = None
        end_date = None
        qp = request.query_params if request is not None else {}
        try:
            cp = qp.get('catchment_point') or qp.get('point_catchment')
            if cp:
                try:
                    cp_obj = CatchmentPoint.objects.filter(id=cp).first()
                    if cp_obj and cp_obj.title:
                        point_name = str(cp_obj.title)
                    else:
                        point_name = f'catchment_{cp}'
                except Exception:
                    point_name = f'catchment_{cp}'
            dr = qp.get('date_time_medition__date__range')
            if dr and ',' in dr:
                start_date, end_date = [x.strip() for x in dr.split(',', 1)]
        except Exception:
            pass
        # Saneamos nombre
        import re as _re
        def clean(t):
            t = t or ''
            t = t.strip()
            t = t.replace(' ', '_')
            t = _re.sub(r'[^A-Za-z0-9_\-]+', '', t)
            return t
        pn = clean(point_name)
        sd = clean(start_date or '')
        ed = clean(end_date or '')
        # Armar nombre final
        parts = [pn]
        if sd:
            parts.append(sd)
        if ed:
            parts.append(ed)
        base = '_'.join(parts) if parts else 'export'
        return f"{base}.xlsx"
    renderer_classes = (JSONRenderer, XLSXRenderer)
    filter_backends = (filters.DjangoFilterBackend,)
    class CustomPagination(PageNumberPagination):
        def paginate_queryset(self, queryset, request, view=None):
            if isinstance(request.accepted_renderer, XLSXRenderer):
                return None
            return super().paginate_queryset(queryset, request, view)
    pagination_class = CustomPagination 
    
   

    class InteractionFilter(filters.FilterSet):
        # Alias for point_catchment -> catchment_point
        point_catchment = filters.NumberFilter(field_name='catchment_point')

        class Meta:
            model = InteractionDetail
            fields = {
                'catchment_point': ['exact'],
                'send_dga': ['exact'],
                'date_time_medition': ['contains', 'gte', 'lte', 'year', 'month', 'day', 'year__range', 'month__range', 'day__range', 'date__range'],
            }

    filterset_class = InteractionFilter

    xlsx_ignore_headers = [
        'modified', 
        'id', 
        'created',
        "nivel", 
        "days_not_conection",
        'catchment_point', 
        'send_dga', 
        'return_dga',
        "date_time_last_logger", 
        "pulses",
        "total_diff",
        "total_today_diff",
        "is_error", 
        "notification",
        "variable_details",
        "is_partial"]
    
    
    column_header = {
        'titles': [
            "Fecha",
            "Caudal (l/s)",
            "Acumulado (m³)",
            "Nivel Freático (m)", 
            "Código Compronante"
        ],
        'column_width': [30, 14, 30, 30, 52],
        'height': 25,
        'style': {
            'fill': {
                'fill_type': 'solid',
                'start_color': '1F3461',
            },
            'alignment': {
                'horizontal': 'center',
                'vertical': 'center',
                'wrapText': True,
                'shrink_to_fit': True,
            },
            'border_side': {
                'border_style': 'thin',
                'color': 'FF000000',
            },
            'font': {
                'name': 'Arial',
                'size': 12,
                'bold': True,
                'color': 'FFFFFF',
            },
        },
        
        
    }
    
    body = {
        'style': {
            'fill': {
                'fill_type': 'solid',
                'start_color': 'FFFFFF',
            },
            'alignment': {
                'horizontal': 'center',
                'vertical': 'center',
                'wrapText': True,
                'shrink_to_fit': True,
            },
            'border_side': {
                'border_style': 'thin',
                'color': 'FF000000',
            },
            'font': {
                'name': 'Arial',
                'size': 12,
                'bold': False,
                'color': 'FF000000',
            }
        },
        'height': 20,
    }
    
  
import rest_framework.response as status
