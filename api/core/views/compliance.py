"""Vistas para consultas de cumplimiento regulatorio (DGA/SMA)."""

import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from api.core.authentication import BearerTokenAuthentication
from django.conf import settings

from api.core.utils.compliance import ComplianceConfig
from api.core.models import InteractionDetail


class DgaComprobanteVerifyView(APIView):
    """
    Consulta el estado de un comprobante DGA en los registros internos.

    Como la API externa del MOP no siempre responde o puede bloquear
    peticiones, este endpoint devuelve los datos que SmartHydro envió a
    la DGA para el comprobante consultado.

    Parámetros GET:
        - codigo_obra: Código de obra DGA (ej. OB-0101-103)
        - numero_comprobante: Comprobante retornado por DGA
        - tipo_dga: SUPERFICIAL o SUBTERRANEO (default SUPERFICIAL)
    """
    authentication_classes = [BearerTokenAuthentication, SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        codigo_obra = request.GET.get('codigo_obra')
        numero_comprobante = request.GET.get('numero_comprobante')
        tipo_dga = request.GET.get('tipo_dga', 'SUPERFICIAL').upper()

        if not numero_comprobante:
            return Response(
                {"error": "Se requiere 'numero_comprobante'."},
                status=400
            )

        if tipo_dga not in ('SUPERFICIAL', 'SUBTERRANEO'):
            return Response(
                {"error": "tipo_dga debe ser SUPERFICIAL o SUBTERRANEO."},
                status=400
            )

        # Buscar en nuestra base de datos el registro con ese comprobante
        filters = {"n_voucher": numero_comprobante}
        if codigo_obra:
            filters["catchment_point__dga_data_config_profiles__code_dga"] = codigo_obra
        registros = InteractionDetail.objects.filter(
            **filters
        ).select_related('catchment_point').distinct().order_by('-date_time_medition')

        if not registros.exists():
            return Response(
                {
                    "status": "01",
                    "message": "No se encontró el comprobante en los registros enviados a la DGA.",
                    "data": None,
                },
                status=404
            )

        registro = registros.first()

        # Extraer fecha y hora de date_time_medition
        fecha_medicion = ""
        hora_medicion = ""
        if registro.date_time_medition:
            fecha_medicion = registro.date_time_medition.strftime("%d-%m-%Y")
            hora_medicion = registro.date_time_medition.strftime("%H:%M:%S")

        data = {
            "caudal": str(registro.flow) if registro.flow is not None else "0.00",
            "fechaMedicion": fecha_medicion,
            "horaMedicion": hora_medicion,
            "totalizador": str(registro.total) if registro.total else "0",
        }

        if tipo_dga == 'SUBTERRANEO':
            data["nivelFreaticoDelPozo"] = (
                str(registro.water_table) if registro.water_table is not None else "0.00"
            )

        return Response({
            "status": "00",
            "message": "Comprobante encontrado en registros internos.",
            "data": data,
            "meta": {
                "codigo_obra": codigo_obra,
                "numero_comprobante": numero_comprobante,
                "tipo_dga": tipo_dga,
                "punto": registro.catchment_point.title if registro.catchment_point else None,
                "punto_id": registro.catchment_point_id,
                "enviado_dga": not registro.send_dga,
                "is_error": registro.is_error,
                "return_dga": registro.return_dga,
            }
        }, status=200)
