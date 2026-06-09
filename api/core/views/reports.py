from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets, status
from rest_framework.decorators import action
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from datetime import datetime
import pytz

from api.core.models import CatchmentPoint, InteractionDetail, ProjectCatchments
from django.db.models import Sum, Avg, Max, Min, Count
from django.db.models.functions import TruncDate
from api.core.reports.excel_generator import (
    generate_excel_by_project,
    generate_excel_by_point,
    generate_excel_last_month_by_points,
    generate_excel_last_year_by_points,
    generate_excel_annual_compressed,
)

from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from drf_spectacular.utils import extend_schema, extend_schema_view


class ActiveCatchmentPointsReportView(APIView):
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Configuración de estilos
        HEADER_FONT = Font(name='Arial', size=10, bold=True, color='FFFFFF')
        HEADER_FILL = PatternFill(start_color='1F3461', end_color='1F3461', fill_type='solid')
        BORDER = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        chile_tz = pytz.timezone("America/Santiago")

        # Crear Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Puntos Activos"

        # Encabezados
        headers = [
            'Cliente',
            'Proyecto',
            'Punto de Captación',
            'Variables',
            'Caudal Promedio',
            'Último Dato (Fecha Medición)',
            'Último Dato (Fecha Logger)'
        ]

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = BORDER
            # Ajustar ancho inicial
            ws.column_dimensions[cell.column_letter].width = 25

        # Obtener puntos activos (con telemetría activada)
        active_points = CatchmentPoint.objects.filter(
            data_config_profiles__is_telemetry=True
        ).select_related(
            'project',
            'project__client'
        ).prefetch_related(
            'schemes__variables'
        ).distinct().order_by(
            'project__client__name',
            'project__name',
            'title'
        )

        # Precalcular últimas interacciones con DISTINCT ON (evita N+1)
        point_ids = list(active_points.values_list('id', flat=True))
        last_interactions_map = {
            interaction.catchment_point_id: interaction
            for interaction in InteractionDetail.objects.filter(
                catchment_point_id__in=point_ids
            ).order_by('catchment_point_id', '-date_time_medition').distinct('catchment_point_id')
        }

        row_num = 2
        for point in active_points:
            # Cliente y Proyecto
            client_name = point.project.client.name if point.project and point.project.client else "N/A"
            project_name = point.project.name if point.project else "N/A"

            # Variables y Flag Caudal Promedio
            variables = []
            has_caudal_promedio = False
            for scheme in point.schemes.all():
                for var in scheme.variables.all():
                    variables.append(var.type_variable)
                    if var.type_variable == 'CAUDAL_PROMEDIO':
                        has_caudal_promedio = True

            variables_str = ", ".join(set(variables)) if variables else "Sin variables"
            caudal_promedio_str = "Si" if has_caudal_promedio else "No"

            # Último dato
            last_interaction = last_interactions_map.get(point.id)

            last_medition = "Sin datos"
            last_logger = "Sin datos"

            if last_interaction:
                if last_interaction.date_time_medition:
                    dt_med = last_interaction.date_time_medition.astimezone(chile_tz)
                    last_medition = dt_med.strftime('%Y-%m-%d %H:%M:%S')

                if last_interaction.date_time_last_logger:
                    dt_log = last_interaction.date_time_last_logger.astimezone(chile_tz)
                    last_logger = dt_log.strftime('%Y-%m-%d %H:%M:%S')

            # Escribir fila
            data = [
                client_name,
                project_name,
                point.title,
                variables_str,
                caudal_promedio_str,
                last_medition,
                last_logger
            ]

            for col_num, value in enumerate(data, 1):
                cell = ws.cell(row=row_num, column=col_num, value=value)
                cell.border = BORDER
                cell.alignment = Alignment(horizontal='left', vertical='center')

            row_num += 1

        # Preparar respuesta
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="reporte_puntos_activos_{datetime.now().strftime("%Y%m%d")}.xlsx"'

        wb.save(response)
        return response


