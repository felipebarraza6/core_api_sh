import logging

import django.db.models as models
from django_filters import rest_framework as filters
from drf_excel.mixins import XLSXFileMixin
from drf_excel.renderers import XLSXRenderer
from rest_framework import mixins, status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from api.telemetry.models import CatchmentPoint, TelemetryRecord
from api.core.serializers import (
    InteractionDetailModelSerializer,
    InteractionDetailModelSerializerNoProcessing,
)

logger = logging.getLogger(__name__)


class InteractionDetailViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):

    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    ordering = ("-timestamp",)
    queryset = TelemetryRecord.objects.select_related("point").order_by("-timestamp")
    serializer_class = InteractionDetailModelSerializer
    lookup_field = "id"

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Limit default list to 100 records if no date filter is present
        date_param_keys = ["timestamp", "hour", "year", "month", "day", "daily"]
        has_date_filter = any(
            key.startswith("timestamp") or key in date_param_keys
            for key in request.query_params.keys()
        )

        if not has_date_filter:
            queryset = queryset[:100]

        # Limit for high frequency points (User Request)
        limit_applied = False
        point_id = request.query_params.get("point") or request.query_params.get(
            "catchment_point"
        )
        if point_id:
            try:
                point = CatchmentPoint.objects.only("frecuency").get(id=point_id)
                if point.frecuency in ["1", "5"]:
                    queryset = queryset[:50]
                    limit_applied = True
            except Exception:
                pass

        if limit_applied:
            serializer = self.get_serializer(queryset, many=True)
            return Response(
                {
                    "count": 50,
                    "next": None,
                    "previous": None,
                    "results": serializer.data,
                }
            )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    class InteractionFilter(filters.FilterSet):
        # Mapeo de campos legacy a nuevos campos V3
        catchment_point = filters.NumberFilter(field_name="point")
        date_time_medition = filters.DateTimeFilter(field_name="timestamp")
        date_time_medition__gte = filters.DateTimeFilter(
            field_name="timestamp", lookup_expr="gte"
        )
        date_time_medition__lte = filters.DateTimeFilter(
            field_name="timestamp", lookup_expr="lte"
        )
        hour = filters.NumberFilter(field_name="timestamp", lookup_expr="hour")

        class Meta:
            model = TelemetryRecord
            fields = {
                "point": ["exact"],
                "send_dga": ["exact"],
                "timestamp": ["contains", "gte", "lte", "year", "month", "day", "hour"],
                "created": ["contains", "gte", "lte"],
            }

    filterset_class = InteractionFilter


class InteractionDetailOverrideViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):

    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    ordering = ("-timestamp",)
    queryset = TelemetryRecord.objects.select_related("point").order_by("-timestamp")
    serializer_class = InteractionDetailModelSerializer
    lookup_field = "id"

    class NoPagination(PageNumberPagination):
        page_size = None

    pagination_class = NoPagination

    class InteractionFilter(filters.FilterSet):
        catchment_point = filters.NumberFilter(field_name="point")
        date_time_medition = filters.DateTimeFilter(field_name="timestamp")

        class Meta:
            model = TelemetryRecord
            fields = {
                "point": ["exact"],
                "send_dga": ["exact"],
                "timestamp": ["contains", "gte", "lte", "year", "month", "day", "hour"],
                "created": ["contains", "gte", "lte"],
            }

    filterset_class = InteractionFilter


class InteractionDetailOverrideMonthViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):

    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    ordering = ("-timestamp",)
    queryset = TelemetryRecord.objects.select_related("point").order_by("-timestamp")
    serializer_class = InteractionDetailModelSerializer
    lookup_field = "id"

    class NoPagination(PageNumberPagination):
        page_size = None

    pagination_class = NoPagination

    class InteractionFilter(filters.FilterSet):
        catchment_point = filters.NumberFilter(field_name="point")
        date_time_medition = filters.DateTimeFilter(field_name="timestamp")

        class Meta:
            model = TelemetryRecord
            fields = {
                "point": ["exact"],
                "send_dga": ["exact"],
                "timestamp": ["contains", "gte", "lte", "year", "month", "day", "hour"],
                "created": ["contains", "gte", "lte"],
            }

    filterset_class = InteractionFilter

    def get_queryset(self):
        """
        Optimización: Obtener solo el último registro por día para cada punto de captación.
        """
        queryset = super().get_queryset()

        # Subquery para obtener el último registro por día
        subquery = (
            TelemetryRecord.objects.filter(
                point=models.OuterRef("point"),
                timestamp__date=models.OuterRef("timestamp__date"),
            )
            .order_by("-timestamp", "-id")
            .values("id")[:1]
        )

        queryset = queryset.filter(id__in=subquery)
        return queryset


class InteractionXLSMonth(XLSXFileMixin, ReadOnlyModelViewSet):
    queryset = TelemetryRecord.objects.all().order_by("-timestamp")
    serializer_class = InteractionDetailModelSerializer

    def get_filename(self, request=None, *args, **kwargs):
        """Construye nombre de archivo según punto y rango de fechas."""
        point_name = "catchment"
        start_date = None
        end_date = None
        qp = request.query_params if request is not None else {}
        try:
            cp = qp.get("catchment_point") or qp.get("point")
            if cp:
                try:
                    cp_obj = CatchmentPoint.objects.filter(id=cp).first()
                    if cp_obj and cp_obj.title:
                        point_name = str(cp_obj.title)
                    else:
                        point_name = f"catchment_{cp}"
                except Exception:
                    point_name = f"catchment_{cp}"
            dr = qp.get("timestamp__date__range") or qp.get(
                "date_time_medition__date__range"
            )
            if dr and "," in dr:
                start_date, end_date = [x.strip() for x in dr.split(",", 1)]
        except Exception:
            pass
        # Saneamos nombre
        import re as _re

        def clean(t):
            t = t or ""
            t = t.strip()
            t = t.replace(" ", "_")
            t = _re.sub(r"[^A-Za-z0-9_\-]+", "", t)
            return t

        pn = clean(point_name)
        sd = clean(start_date or "")
        ed = clean(end_date or "")
        parts = [pn]
        if sd:
            parts.append(sd)
        if ed:
            parts.append(ed)
        base = "_".join(parts) if parts else "export"
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
        queryset = queryset.select_related("point")

        subquery = (
            TelemetryRecord.objects.filter(
                point=models.OuterRef("point"),
                timestamp__date=models.OuterRef("timestamp__date"),
            )
            .order_by("-timestamp")
            .values("id")[:1]
        )

        queryset = queryset.filter(id__in=subquery)
        return queryset

    class InteractionFilter(filters.FilterSet):
        catchment_point = filters.NumberFilter(field_name="point")
        date_time_medition = filters.DateTimeFilter(field_name="timestamp")

        class Meta:
            model = TelemetryRecord
            fields = {
                "point": ["exact"],
                "send_dga": ["exact"],
                "timestamp": [
                    "contains",
                    "gte",
                    "lte",
                    "year",
                    "month",
                    "day",
                    "date__range",
                ],
            }

    filterset_class = InteractionFilter

    xlsx_ignore_headers = [
        "modified",
        "id",
        "created",
        "nivel",
        "days_not_conection",
        "point",
        "send_dga",
        "return_dga",
        "date_time_last_logger",
        "pulses",
        "total_diff",
        "n_voucher",
        "is_error",
        "notification",
    ]

    column_header = {
        "titles": [
            "Fecha",
            "Caudal (l/s)",
            "Acumulado (m³)",
            "Consumo (m³)",
            "Nivel Freático (m)",
        ],
        "column_width": [30, 14, 30, 30, 52],
        "height": 25,
        "style": {
            "fill": {"fill_type": "solid", "start_color": "1F3461"},
            "alignment": {
                "horizontal": "center",
                "vertical": "center",
                "wrapText": True,
                "shrink_to_fit": True,
            },
            "border_side": {"border_style": "thin", "color": "FF000000"},
            "font": {"name": "Arial", "size": 12, "bold": True, "color": "FFFFFF"},
        },
    }

    body = {
        "style": {
            "fill": {"fill_type": "solid", "start_color": "FFFFFF"},
            "alignment": {
                "horizontal": "center",
                "vertical": "center",
                "wrapText": True,
                "shrink_to_fit": True,
            },
            "border_side": {"border_style": "thin", "color": "FF000000"},
            "font": {"name": "Arial", "size": 12, "bold": False, "color": "FF000000"},
        },
        "height": 20,
    }


