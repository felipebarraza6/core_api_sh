from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from datetime import datetime
import pytz

from api.core.models import CatchmentPoint, InteractionDetail, Variable

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
            last_interaction = InteractionDetail.objects.filter(
                catchment_point=point
            ).order_by('-date_time_medition').first()

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
