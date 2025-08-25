from rest_framework.viewsets import ReadOnlyModelViewSet
from drf_excel.mixins import XLSXFileMixin
from drf_excel.renderers import XLSXRenderer
from rest_framework.renderers import JSONRenderer

from api.core.serializers import InteractionDetailModelSerializer, InteractionDetailModelSerializerNoProcessing
from api.core.models import InteractionDetail, CatchmentPoint
import django.db.models as models
from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets, status

from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated
)





class InteractionDetailViewSet(mixins.CreateModelMixin,
                               mixins.RetrieveModelMixin,
                               mixins.UpdateModelMixin,
                               mixins.ListModelMixin,
                               mixins.DestroyModelMixin,
                               viewsets.GenericViewSet):

    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    ordering = ('-date_time_medition', )
    queryset = InteractionDetail.objects.all().order_by('-date_time_medition')
    serializer_class = InteractionDetailModelSerializer
    lookup_field = "id"

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


class InteractionDetailOverrideViewSet(mixins.CreateModelMixin,
                               mixins.RetrieveModelMixin,
                               mixins.UpdateModelMixin,
                               mixins.ListModelMixin,
                               mixins.DestroyModelMixin,
                               viewsets.GenericViewSet):

    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    ordering = ('-date_time_medition', )
    queryset = InteractionDetail.objects.all().order_by('-date_time_medition')
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


class InteractionDetailOverrideMonthViewSet(mixins.CreateModelMixin,
                                            mixins.RetrieveModelMixin,
                                            mixins.UpdateModelMixin,
                                            mixins.ListModelMixin,
                                            mixins.DestroyModelMixin,
                                            viewsets.GenericViewSet):

    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    ordering = ('-date_time_medition', )
    queryset = InteractionDetail.objects.filter().order_by('-date_time_medition')
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
    
    def get_queryset(self):
        queryset = super().get_queryset()
        subquery = InteractionDetail.objects.filter(
            catchment_point=models.OuterRef('catchment_point'),
            date_time_medition__date=models.OuterRef('date_time_medition__date')
        ).order_by('-date_time_medition').values('id')[:1]
        
        queryset = queryset.filter(id__in=subquery)
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
        "nivel", 
        "days_not_conection",
        'catchment_point', 
        'send_dga', 
        'return_dga',
        "date_time_last_logger", 
        "n_voucher", 
        "pulses",
        "is_error", 
        "notification"]
    
    
    column_header = {
        'titles': [
            "Fecha",
            "Caudal (l/s)",
            "Acumulado (m³)",
            "Acumulado/hora (m³)",
            "Contador diario (m³)",
            "Nivel Freático (m)"
        ],
        'column_width': [30, 14, 30, 30, 30, 22],
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
        "total_today_diff",
        "is_error", 
        "notification"]
    
    
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
    
  