class InteractionXLS(XLSXFileMixin, ReadOnlyModelViewSet):
    queryset = TelemetryRecord.objects.all().order_by("-timestamp")
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
        catchment_point = filters.NumberFilter(field_name="point")
        date_time_medition = filters.DateTimeFilter(field_name="timestamp")

        class Meta:
            model = TelemetryRecord
            fields = {
                "point": ["exact"],
                "send_dga": ["exact"],
                "timestamp": [
                    "contains",
                    "gte",
                    "lte",
                    "year",
                    "month",
                    "day",
                    "date__range",
                ],
            }

    filterset_class = InteractionFilter

    xlsx_ignore_headers = [
        "modified",
        "id",
        "created",
        "days_not_conection",
        "point",
        "send_dga",
        "return_dga",
        "date_time_last_logger",
        "n_voucher",
        "pulses",
        "is_error",
        "notification",
    ]

    column_header = {
        "titles": [
            "Fecha",
            "Caudal (l/s)",
            "Acumulado (m³)",
            "Acumulado/hora (m³)",
            "Contador diario (m³)",
            "Nivel (m)",
            "Nivel Freático (m)",
        ],
        "column_width": [30, 14, 30, 30, 30, 22, 22],
        "height": 25,
        "style": {
            "fill": {"fill_type": "solid", "start_color": "1F3461"},
            "alignment": {
                "horizontal": "center",
                "vertical": "center",
                "wrapText": True,
                "shrink_to_fit": True,
            },
            "border_side": {"border_style": "thin", "color": "FF000000"},
            "font": {"name": "Arial", "size": 12, "bold": True, "color": "FFFFFFFF"},
        },
    }

    def get_renderer_context(self):
        context = super().get_renderer_context()
        if not self.request:
            return context

        point_id = self.request.query_params.get(
            "point"
        ) or self.request.query_params.get("catchment_point")
        if point_id:
            try:
                from api.telemetry.models.telemetry import CoreVariable

                variables = CoreVariable.objects.filter(
                    point_id=point_id, is_active=True
                ).values_list("internal_code", flat=True)
                variables_set = set(variables)

                indices_to_keep = [0]
                has_caudal = "flow" in variables_set or "caudal" in variables_set
                has_total = "total" in variables_set
                has_nivel = "nivel" in variables_set or "water_table" in variables_set

                if has_caudal:
                    indices_to_keep.append(1)
                if has_total:
                    indices_to_keep.extend([2, 3, 4])
                if has_nivel:
                    indices_to_keep.extend([5, 6])

                base_header = self.__class__.column_header
                new_titles = [base_header["titles"][i] for i in indices_to_keep]
                new_widths = [base_header["column_width"][i] for i in indices_to_keep]

                dynamic_header = {
                    "titles": new_titles,
                    "column_width": new_widths,
                    "height": base_header.get("height", 25),
                    "style": base_header.get("style", {}),
                }
                self.column_header = dynamic_header
                context["header"] = dynamic_header
            except Exception:
                pass
        return context

    body = {
        "style": {
            "fill": {"fill_type": "solid", "start_color": "FFFFFF"},
            "alignment": {
                "horizontal": "center",
                "vertical": "center",
                "wrapText": True,
                "shrink_to_fit": True,
            },
            "border_side": {"border_style": "thin", "color": "FF000000"},
            "font": {"name": "Arial", "size": 12, "bold": False, "color": "FF000000"},
        },
        "height": 20,
    }