@extend_schema_view(
    by_project=extend_schema(summary="Excel por proyecto", description="Análisis de telemetría agregado por proyecto. Query: project_id."),
    by_point=extend_schema(summary="Excel por punto", description="Análisis de telemetría por punto y período. Query: point_id, year, month."),
    last_month=extend_schema(summary="Excel último mes", description="Datos del mes anterior para múltiples puntos. Query: project_id, point_ids."),
    last_year=extend_schema(summary="Excel último año", description="Datos del año anterior para múltiples puntos. Query: project_id, point_ids."),
    annual_compressed=extend_schema(summary="Excel anual comprimido", description="Resumen anual comprimido por punto. Query: project_id, point_ids."),
    json_by_project=extend_schema(summary="JSON por proyecto", description="Resumen de últimos 30 días por punto. Query: project_id, point_ids."),
    json_by_point=extend_schema(summary="JSON por punto", description="Datos diarios agregados por punto. Query: point_id, year, month."),
    json_last_month=extend_schema(summary="JSON último mes", description="Datos del mes anterior por punto. Query: project_id, point_ids."),
    json_last_year=extend_schema(summary="JSON último año", description="Datos del año anterior por punto. Query: project_id, point_ids."),
    json_annual_compressed=extend_schema(summary="JSON anual comprimido", description="Resumen anual por punto. Query: project_id, point_ids."),
)
class ReportsGenerationViewSet(viewsets.ViewSet):
    """
    ViewSet para generar reportes Excel y JSON desde el frontend.
    """
    permission_classes = [IsAuthenticated]

    def _get_points(self, project_id=None, point_ids=None):
        """Helper para obtener puntos según filtros."""
        queryset = CatchmentPoint.objects.all()
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        if point_ids:
            queryset = queryset.filter(id__in=point_ids)
        return list(queryset)

    def _excel_response(self, buffer, filename):
        """Helper para crear respuesta Excel."""
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @action(detail=False, methods=['get'], url_path='by-project')
    def by_project(self, request):
        """
        Genera Excel de análisis de telemetría por proyecto.

        Query params:
            - project_id: ID del proyecto (obligatorio)
        """
        project_id = request.query_params.get('project_id')
        if not project_id:
            return Response(
                {'error': 'project_id es requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            project = ProjectCatchments.objects.get(id=project_id)
        except ProjectCatchments.DoesNotExist:
            return Response(
                {'error': 'Proyecto no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )

        points = self._get_points(project_id=project_id)
        if not points:
            return Response(
                {'error': 'No hay puntos en este proyecto'},
                status=status.HTTP_404_NOT_FOUND
            )

        buffer = generate_excel_by_project(points, project_name=project.name)
        return self._excel_response(
            buffer,
            f"reporte_proyecto_{project.name}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        )

    @action(detail=False, methods=['get'], url_path='by-point')
    def by_point(self, request):
        """
        Genera Excel de análisis de telemetría por punto.

        Query params:
            - point_id: ID del punto (obligatorio)
            - year: Año (opcional, default año actual)
            - month: Mes 1-12 (opcional, si no se especifica procesa todo el año)
        """
        point_id = request.query_params.get('point_id')
        if not point_id:
            return Response(
                {'error': 'point_id es requerido'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            point = CatchmentPoint.objects.get(id=point_id)
        except CatchmentPoint.DoesNotExist:
            return Response(
                {'error': 'Punto no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )

        year = request.query_params.get('year')
        month = request.query_params.get('month')

        try:
            year = int(year) if year else None
        except (ValueError, TypeError):
            year = None
        try:
            month = int(month) if month else None
        except (ValueError, TypeError):
            month = None

        buffer = generate_excel_by_point(point, year=year, month=month)
        return self._excel_response(
            buffer,
            f"reporte_punto_{point.title}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        )

    @action(detail=False, methods=['get'], url_path='last-month')
    def last_month(self, request):
        """
        Genera Excel del último mes completo para varios puntos.

        Query params:
            - project_id: ID del proyecto (opcional)
            - point_ids: Lista de IDs separados por coma (opcional)
        """
        project_id = request.query_params.get('project_id')
        point_ids_str = request.query_params.get('point_ids')

        point_ids = None
        if point_ids_str:
            try:
                point_ids = [int(x.strip()) for x in point_ids_str.split(',') if x.strip()]
            except (ValueError, TypeError):
                point_ids = None

        points = self._get_points(project_id=project_id, point_ids=point_ids)
        if not points:
            return Response(
                {'error': 'No hay puntos para generar el reporte'},
                status=status.HTTP_404_NOT_FOUND
            )

        project_name = None
        if project_id:
            try:
                project_name = ProjectCatchments.objects.get(id=project_id).name
            except ProjectCatchments.DoesNotExist:
                pass

        buffer = generate_excel_last_month_by_points(points, project_name=project_name)
        return self._excel_response(
            buffer,
            f"reporte_ultimo_mes_{datetime.now().strftime('%Y%m%d')}.xlsx"
        )

    @action(detail=False, methods=['get'], url_path='last-year')
    def last_year(self, request):
        """
        Genera Excel del último año completo para varios puntos.

        Query params:
            - project_id: ID del proyecto (opcional)
            - point_ids: Lista de IDs separados por coma (opcional)
        """
        project_id = request.query_params.get('project_id')
        point_ids_str = request.query_params.get('point_ids')

        point_ids = None
        if point_ids_str:
            try:
                point_ids = [int(x.strip()) for x in point_ids_str.split(',') if x.strip()]
            except (ValueError, TypeError):
                point_ids = None

        points = self._get_points(project_id=project_id, point_ids=point_ids)
        if not points:
            return Response(
                {'error': 'No hay puntos para generar el reporte'},
                status=status.HTTP_404_NOT_FOUND
            )

        project_name = None
        if project_id:
            try:
                project_name = ProjectCatchments.objects.get(id=project_id).name
            except ProjectCatchments.DoesNotExist:
                pass

        buffer = generate_excel_last_year_by_points(points, project_name=project_name)
        return self._excel_response(
            buffer,
            f"reporte_ultimo_año_{datetime.now().strftime('%Y%m%d')}.xlsx"
        )

    @action(detail=False, methods=['get'], url_path='annual-compressed')
    def annual_compressed(self, request):
        """
        Genera Excel anual comprimido (resumen) para varios puntos.

        Query params:
            - project_id: ID del proyecto (opcional)
            - point_ids: Lista de IDs separados por coma (opcional)
        """
        project_id = request.query_params.get('project_id')
        point_ids_str = request.query_params.get('point_ids')

        point_ids = None
        if point_ids_str:
            try:
                point_ids = [int(x.strip()) for x in point_ids_str.split(',') if x.strip()]
            except (ValueError, TypeError):
                point_ids = None

        points = self._get_points(project_id=project_id, point_ids=point_ids)
        if not points:
            return Response(
                {'error': 'No hay puntos para generar el reporte'},
                status=status.HTTP_404_NOT_FOUND
            )

        project_name = None
        if project_id:
            try:
                project_name = ProjectCatchments.objects.get(id=project_id).name
            except ProjectCatchments.DoesNotExist:
                pass

        buffer = generate_excel_annual_compressed(points, project_name=project_name)
        return self._excel_response(
            buffer,
            f"reporte_anual_comprimido_{datetime.now().strftime('%Y%m%d')}.xlsx"
        )

    # =========================================================================
    # JSON REPORTS (para frontend)
    # =========================================================================

    def _get_point_ids_from_params(self, request):
        """Extrae point_ids de query params."""
        project_id = request.query_params.get('project_id')
        point_ids_str = request.query_params.get('point_ids')
        point_ids = None
        if point_ids_str:
            try:
                point_ids = [int(x.strip()) for x in point_ids_str.split(',') if x.strip()]
            except (ValueError, TypeError):
                point_ids = None
        points = self._get_points(project_id=project_id, point_ids=point_ids)
        return project_id, points

    def _json_response(self, data):
        return Response(data)

    @action(detail=False, methods=['get'], url_path='json/by-project')
    def json_by_project(self, request):
        """Reporte JSON por proyecto: resumen de cada punto (últimos 30 días)."""
        project_id, points = self._get_point_ids_from_params(request)
        if not points:
            return Response({'error': 'No hay puntos'}, status=status.HTTP_404_NOT_FOUND)

        from django.utils import timezone
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=30)
        point_ids = [p.id for p in points]

        # Agregados por punto
        aggregates = (
            InteractionDetail.objects
            .filter(catchment_point_id__in=point_ids, date_time_medition__gte=cutoff)
            .values('catchment_point_id', 'catchment_point__title')
            .annotate(
                total_consumo=Sum('total_diff'),
                caudal_promedio=Avg('flow'),
                caudal_max=Max('flow'),
                nivel_promedio=Avg('nivel'),
                ultima_medicion=Max('date_time_medition'),
                registros=Count('id'),
            )
            .order_by('catchment_point_id')
        )

        return self._json_response(list(aggregates))

    @action(detail=False, methods=['get'], url_path='json/by-point')
    def json_by_point(self, request):
        """Reporte JSON por punto: datos diarios agregados."""
        point_id = request.query_params.get('point_id')
        if not point_id:
            return Response({'error': 'point_id es requerido'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            point = CatchmentPoint.objects.get(id=point_id)
        except CatchmentPoint.DoesNotExist:
            return Response({'error': 'Punto no encontrado'}, status=status.HTTP_404_NOT_FOUND)

        try:
            year = int(request.query_params.get('year', timezone.now().year))
        except (ValueError, TypeError):
            year = timezone.now().year
        month = request.query_params.get('month')

        try:
            month_int = int(month) if month else None
        except (ValueError, TypeError):
            month_int = None

        qs = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__year=year,
        )
        if month_int:
            qs = qs.filter(date_time_medition__month=month_int)

        daily = (
            qs.annotate(dia=TruncDate('date_time_medition'))
            .values('dia')
            .annotate(
                consumo=Sum('total_diff'),
                caudal_promedio=Avg('flow'),
                caudal_max=Max('flow'),
                nivel_promedio=Avg('nivel'),
                total=Max('total'),
                registros=Count('id'),
            )
            .order_by('dia')
        )

        return self._json_response({
            'point_id': point.id,
            'point_title': point.title,
            'year': year,
            'month': month_int,
            'daily_data': list(daily),
        })

    @action(detail=False, methods=['get'], url_path='json/last-month')
    def json_last_month(self, request):
        """Reporte JSON del último mes completo por punto."""
        project_id, points = self._get_point_ids_from_params(request)
        if not points:
            return Response({'error': 'No hay puntos'}, status=status.HTTP_404_NOT_FOUND)

        from django.utils import timezone
        from datetime import timedelta
        today = timezone.now().date()
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        first_day_last_month = last_day_last_month.replace(day=1)

        point_ids = [p.id for p in points]
        daily = (
            InteractionDetail.objects
            .filter(
                catchment_point_id__in=point_ids,
                date_time_medition__date__gte=first_day_last_month,
                date_time_medition__date__lte=last_day_last_month,
            )
            .annotate(dia=TruncDate('date_time_medition'))
            .values('catchment_point_id', 'catchment_point__title', 'dia')
            .annotate(
                consumo=Sum('total_diff'),
                caudal_promedio=Avg('flow'),
                caudal_max=Max('flow'),
                nivel_promedio=Avg('nivel'),
                registros=Count('id'),
            )
            .order_by('catchment_point_id', 'dia')
        )

        return self._json_response(list(daily))

    @action(detail=False, methods=['get'], url_path='json/last-year')
    def json_last_year(self, request):
        """Reporte JSON del último año completo por punto (mensual)."""
        project_id, points = self._get_point_ids_from_params(request)
        if not points:
            return Response({'error': 'No hay puntos'}, status=status.HTTP_404_NOT_FOUND)

        from django.utils import timezone
        today = timezone.now().date()
        start_of_this_year = today.replace(month=1, day=1)
        start_of_last_year = (start_of_this_year - timedelta(days=1)).replace(month=1, day=1)
        end_of_last_year = start_of_this_year - timedelta(days=1)

        point_ids = [p.id for p in points]
        monthly = (
            InteractionDetail.objects
            .filter(
                catchment_point_id__in=point_ids,
                date_time_medition__date__gte=start_of_last_year,
                date_time_medition__date__lte=end_of_last_year,
            )
            .values('catchment_point_id', 'catchment_point__title')
            .annotate(
                mes=TruncDate('date_time_medition'),
                consumo=Sum('total_diff'),
                caudal_promedio=Avg('flow'),
                caudal_max=Max('flow'),
                nivel_promedio=Avg('nivel'),
                registros=Count('id'),
            )
            .order_by('catchment_point_id', 'mes')
        )

        return self._json_response(list(monthly))

    @action(detail=False, methods=['get'], url_path='json/annual-compressed')
    def json_annual_compressed(self, request):
        """Reporte JSON anual comprimido: resumen por punto del año actual."""
        project_id, points = self._get_point_ids_from_params(request)
        if not points:
            return Response({'error': 'No hay puntos'}, status=status.HTTP_404_NOT_FOUND)

        from django.utils import timezone
        today = timezone.now().date()
        start_of_year = today.replace(month=1, day=1)

        point_ids = [p.id for p in points]
        summary = (
            InteractionDetail.objects
            .filter(
                catchment_point_id__in=point_ids,
                date_time_medition__date__gte=start_of_year,
            )
            .values('catchment_point_id', 'catchment_point__title')
            .annotate(
                consumo_total=Sum('total_diff'),
                caudal_promedio=Avg('flow'),
                caudal_maximo=Max('flow'),
                nivel_promedio=Avg('nivel'),
                ultima_medicion=Max('date_time_medition'),
                registros=Count('id'),
            )
            .order_by('catchment_point_id')
        )

        return self._json_response(list(summary))
