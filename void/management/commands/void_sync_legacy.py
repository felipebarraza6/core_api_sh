"""Sync legacy CatchmentPoint records into void.

Además de crear Point/Device, ahora migra:
- Constantes del punto (d1..d6) desde ProfileDataConfigCatchment.
- Configuración de variables desde Variable (esquemas).
- Perfil de cumplimiento DGA desde DgaDataConfigCatchment.
"""
from collections import Counter
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand

from api.core.models import CatchmentPoint
from void.models import (
    ComplianceAuthority,
    Device,
    DeviceVariableConfig,
    Point,
    PointComplianceProfile,
    Provider,
)
from void.services.handlers.stateful_rulesets import apply_nivel_schema, apply_totalizer_schema


class Command(BaseCommand):
    help = "Sincroniza puntos legacy (CatchmentPoint) hacia void con config completa"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="No crear registros, solo mostrar lo que se haría.",
        )
        parser.add_argument(
            "--point-id",
            type=int,
            help="Sincronizar solo un punto legacy específico.",
        )
        parser.add_argument(
            "--project-legacy-id",
            type=int,
            help="Sincronizar solo puntos de un proyecto legacy (core_projectcatchments.id).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        point_id = options["point_id"]
        project_id = options["project_legacy_id"]

        qs = CatchmentPoint.objects.filter(is_active=True) if hasattr(CatchmentPoint, "is_active") else CatchmentPoint.objects.all()
        if point_id:
            qs = qs.filter(pk=point_id)
        if project_id:
            qs = qs.filter(project_id=project_id)

        if not dry_run:
            self._ensure_dga_authority()

        created_points = 0
        created_devices = 0
        updated_devices = 0
        created_configs = 0
        created_compliance = 0
        skipped = 0

        for cp in qs:
            if dry_run:
                skipped += 1
                continue

            point, point_created = self._sync_point(cp)
            if point_created:
                created_points += 1

            device, device_created = self._sync_device(cp, point)
            if device_created:
                created_devices += 1
            else:
                updated_devices += 1

            created_configs += self._sync_variable_configs(cp, device)
            created_compliance += self._sync_compliance(cp, point)

        if dry_run:
            self.stdout.write(self.style.NOTICE(f"Dry-run: {qs.count()} puntos legacy procesables."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sincronización completa: {created_points} puntos, "
                    f"{created_devices} devices creados, {updated_devices} devices actualizados, "
                    f"{created_configs} variable configs, {created_compliance} perfiles DGA, "
                    f"{skipped} omitidos."
                )
            )

    def _ensure_dga_authority(self):
        """Crea/actualiza ComplianceAuthority DGA desde variables de entorno.

        Las credenciales nunca se hardcodean; se leen de settings que a su vez
        vienen del entorno. Si no existen, se usan defaults inofensivos.
        """
        base_url = getattr(settings, "DGA_BASE_URL", "https://apimee.mop.gob.cl/api/v1")
        rut_empresa = getattr(settings, "DGA_DEFAULT_RUT_EMPRESA", "76944359-2")
        password = getattr(settings, "DGA_DEFAULT_PASSWORD", "")

        ComplianceAuthority.objects.update_or_create(
            code="dga",
            defaults={
                "name": "DGA",
                "protocol": "HTTP_REST",
                "auth_type": "JSON_BODY",
                "base_url": base_url,
                "auth_username": rut_empresa,
                "auth_password": password,
                "protocol_config": {
                    "subterraneo_endpoint": "/mediciones/subterraneas",
                    "superficial_endpoint": "/mediciones/superficiales/flujometro",
                    "default_rut_empresa": rut_empresa,
                },
            },
        )

    def _sync_point(self, cp: CatchmentPoint) -> tuple:
        """Crea/actualiza Point desde CatchmentPoint."""
        project_name = ""
        client_name = ""
        try:
            project_name = cp.project.name or ""
        except Exception:
            pass
        try:
            client_name = cp.owner_user.get_full_name() or cp.owner_user.username or ""
        except Exception:
            pass

        constants = self._build_constants(cp)

        defaults = {
            "name": cp.title or f"Punto {cp.id}",
            "code_internal": cp.title or "",
            "frequency_minutes": self._parse_frequency(cp.frecuency),
            "lat": cp.lat or "",
            "lon": cp.lon or "",
            "client": client_name,
            "project": project_name,
            "constants": constants,
            "migration_status": "shadow",
        }
        return Point.objects.update_or_create(legacy_point=cp, defaults=defaults)

    def _sync_device(self, cp: CatchmentPoint, point: Point) -> tuple:
        """Crea/actualiza Device asociado al Point."""
        void_provider = self._resolve_void_provider(cp)
        external_id = self._resolve_external_id(cp)
        variables = self._infer_variables(cp)

        defaults = {
            "is_active": True,
            "provider": void_provider,
            "external_id": external_id or "",
            "configuration": {
                "variables": variables,
                "legacy_provider_id": cp.telemetry_provider_id,
                "legacy_source": self._provider_source(cp),
            },
        }
        return Device.objects.update_or_create(point=point, defaults=defaults)

    def _sync_variable_configs(self, cp: CatchmentPoint, device: Device) -> int:
        """Crea DeviceVariableConfig por cada Variable legacy del punto."""
        from api.core.models import Variable as LegacyVariable

        scheme_ids = cp.schemes.values_list("id", flat=True)
        legacy_vars = LegacyVariable.objects.filter(scheme_catchment_id__in=scheme_ids)
        profile = cp.data_config_profiles.first()

        created = 0
        has_caudal_promedio = False
        for lv in legacy_vars:
            source = lv.str_variable or lv.type_variable or ""
            if not source:
                continue

            legacy_type = (lv.type_variable or "").upper()
            if legacy_type == "CAUDAL_PROMEDIO":
                # En void el caudal promedio se calcula como derivada del
                # totalizador stateful; no se crea una variable separada.
                has_caudal_promedio = True
                continue

            internal, processing_type = self._map_variable_type(lv.type_variable)
            pulses_factor = lv.pulses_factor or 1000

            defaults = {
                "internal_variable": internal,
                "processing_type": processing_type,
                "pulses_factor": pulses_factor,
                "is_active": True,
            }

            if processing_type == "formula":
                defaults["formula"] = self._build_formula(lv, profile)
                defaults["offset"] = self._variable_offset(lv, profile)

            config, created_flag = DeviceVariableConfig.objects.update_or_create(
                device=device,
                source_variable=source,
                defaults=defaults,
            )

            if processing_type == "stateful" and created_flag:
                if internal == "nivel":
                    apply_nivel_schema(
                        device=device,
                        source_variable=source,
                        internal_variable=internal,
                        offset=float(self._variable_offset(lv, profile)),
                        calculate_nivel=lv.calculate_nivel or 1,
                    )
                else:
                    apply_totalizer_schema(
                        device=device,
                        source_variable=source,
                        internal_variable=internal,
                        pulses_factor=pulses_factor,
                    )

            if created_flag:
                created += 1

        # Si el esquema legacy tenía CAUDAL_PROMEDIO, activamos compute_flow
        # en el totalizador stateful del device.
        if has_caudal_promedio:
            totalizer_config = device.variable_configs.filter(
                processing_type="stateful",
            ).first()
            if totalizer_config and not totalizer_config.compute_flow:
                totalizer_config.compute_flow = True
                totalizer_config.save(update_fields=["compute_flow"])

        return created

    def _sync_compliance(self, cp: CatchmentPoint, point: Point) -> int:
        """Crea PointComplianceProfile para DGA si está activo en legacy."""
        from void.models import ComplianceStandard

        dga_cfg = cp.dga_data_config_profiles.filter(send_dga=True).first()
        if not dga_cfg:
            return 0

        authority = ComplianceAuthority.objects.get(code="dga")

        extra_config = {}
        point_password = ""
        if hasattr(dga_cfg, "password_dga_software"):
            point_password = dga_cfg.password_dga_software or ""
        if point_password:
            extra_config["password"] = point_password

        informant_name = ""
        if hasattr(dga_cfg, "name_informant"):
            informant_name = dga_cfg.name_informant or ""

        standard_code = (dga_cfg.standard or "SIN_ESTANDAR").strip().upper()
        try:
            standard = ComplianceStandard.objects.get(code=standard_code)
        except ComplianceStandard.DoesNotExist:
            standard = ComplianceStandard.objects.get(code="SIN_ESTANDAR")

        type_key = (dga_cfg.type_dga or "SUBTERRANEO").strip().upper()

        _, created = PointComplianceProfile.objects.update_or_create(
            point=point,
            authority=authority,
            defaults={
                "is_active": True,
                "external_code": dga_cfg.code_dga or "",
                "type_key": type_key,
                "standard": standard,
                "standard_legacy": standard_code,
                "flow_granted": dga_cfg.flow_granted_dga or 0,
                "informant_rut": dga_cfg.rut_report_dga or "",
                "informant_name": informant_name,
                "variable_mapping": {
                    "total": "total",
                    "flow": "flow",
                    "water_table": "water_table",
                },
                "extra_config": extra_config,
            },
        )
        return 1 if created else 0

    def _build_constants(self, cp: CatchmentPoint) -> dict:
        """Extrae d1..d6 desde ProfileDataConfigCatchment."""
        data_cfg = cp.data_config_profiles.first()
        if not data_cfg:
            return {}
        return {
            "d1": float(data_cfg.d1 or 0),
            "d2": float(data_cfg.d2 or 0),
            "d3": float(data_cfg.d3 or 0),
            "d4": float(data_cfg.d4 or 0),
            "d5": float(data_cfg.d5 or 0),
            "d6": data_cfg.d6 or 0,
            "max_diff_m3_per_hour": float(data_cfg.max_diff_m3_per_hour or 500),
            "max_flow_ls": float(data_cfg.max_flow_ls or 150),
            "max_time_gap_hours": float(data_cfg.max_time_gap_hours or 2),
            "reconnection_threshold_hours": float(data_cfg.reconnection_threshold_hours or 2),
            "addition": float(data_cfg.addition or 0),
            "nivel_offset": float(data_cfg.nivel_offset or 0),
        }

    def _map_variable_type(self, legacy_type: str) -> tuple:
        """Mapea tipo_variable legacy a internal_variable + processing_type de void."""
        if not legacy_type:
            return ("value", "none")
        lt = legacy_type.upper()
        if lt == "TOTALIZADO":
            return ("pulses", "stateful")
        if lt == "CAUDAL":
            return ("flow", "formula")
        if lt == "NIVEL":
            return ("nivel", "stateful")
        if lt == "CAUDAL_PROMEDIO":
            return ("flow", "formula")
        return (legacy_type.lower(), "formula")

    def _build_formula(self, lv, profile=None) -> str:
        """Construye fórmula que replica el cálculo legacy para la variable.

        Soporta:
        - NIVEL: ``(abs(value) + offset) / calculate_nivel`` (replica ``nivel_mt``).
        - CAUDAL/CAUDAL_PROMEDIO: divisor de escala ``calculate_nivel`` y
          conversión a L/s (``/ 3.6``) cuando ``convert_to_lt`` es True.

        Nota: ``CAUDAL_PROMEDIO`` real requiere derivada del totalizador;
        esta fórmula genera el caudal instantáneo equivalente. Se documenta
        como gap en ``docs/void/MILESTONE_2.md``.
        """
        legacy_type = (lv.type_variable or "").upper()
        calculate_nivel = lv.calculate_nivel or 0
        convert_to_lt = lv.convert_to_lt

        if legacy_type == "NIVEL":
            # Legacy: nivel_mt(abs(raw) + nivel_offset, calculate_nivel)
            base = "(abs(value) + offset)"
            if calculate_nivel and calculate_nivel > 0:
                return f"{base} / {calculate_nivel}"
            return base

        # CAUDAL / CAUDAL_PROMEDIO: replicar instantaneous_flow
        divisor = 1.0
        if calculate_nivel and calculate_nivel > 0:
            divisor *= float(calculate_nivel)
        if convert_to_lt:
            divisor *= 3.6

        if divisor != 1.0:
            return f"value / {divisor}"
        return "value"

    def _variable_offset(self, lv, profile) -> Decimal:
        """Offset específico de la variable según tipo legacy.

        NIVEL usa ``ProfileDataConfigCatchment.nivel_offset``; el resto usa 0.
        """
        from api.core.models import ProfileDataConfigCatchment

        legacy_type = (lv.type_variable or "").upper()
        if legacy_type == "NIVEL" and isinstance(profile, ProfileDataConfigCatchment):
            return Decimal(profile.nivel_offset or 0)
        return Decimal(0)

    def _resolve_void_provider(self, cp: CatchmentPoint) -> Provider | None:
        """Busca proveedor void equivalente al legacy."""
        legacy_provider_id = cp.telemetry_provider_id
        if legacy_provider_id:
            try:
                return Provider.objects.get(metadata__legacy_provider_id=legacy_provider_id)
            except Provider.DoesNotExist:
                pass
            try:
                legacy = cp.telemetry_provider
                return Provider.objects.get(name=legacy.name)
            except (AttributeError, Provider.DoesNotExist):
                pass
        return None

    def _resolve_external_id(self, cp: CatchmentPoint) -> str:
        """Obtiene token/device id más frecuente del punto."""
        from api.core.models import Variable as LegacyVariable

        tokens = list(
            cp.data_config_profiles.exclude(token_service__isnull=True)
            .exclude(token_service="")
            .values_list("token_service", flat=True)
        )
        if not tokens:
            scheme_ids = cp.schemes.values_list("id", flat=True)
            tokens = list(
                LegacyVariable.objects.filter(
                    scheme_catchment_id__in=scheme_ids,
                    provider__isnull=False,
                )
                .exclude(token_service__isnull=True)
                .exclude(token_service="")
                .values_list("token_service", flat=True)
            )
        if not tokens:
            return ""
        most_common, _ = Counter(tokens).most_common(1)[0]
        return most_common or ""

    def _provider_source(self, cp: CatchmentPoint) -> str:
        if cp.telemetry_provider_id:
            return "telemetry_provider_fk"
        if cp.is_tdata:
            return "is_tdata_flag"
        if cp.is_thethings:
            return "is_thethings_flag"
        if cp.is_novus:
            return "is_novus_flag"
        return "unknown"

    def _parse_frequency(self, value):
        try:
            return int(value)
        except (ValueError, TypeError):
            return 60

    def _infer_variables(self, catchment_point):
        """Infiere variables básicas según tipo de punto."""
        from api.core.models import Variable as LegacyVariable

        variables = ["pulses"]
        if catchment_point.is_novus:
            variables.extend(["nivel"])
        scheme_ids = catchment_point.schemes.values_list("id", flat=True)
        legacy_vars = (
            LegacyVariable.objects.filter(scheme_catchment_id__in=scheme_ids)
            .exclude(str_variable__isnull=True)
            .exclude(str_variable="")
            .values_list("str_variable", flat=True)
        )
        for v in legacy_vars:
            if v and v not in variables:
                variables.append(v)
        return variables
