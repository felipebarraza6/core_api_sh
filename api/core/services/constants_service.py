"""
Servicio de Constantes Históricas
Permite editar data histórica y aplicar constantes por rangos de fechas
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from django.db import transaction
from django.utils import timezone
from django.db.models import Q, F

from ..models import (
    ConstantDefinition, ConstantApplication, DataCorrectionLog,
    DataPoint, IoTDevice, CatchmentPoint
)

logger = logging.getLogger(__name__)


class ConstantsService:
    """
    Servicio para gestión de constantes históricas y edición de data
    """

    @staticmethod
    def apply_constant_to_historical_data(
        constant: ConstantDefinition,
        start_date: datetime,
        end_date: Optional[datetime] = None,
        user=None
    ) -> Dict[str, any]:
        """
        Aplicar una constante a datos históricos en un rango de fechas
        """
        try:
            logger.info(f"Applying constant {constant.code} to historical data from {start_date} to {end_date}")

            # Crear aplicación de constante
            application = ConstantApplication.objects.create(
                constant=constant,
                start_date=start_date,
                end_date=end_date,
                applied_by=user,
                change_reason=f"Applied constant {constant.name} to historical data",
                auto_recalculate=True
            )

            # Ejecutar recálculo
            result = ConstantsService._recalculate_historical_data(application)

            # Actualizar estado de la aplicación
            application.records_affected = result['records_affected']
            application.recalculation_status = 'COMPLETED' if result['success'] else 'FAILED'
            if not result['success']:
                application.recalculation_errors = '; '.join(result['errors'])
            application.save()

            logger.info(f"Constant application completed: {result['records_affected']} records affected")

            return {
                'success': True,
                'application_id': application.id,
                'records_affected': result['records_affected'],
                'errors': result.get('errors', [])
            }

        except Exception as exc:
            logger.error(f"Failed to apply constant to historical data: {exc}")
            return {
                'success': False,
                'error': str(exc)
            }

    @staticmethod
    def _recalculate_historical_data(application: ConstantApplication) -> Dict[str, any]:
        """
        Recalcular datos históricos afectados por una aplicación de constante
        """
        try:
            constant = application.constant
            affected_start, affected_end = application.get_affected_date_range()

            # Encontrar DataPoints afectados
            affected_points = DataPoint.objects.filter(
                Q(device=constant.device) if constant.device else
                Q(point=constant.point) if constant.point else
                Q(),  # Global
                collected_at__gte=affected_start,
                collected_at__lte=affected_end
            ).select_related('stream', 'device')

            records_affected = 0
            errors = []

            # Procesar en batches para evitar memory issues
            batch_size = 100
            for i in range(0, affected_points.count(), batch_size):
                batch = affected_points[i:i+batch_size]

                for data_point in batch:
                    try:
                        ConstantsService._recalculate_single_data_point(data_point, application)
                        records_affected += 1

                    except Exception as exc:
                        error_msg = f"Failed to recalculate point {data_point.id}: {exc}"
                        logger.error(error_msg)
                        errors.append(error_msg)

            return {
                'success': True,
                'records_affected': records_affected,
                'errors': errors
            }

        except Exception as exc:
            logger.error(f"Failed to recalculate historical data: {exc}")
            return {
                'success': False,
                'records_affected': 0,
                'errors': [str(exc)]
            }

    @staticmethod
    def _recalculate_single_data_point(data_point: DataPoint, application: ConstantApplication):
        """
        Recalcular un punto de dato individual aplicando la constante
        """
        constant = application.constant
        original_value = data_point.processed_value

        if original_value is None:
            return  # No hay valor procesado para recalcular

        # Aplicar la constante según su tipo
        new_value = ConstantsService._apply_constant_to_value(
            float(original_value), constant
        )

        if new_value != original_value:
            # Crear log de corrección
            DataCorrectionLog.objects.create(
                original_record=data_point,
                original_raw_value=data_point.raw_value,
                original_processed_value=original_value,
                corrected_processed_value=new_value,
                correction_type='CONSTANT_CHANGE',
                correction_reason=f"Applied constant {constant.name} ({constant.code})",
                corrected_by=application.applied_by,
                correction_metadata={
                    'constant_id': constant.id,
                    'constant_value': float(constant.value_numeric),
                    'application_id': application.id,
                    'previous_value': float(original_value),
                    'new_value': float(new_value)
                }
            )

            # Actualizar el punto de dato
            data_point.processed_value = new_value
            data_point.save(update_fields=['processed_value'])

    @staticmethod
    def _apply_constant_to_value(value: float, constant: ConstantDefinition) -> float:
        """
        Aplicar una constante a un valor según su tipo
        """
        constant_value = float(constant.value_numeric)

        if constant.constant_type == 'TOTALIZER_OFFSET':
            return value + constant_value
        elif constant.constant_type == 'FLOW_MULTIPLIER':
            return value * constant_value
        elif constant.constant_type == 'LEVEL_OFFSET':
            return value + constant_value
        elif constant.constant_type == 'BATTERY_CALIBRATION':
            # Calibración especial para batería
            return max(0, min(100, value + constant_value))
        elif constant.constant_type == 'CONVERSION_FACTOR':
            return value * constant_value
        else:
            # Para constantes personalizadas, aplicar como offset por defecto
            return value + constant_value

    @staticmethod
    def edit_historical_data_point(
        data_point_id: str,
        new_raw_value: str = None,
        new_processed_value: float = None,
        correction_reason: str = "",
        user=None
    ) -> Dict[str, any]:
        """
        Editar manualmente un punto de dato histórico
        """
        try:
            data_point = DataPoint.objects.get(data_point_id=data_point_id)

            # Guardar valores originales
            original_raw = data_point.raw_value
            original_processed = data_point.processed_value

            # Aplicar cambios
            updates = {}
            if new_raw_value is not None:
                data_point.raw_value = new_raw_value
                updates['raw_value'] = new_raw_value

            if new_processed_value is not None:
                data_point.processed_value = new_processed_value
                updates['processed_value'] = new_processed_value

            # Crear log de corrección
            DataCorrectionLog.objects.create(
                original_record=data_point,
                original_raw_value=original_raw,
                original_processed_value=original_processed,
                corrected_raw_value=new_raw_value or original_raw,
                corrected_processed_value=new_processed_value if new_processed_value is not None else original_processed,
                correction_type='MANUAL_EDIT',
                correction_reason=correction_reason or "Manual data correction",
                corrected_by=user,
                correction_metadata={
                    'changes': list(updates.keys()),
                    'manual_edit': True
                }
            )

            # Guardar cambios
            data_point.save(update_fields=list(updates.keys()) + ['updated_at'])

            logger.info(f"Manual edit applied to data point {data_point_id}")

            return {
                'success': True,
                'data_point_id': data_point_id,
                'changes': updates
            }

        except DataPoint.DoesNotExist:
            return {
                'success': False,
                'error': f'Data point {data_point_id} not found'
            }
        except Exception as exc:
            logger.error(f"Failed to edit historical data point: {exc}")
            return {
                'success': False,
                'error': str(exc)
            }

    @staticmethod
    def get_applicable_constants_for_point(
        device: IoTDevice = None,
        point: CatchmentPoint = None,
        timestamp: datetime = None
    ) -> List[ConstantDefinition]:
        """
        Obtener constantes aplicables para un punto/dispositivo en un timestamp
        """
        if timestamp is None:
            timestamp = timezone.now()

        # Construir query para constantes aplicables
        query = Q(
            constantapplication__is_active=True,
            constantapplication__start_date__lte=timestamp,
        ) & (
            Q(constantapplication__end_date__gte=timestamp) |
            Q(constantapplication__end_date__isnull=True)
        )

        # Aplicar scope (device > point > global)
        if device:
            query &= Q(Q(device=device) | Q(point=device.catchment_point) | (Q(device__isnull=True) & Q(point__isnull=True)))
        elif point:
            query &= Q(Q(point=point) | (Q(device__isnull=True) & Q(point__isnull=True)))
        else:
            query &= Q(device__isnull=True, point__isnull=True)

        # Obtener constantes ordenadas por prioridad
        constants = ConstantDefinition.objects.filter(query).distinct().order_by('-priority')

        return list(constants)

    @staticmethod
    def create_constant_range_application(
        constant: ConstantDefinition,
        start_date: datetime,
        end_date: Optional[datetime],
        applied_by=None,
        reason: str = ""
    ) -> Dict[str, any]:
        """
        Crear una aplicación de constante para un rango específico de fechas
        """
        try:
            # Validar que no haya solapamiento con aplicaciones existentes
            overlapping = ConstantApplication.objects.filter(
                constant=constant,
                is_active=True,
                start_date__lt=end_date if end_date else timezone.now() + timedelta(days=365),
                end_date__gt=start_date
            )

            if overlapping.exists():
                return {
                    'success': False,
                    'error': f'Constant application overlaps with existing applications: {[app.id for app in overlapping]}'
                }

            # Crear aplicación
            application = ConstantApplication.objects.create(
                constant=constant,
                start_date=start_date,
                end_date=end_date,
                applied_by=applied_by,
                change_reason=reason or f"Constant {constant.name} applied to date range",
                auto_recalculate=True
            )

            # Si es para aplicar inmediatamente, ejecutar recálculo
            if application.auto_recalculate:
                result = ConstantsService._recalculate_historical_data(application)

                application.records_affected = result['records_affected']
                application.recalculation_status = 'COMPLETED' if result['success'] else 'FAILED'
                if not result['success']:
                    application.recalculation_errors = '; '.join(result['errors'])
                application.save()

            return {
                'success': True,
                'application_id': application.id,
                'records_affected': application.records_affected,
                'status': application.recalculation_status
            }

        except Exception as exc:
            logger.error(f"Failed to create constant range application: {exc}")
            return {
                'success': False,
                'error': str(exc)
            }

    @staticmethod
    def bulk_edit_historical_data(
        filters: Dict,
        transformation: Dict,
        reason: str = "",
        user=None
    ) -> Dict[str, any]:
        """
        Editar múltiples puntos de datos históricos en bulk
        """
        try:
            # Construir query de filtros
            query = Q()

            if 'device_id' in filters:
                query &= Q(device__device_id=filters['device_id'])

            if 'point_id' in filters:
                query &= Q(point_id=filters['point_id'])

            if 'start_date' in filters:
                query &= Q(collected_at__gte=filters['start_date'])

            if 'end_date' in filters:
                query &= Q(collected_at__lte=filters['end_date'])

            if 'stream_code' in filters:
                query &= Q(stream__code=filters['stream_code'])

            # Obtener puntos a editar
            data_points = DataPoint.objects.filter(query).select_related('stream', 'device')

            edited_count = 0
            errors = []

            # Procesar en batches
            batch_size = 50
            for i in range(0, data_points.count(), batch_size):
                batch = data_points[i:i+batch_size]

                for data_point in batch:
                    try:
                        # Aplicar transformación
                        changes = ConstantsService._apply_bulk_transformation(data_point, transformation)

                        if changes:
                            # Crear log de corrección
                            DataCorrectionLog.objects.create(
                                original_record=data_point,
                                original_raw_value=data_point.raw_value,
                                original_processed_value=data_point.processed_value,
                                corrected_raw_value=data_point.raw_value,  # No cambia raw
                                corrected_processed_value=data_point.processed_value,
                                correction_type='MANUAL_EDIT',
                                correction_reason=f"Bulk edit: {reason}",
                                corrected_by=user,
                                correction_metadata={
                                    'bulk_edit': True,
                                    'transformation': transformation,
                                    'changes': changes
                                }
                            )

                            # Guardar cambios
                            update_fields = list(changes.keys()) + ['updated_at']
                            data_point.save(update_fields=update_fields)

                            edited_count += 1

                    except Exception as exc:
                        error_msg = f"Failed to edit point {data_point.id}: {exc}"
                        logger.error(error_msg)
                        errors.append(error_msg)

            return {
                'success': True,
                'records_edited': edited_count,
                'errors': errors
            }

        except Exception as exc:
            logger.error(f"Bulk edit failed: {exc}")
            return {
                'success': False,
                'error': str(exc)
            }

    @staticmethod
    def _apply_bulk_transformation(data_point: DataPoint, transformation: Dict) -> Dict:
        """
        Aplicar transformación bulk a un punto de dato
        """
        changes = {}

        if 'add_offset' in transformation and data_point.processed_value is not None:
            offset = float(transformation['add_offset'])
            data_point.processed_value += offset
            changes['processed_value'] = data_point.processed_value

        if 'multiply_factor' in transformation and data_point.processed_value is not None:
            factor = float(transformation['multiply_factor'])
            data_point.processed_value *= factor
            changes['processed_value'] = data_point.processed_value

        if 'set_quality' in transformation:
            new_quality = transformation['set_quality']
            if new_quality in ['EXCELLENT', 'GOOD', 'FAIR', 'POOR', 'INVALID']:
                data_point.quality = new_quality
                changes['quality'] = new_quality

        return changes

    @staticmethod
    def validate_constant_range(
        constant: ConstantDefinition,
        start_date: datetime,
        end_date: Optional[datetime]
    ) -> Tuple[bool, str]:
        """
        Validar que un rango de constante no tenga conflictos
        """
        try:
            # Verificar solapamientos
            overlapping = ConstantApplication.objects.filter(
                constant=constant,
                is_active=True,
                start_date__lt=end_date if end_date else timezone.now() + timedelta(days=365),
                end_date__gt=start_date
            )

            if overlapping.exists():
                return False, f"Solapamiento con aplicaciones existentes: {[app.id for app in overlapping]}"

            # Verificar lógica temporal
            if end_date and end_date <= start_date:
                return False, "La fecha de fin debe ser posterior a la fecha de inicio"

            return True, "Rango válido"

        except Exception as exc:
            return False, f"Error de validación: {exc}"


# Instancia global del servicio
constants_service = ConstantsService()