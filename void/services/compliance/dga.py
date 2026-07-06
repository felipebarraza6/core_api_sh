"""DGA compliance adapter for void."""
import json
import re

import requests
from django.db import models

from void.models import ComplianceSubmission, DeviceVariableConfig, ProcessedReading

from .base import BaseComplianceAdapter, ComplianceResult
from .registry import ComplianceAdapterRegistry


@ComplianceAdapterRegistry.register("dga")
class DGAComplianceAdapter(BaseComplianceAdapter):
    """Adaptador para envío de mediciones a DGA (apimee.mop.gob.cl)."""

    code = "dga"

    def _to_int_total(self, value) -> int:
        """Convierte total a entero, agregando puntos si aplica."""
        try:
            return int(value)
        except (ValueError, TypeError):
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return 0

    def _aggregate_total(self, profile, reading) -> int:
        """Suma totales de puntos agregados al total del reading principal."""
        total = self._to_int_total(reading.total)
        aggregate_point_ids = profile.aggregate_points or []
        if not aggregate_point_ids:
            return total

        extra = 0.0
        for pid in aggregate_point_ids:
            try:
                last = ProcessedReading.objects.filter(
                    device__point_id=pid,
                ).order_by("-timestamp").first()
                if last and last.total is not None:
                    extra += float(last.total)
            except Exception:
                continue
        return int(total + extra)

    def _resolve_for_timestamp(self, profile, reading, field: str):
        """Resuelve un campo del payload buscando en readings del mismo timestamp.

        ``ProcessedReading`` es por variable, por lo que un reading de ``total``
        puede no tener ``flow``/``water_table``. Este método busca otras
        lecturas procesadas del mismo device + timestamp cuya config apunte al
        campo solicitado. Si no encuentra ``water_table`` pero encuentra
        ``nivel`` y la constante ``d3`` del punto, calcula ``d3 - nivel``.
        """
        value = profile.resolve_value(reading, field)
        if value is not None and value != 0 and value != "0":
            return value

        mapped = (profile.variable_mapping or {}).get(field, field)
        target_fields = [mapped]
        # water_table se calcula frecuentemente a partir de nivel.
        if mapped == "water_table":
            target_fields.append("nivel")

        configs = DeviceVariableConfig.objects.filter(
            device=reading.device,
            is_active=True,
        ).filter(
            models.Q(output_field__in=target_fields)
            | models.Q(internal_variable__in=target_fields)
        )

        def _find_reading(cfg):
            """Busca lectura del mismo timestamp o la más cercana dentro de 5s."""
            from datetime import timedelta
            qs = ProcessedReading.objects.filter(
                device=reading.device,
                variable=cfg.source_variable,
            )
            exact = qs.filter(timestamp=reading.timestamp).first()
            if exact:
                return exact
            window = timedelta(seconds=5)
            candidates = list(qs.filter(
                timestamp__gte=reading.timestamp - window,
                timestamp__lte=reading.timestamp + window,
            ))
            if not candidates:
                return None
            return min(candidates, key=lambda r: abs((r.timestamp - reading.timestamp).total_seconds()))

        nivel_value = None
        for cfg in configs:
            other = _find_reading(cfg)
            if not other:
                continue
            for target in target_fields:
                candidate = getattr(other, target, None)
                if candidate is not None:
                    if target == "nivel":
                        nivel_value = candidate
                    if mapped == "water_table" and target == "nivel":
                        continue
                    return candidate
                candidate = (other.extra_values or {}).get(target)
                if candidate is not None:
                    if target == "nivel":
                        nivel_value = candidate
                    if mapped == "water_table" and target == "nivel":
                        continue
                    return candidate

        # Fallback: calcular water_table desde nivel y d3.
        if mapped == "water_table" and nivel_value is not None:
            d3 = (reading.device.point.constants or {}).get("d3")
            if d3 is not None and float(d3) > 0:
                result = float(d3) - float(nivel_value)
                if result >= 0:
                    return result

        return value

    def build_payload(
        self,
        profile,
        reading,
        aggregate_readings=None,
    ) -> dict:
        """Construye payload DGA para SUBTERRANEO o SUPERFICIAL."""
        protocol_config = self.authority.protocol_config or {}
        cfg = protocol_config

        timestamp = reading.timestamp
        fecha = timestamp.strftime("%Y-%m-%d")
        hora = timestamp.strftime("%H:%M:%S")
        timestamp_origen = timestamp.strftime("%Y-%m-%dT%H:%M:%S")

        totalizador = self._aggregate_total(profile, reading)
        flow = round(float(self._resolve_for_timestamp(profile, reading, "flow") or 0), 2)
        water_table = float(self._resolve_for_timestamp(profile, reading, "water_table") or 0)

        if flow is None or flow < 0:
            flow = 0.0
        if water_table is None or water_table < 0:
            water_table = 0.0

        rut = profile.informant_rut or self.authority.auth_username
        password = profile.extra_config.get("password") or self.authority.auth_password
        rut_empresa = cfg.get("default_rut_empresa") or self.authority.auth_username

        type_dga = (profile.type_key or "SUBTERRANEO").upper()

        payload = {
            "_type_dga": type_dga,
            "_codigo_obra": profile.external_code or "",
            "_timestamp_origen": timestamp_origen,
            "autenticacion": {
                "password": password,
                "rutUsuario": rut,
                "rutEmpresa": rut_empresa,
            }
        }

        if type_dga == "SUBTERRANEO":
            payload["medicionSubterranea"] = {
                "caudal": str(flow),
                "fechaMedicion": fecha,
                "horaMedicion": hora,
                "totalizador": str(totalizador),
                "nivelFreaticoDelPozo": str(water_table),
            }
        else:
            payload["medicionSuperficialFlujometro"] = {
                "caudal": str(flow),
                "fechaMedicion": fecha,
                "horaMedicion": hora,
                "totalizador": str(totalizador),
            }

        return payload

    def send(self, payload: dict) -> ComplianceResult:
        """Envía payload a DGA y retorna resultado interpretado."""
        protocol_config = self.authority.protocol_config or {}
        cfg = protocol_config
        base_url = self.authority.base_url or "https://apimee.mop.gob.cl/api/v1"

        type_dga = payload.get("_type_dga", "SUBTERRANEO")
        if type_dga == "SUBTERRANEO":
            endpoint = cfg.get("subterraneo_endpoint", "/mediciones/subterraneas")
        else:
            endpoint = cfg.get("superficial_endpoint", "/mediciones/superficiales/flujometro")

        url = f"{base_url.rstrip('/')}{endpoint}"

        # Headers legacy de DGA usan codigoObra y timeStampOrigen.
        codigo_obra = payload.get("_codigo_obra", "")
        timestamp_origen = payload.get("_timestamp_origen", "")
        headers = {
            "codigoObra": codigo_obra,
            "timeStampOrigen": timestamp_origen,
            "Content-Type": "application/json",
        }

        last_exception = None
        for attempt in range(self.authority.retry_attempts or 1):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=self.authority.timeout_seconds or 10,
                )
                return self.handle_response(response.status_code, response.text)
            except requests.RequestException as exc:
                last_exception = exc
                continue

        return ComplianceResult(
            success=False,
            status="failed",
            response_body=str(last_exception) if last_exception else "",
            error_message=f"Error de conexión tras {self.authority.retry_attempts} intentos",
        )

    def handle_response(self, response_status: int, response_body: str) -> ComplianceResult:
        """Interpreta respuesta DGA incluyendo duplicados e irrecuperables."""
        if response_status == 200:
            voucher = ""
            try:
                data = json.loads(response_body)
                # DGA retorna comprobante en distintas formas según endpoint.
                voucher = data.get("comprobante") or data.get("n_voucher") or data.get("id") or ""
            except Exception:
                pass
            return ComplianceResult(
                success=True,
                status="confirmed",
                response_status=response_status,
                response_body=response_body,
                voucher=str(voucher),
            )

        if response_status == 400:
            try:
                error_data = json.loads(response_body)
                message = error_data.get("message", "")
            except Exception:
                message = response_body

            if "Ya existe un registro" in message and "Comprobante:" in message:
                match = re.search(r"Comprobante: ([^\s\"']+)", message)
                voucher = match.group(1) if match else "Duplicado"
                return ComplianceResult(
                    success=True,
                    status="duplicate",
                    response_status=response_status,
                    response_body=response_body,
                    voucher=voucher,
                )

            if "Usuario no es el informante registrado en la Obra" in message:
                return ComplianceResult(
                    success=False,
                    status="unrecoverable",
                    response_status=response_status,
                    response_body=response_body,
                    error_message=message,
                )

            return ComplianceResult(
                success=False,
                status="failed",
                response_status=response_status,
                response_body=response_body,
                error_message=message or "Error 400",
            )

        return ComplianceResult(
            success=False,
            status="failed",
            response_status=response_status,
            response_body=response_body,
            error_message=f"HTTP {response_status}",
        )
