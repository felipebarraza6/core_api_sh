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
from api.core.reports.excel_generator import (
    generate_excel_by_project,
    generate_excel_by_point,
    generate_excel_last_month_by_points,
    generate_excel_last_year_by_points,
    generate_excel_annual_compressed,
)

from rest_framework.authentication import SessionAuthentication, BasicAuthentication


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


class ReportsGenerationViewSet(viewsets.ViewSet):
    """
    ViewSet para generar reportes Excel y PDF desde el frontend.

    Endpoints:
    - GET /api/reports/by-project/?project_id=1
    - GET /api/reports/by-point/?point_id=1&year=2025&month=5
    - GET /api/reports/last-month/?project_id=1
    - GET /api/reports/last-year/?project_id=1
    - GET /api/reports/annual-compressed/?project_id=1
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

        year = int(year) if year else None
        month = int(month) if month else None

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
            point_ids = [int(x.strip()) for x in point_ids_str.split(',') if x.strip()]

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
            point_ids = [int(x.strip()) for x in point_ids_str.split(',') if x.strip()]

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
            point_ids = [int(x.strip()) for x in point_ids_str.split(',') if x.strip()]

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