class InteractionXLSDga(XLSXFileMixin, ReadOnlyModelViewSet):
    queryset = TelemetryRecord.objects.all().order_by("-timestamp")
    serializer_class = InteractionDetailModelSerializerNoProcessing

    def get_filename(self, request=None, *args, **kwargs):
        """Construye nombre de archivo según punto y rango de fechas."""
        point_name = "catchment"
        start_date = None
        end_date = None
        qp = request.query_params if request is not None else {}
        try:
            cp = qp.get("catchment_point") or qp.get("point")
            if cp:
                try:
                    cp_obj = CatchmentPoint.objects.filter(id=cp).first()
                    if cp_obj and cp_obj.title:
                        point_name = str(cp_obj.title)
                    else:
                        point_name = f"catchment_{cp}"
                except Exception:
                    point_name = f"catchment_{cp}"
            dr = qp.get("timestamp__date__range") or qp.get(
                "date_time_medition__date__range"
            )
            if dr and "," in dr:
                start_date, end_date = [x.strip() for x in dr.split(",", 1)]
        except Exception:
            pass
        # Saneamos nombre
        import re as _re

        def clean(t):
            t = t or ""
            t = t.strip()
            t = t.replace(" ", "_")
            t = _re.sub(r"[^A-Za-z0-9_\-]+", "", t)
            return t

        pn = clean(point_name)
        sd = clean(start_date or "")
        ed = clean(end_date or "")
        parts = [pn]
        if sd:
            parts.append(sd)
        if ed:
            parts.append(ed)
        base = "_".join(parts) if parts else "export"
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
        catchment_point = filters.NumberFilter(field_name="point")
        point_catchment = filters.NumberFilter(field_name="point")
        date_time_medition = filters.DateTimeFilter(field_name="timestamp")

        class Meta:
            model = TelemetryRecord
            fields = {
                "point": ["exact"],
                "send_dga": ["exact"],
                "timestamp": [
                    "contains",
                    "gte",
                    "lte",
                    "year",
                    "month",
                    "day",
                    "date__range",
                ],
            }

    filterset_class = InteractionFilter

    xlsx_ignore_headers = [
        "modified",
        "id",
        "created",
        "nivel",
        "days_not_conection",
        "point",
        "send_dga",
        "return_dga",
        "date_time_last_logger",
        "pulses",
        "total_diff",
        "total_today_diff",
        "is_error",
        "notification",
    ]

    column_header = {
        "titles": [
            "Fecha",
            "Caudal (l/s)",
            "Acumulado (m³)",
            "Nivel Freático (m)",
            "Código Compronante",
        ],
        "column_width": [30, 14, 30, 30, 52],
        "height": 25,
        "style": {
            "fill": {"fill_type": "solid", "start_color": "1F3461"},
            "alignment": {
                "horizontal": "center",
                "vertical": "center",
                "wrapText": True,
                "shrink_to_fit": True,
            },
            "border_side": {"border_style": "thin", "color": "FF000000"},
            "font": {"name": "Arial", "size": 12, "bold": True, "color": "FFFFFF"},
        },
    }

    body = {
        "style": {
            "fill": {"fill_type": "solid", "start_color": "FFFFFF"},
            "alignment": {
                "horizontal": "center",
                "vertical": "center",
                "wrapText": True,
                "shrink_to_fit": True,
            },
            "border_side": {"border_style": "thin", "color": "FF000000"},
            "font": {"name": "Arial", "size": 12, "bold": False, "color": "FF000000"},
        },
        "height": 20,
    }


import rest_framework.response as status
