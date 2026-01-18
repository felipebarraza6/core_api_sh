"""
Servicio de Control de Acciones de Usuario
Implementa un sistema de permisos granular y auditoría de acciones
"""

from django.core.cache import cache
from django.utils import timezone
from django.contrib.auth.models import User
from typing import Dict, List, Optional, Any
import json

from ..models.management_super import SystemConfiguration


class ActionService:
    """
    Servicio para control de acciones y permisos de usuario
    Implementa un sistema de ERP integrado
    """

    # Definición de todas las acciones disponibles
    ACTIONS = {
        # Dashboard y visualización
        'DASHBOARD_VIEW': {
            'name': 'Ver Dashboard',
            'category': 'dashboard',
            'description': 'Acceso al dashboard principal'
        },
        'DASHBOARD_ADMIN': {
            'name': 'Dashboard Administrativo',
            'category': 'dashboard',
            'description': 'Acceso a métricas administrativas'
        },

        # Telemetría
        'TELEMETRY_VIEW': {
            'name': 'Ver Telemetría',
            'category': 'telemetry',
            'description': 'Visualizar datos de telemetría'
        },
        'TELEMETRY_EDIT': {
            'name': 'Editar Telemetría',
            'category': 'telemetry',
            'description': 'Modificar datos de telemetría'
        },
        'TELEMETRY_DELETE': {
            'name': 'Eliminar Telemetría',
            'category': 'telemetry',
            'description': 'Eliminar registros de telemetría'
        },

        # Control DGA
        'DGA_SEND': {
            'name': 'Enviar a DGA',
            'category': 'dga',
            'description': 'Enviar datos automáticamente a DGA'
        },
        'DGA_DISABLE': {
            'name': 'Desactivar DGA',
            'category': 'dga',
            'description': 'Desactivar envío automático a DGA'
        },
        'DGA_CONFIG': {
            'name': 'Configurar DGA',
            'category': 'dga',
            'description': 'Modificar configuración DGA'
        },

        # Reportes
        'REPORTS_GENERATE': {
            'name': 'Generar Reportes',
            'category': 'reports',
            'description': 'Crear reportes personalizados'
        },
        'REPORTS_SCHEDULE': {
            'name': 'Programar Reportes',
            'category': 'reports',
            'description': 'Configurar reportes automáticos'
        },
        'REPORTS_EXPORT': {
            'name': 'Exportar Datos',
            'category': 'reports',
            'description': 'Exportar datos en diferentes formatos'
        },

        # Gestión de dispositivos
        'DEVICES_MANAGE': {
            'name': 'Gestionar Dispositivos',
            'category': 'devices',
            'description': 'Administrar dispositivos IoT'
        },
        'DEVICES_CONFIG': {
            'name': 'Configurar Dispositivos',
            'category': 'devices',
            'description': 'Modificar configuración de dispositivos'
        },
        'DEVICES_MAINTENANCE': {
            'name': 'Programar Mantenimiento',
            'category': 'devices',
            'description': 'Gestionar mantenimiento de dispositivos'
        },

        # Alertas
        'ALERTS_MANAGE': {
            'name': 'Gestionar Alertas',
            'category': 'alerts',
            'description': 'Administrar reglas de alertas'
        },
        'ALERTS_CONFIG': {
            'name': 'Configurar Alertas',
            'category': 'alerts',
            'description': 'Crear y modificar alertas'
        },
        'ALERTS_ESCALATE': {
            'name': 'Escalar Alertas',
            'category': 'alerts',
            'description': 'Escalar alertas críticas'
        },

        # Gestión de usuarios
        'USERS_MANAGE': {
            'name': 'Gestionar Usuarios',
            'category': 'users',
            'description': 'Administrar usuarios del sistema'
        },
        'USERS_PERMISSIONS': {
            'name': 'Administrar Permisos',
            'category': 'users',
            'description': 'Modificar permisos de usuarios'
        },
        'USERS_AUDIT': {
            'name': 'Ver Auditoría',
            'category': 'users',
            'description': 'Acceder a logs de auditoría'
        },

        # Sistema
        'SYSTEM_CONFIG': {
            'name': 'Configurar Sistema',
            'category': 'system',
            'description': 'Modificar configuración del sistema'
        },
        'SYSTEM_MAINTENANCE': {
            'name': 'Mantenimiento del Sistema',
            'category': 'system',
            'description': 'Realizar tareas de mantenimiento'
        },
        'SYSTEM_BACKUP': {
            'name': 'Respaldos del Sistema',
            'category': 'system',
            'description': 'Gestionar respaldos del sistema'
        },

        # Estadísticas
        'SYSTEM_STATS_VIEW': {
            'name': 'Ver Estadísticas del Sistema',
            'category': 'stats',
            'description': 'Acceder a métricas del sistema'
        }
    }

    # Perfiles predefinidos de usuario
    USER_PROFILES = {
        'ADMIN': {
            'name': 'Administrador',
            'permissions': ['*'],  # Todos los permisos
            'description': 'Acceso completo al sistema'
        },
        'MANAGER': {
            'name': 'Gerente',
            'permissions': [
                'DASHBOARD_VIEW', 'TELEMETRY_VIEW', 'REPORTS_GENERATE',
                'ALERTS_MANAGE', 'DEVICES_CONFIG', 'USERS_AUDIT',
                'SYSTEM_STATS_VIEW'
            ],
            'description': 'Gestión operativa completa'
        },
        'OPERATOR': {
            'name': 'Operador',
            'permissions': [
                'DASHBOARD_VIEW', 'TELEMETRY_VIEW', 'REPORTS_GENERATE',
                'ALERTS_MANAGE', 'DEVICES_CONFIG'
            ],
            'description': 'Operación diaria del sistema'
        },
        'VIEWER': {
            'name': 'Visualizador',
            'permissions': [
                'DASHBOARD_VIEW', 'TELEMETRY_VIEW', 'REPORTS_GENERATE'
            ],
            'description': 'Solo lectura y reportes'
        },
        'CLIENT': {
            'name': 'Cliente',
            'permissions': [
                'DASHBOARD_VIEW', 'TELEMETRY_VIEW', 'REPORTS_GENERATE'
            ],
            'description': 'Acceso limitado a sus propios datos'
        }
    }

    @staticmethod
    def user_can_perform_action(user, action_code: str, resource_id: Optional[str] = None) -> bool:
        """
        Verificar si un usuario puede realizar una acción específica
        """
        try:
            # Administradores tienen todos los permisos
            if user.is_staff or user.is_superuser:
                return True

            # Obtener permisos del usuario desde cache o configuración
            user_permissions = ActionService._get_user_permissions(user)

            # Verificar permiso específico
            if action_code in user_permissions:
                return True

            # Verificar permisos comodín (ej: TELEMETRY_*)
            action_category = action_code.split('_')[0]
            wildcard_permission = f"{action_category}_*"
            if wildcard_permission in user_permissions:
                return True

            # Verificar permisos de grupo (ej: DASHBOARD_*)
            for permission in user_permissions:
                if permission.endswith('*') and action_code.startswith(permission[:-1]):
                    return True

            return False

        except Exception as exc:
            # En caso de error, denegar acceso por seguridad
            ActionService.log_user_action(user, f"PERMISSION_CHECK_ERROR_{action_code}", resource_id, {
                'error': str(exc)
            })
            return False

    @staticmethod
    def _get_user_permissions(user) -> List[str]:
        """
        Obtener permisos del usuario desde cache o configuración
        """
        cache_key = f'user_permissions_{user.id}'

        # Intentar obtener de cache
        cached_permissions = cache.get(cache_key)
        if cached_permissions:
            return cached_permissions

        # Calcular permisos del usuario
        permissions = ActionService._calculate_user_permissions(user)

        # Cache por 15 minutos
        cache.set(cache_key, permissions, 900)

        return permissions

    @staticmethod
    def _calculate_user_permissions(user) -> List[str]:
        """
        Calcular permisos basados en configuración del usuario
        """
        try:
            # Por defecto, usuarios normales tienen permisos básicos
            permissions = ['DASHBOARD_VIEW', 'TELEMETRY_VIEW']

            # Verificar configuración específica del usuario
            user_config = SystemConfiguration.objects.filter(
                key=f'user_permissions_{user.id}'
            ).first()

            if user_config and user_config.value:
                config_permissions = user_config.value.get('permissions', [])
                permissions.extend(config_permissions)

            # Verificar perfil asignado
            profile_config = SystemConfiguration.objects.filter(
                key=f'user_profile_{user.id}'
            ).first()

            if profile_config and profile_config.value:
                profile_name = profile_config.value.get('profile')
                if profile_name in ActionService.USER_PROFILES:
                    profile_permissions = ActionService.USER_PROFILES[profile_name]['permissions']
                    if '*' in profile_permissions:
                        # Perfil con todos los permisos
                        permissions = list(ActionService.ACTIONS.keys())
                    else:
                        permissions.extend(profile_permissions)

            return list(set(permissions))  # Eliminar duplicados

        except Exception as exc:
            # En caso de error, permisos mínimos
            return ['DASHBOARD_VIEW']

    @staticmethod
    def get_user_permissions_summary(user) -> Dict[str, Any]:
        """
        Obtener resumen completo de permisos del usuario
        """
        try:
            permissions = ActionService._get_user_permissions(user)

            # Organizar por categorías
            categories = {}
            for action_code in permissions:
                if action_code in ActionService.ACTIONS:
                    category = ActionService.ACTIONS[action_code]['category']
                    if category not in categories:
                        categories[category] = []
                    categories[category].append({
                        'code': action_code,
                        'name': ActionService.ACTIONS[action_code]['name'],
                        'description': ActionService.ACTIONS[action_code]['description']
                    })

            # Obtener perfil actual
            profile_info = ActionService._get_user_profile_info(user)

            return {
                'permissions': permissions,
                'categories': categories,
                'total_permissions': len(permissions),
                'profile': profile_info,
                'last_updated': timezone.now().isoformat()
            }

        except Exception as exc:
            return {
                'error': str(exc),
                'permissions': [],
                'categories': {}
            }

    @staticmethod
    def _get_user_profile_info(user) -> Dict[str, Any]:
        """Obtener información del perfil asignado al usuario"""
        try:
            profile_config = SystemConfiguration.objects.filter(
                key=f'user_profile_{user.id}'
            ).first()

            if profile_config and profile_config.value:
                profile_name = profile_config.value.get('profile')
                if profile_name in ActionService.USER_PROFILES:
                    return ActionService.USER_PROFILES[profile_name]

            return {
                'name': 'Usuario Estándar',
                'description': 'Permisos básicos del sistema'
            }

        except Exception:
            return {
                'name': 'Error',
                'description': 'No se pudo determinar el perfil'
            }

    @staticmethod
    def assign_user_profile(user, profile_name: str) -> bool:
        """
        Asignar un perfil predefinido a un usuario
        """
        try:
            if profile_name not in ActionService.USER_PROFILES:
                return False

            # Guardar configuración del perfil
            config, created = SystemConfiguration.objects.get_or_create(
                key=f'user_profile_{user.id}',
                defaults={
                    'value': {'profile': profile_name},
                    'category': 'USERS'
                }
            )

            if not created:
                config.value = {'profile': profile_name}
                config.save()

            # Limpiar cache de permisos
            cache.delete(f'user_permissions_{user.id}')

            ActionService.log_user_action(
                user, 'USER_PROFILE_ASSIGNED', str(user.id),
                {'profile': profile_name, 'assigned_by': user.id}
            )

            return True

        except Exception as exc:
            ActionService.log_user_action(
                user, 'USER_PROFILE_ASSIGN_ERROR', str(user.id),
                {'error': str(exc), 'profile': profile_name}
            )
            return False

    @staticmethod
    def grant_user_permission(user, action_code: str, granted_by: User = None) -> bool:
        """
        Otorgar un permiso específico a un usuario
        """
        try:
            if action_code not in ActionService.ACTIONS:
                return False

            # Obtener configuración actual de permisos
            config, created = SystemConfiguration.objects.get_or_create(
                key=f'user_permissions_{user.id}',
                defaults={
                    'value': {'permissions': []},
                    'category': 'USERS'
                }
            )

            permissions = config.value.get('permissions', [])
            if action_code not in permissions:
                permissions.append(action_code)
                config.value['permissions'] = permissions
                config.save()

            # Limpiar cache
            cache.delete(f'user_permissions_{user.id}')

            ActionService.log_user_action(
                user, 'USER_PERMISSION_GRANTED', str(user.id),
                {'permission': action_code, 'granted_by': granted_by.id if granted_by else None}
            )

            return True

        except Exception as exc:
            ActionService.log_user_action(
                user, 'USER_PERMISSION_GRANT_ERROR', str(user.id),
                {'error': str(exc), 'permission': action_code}
            )
            return False

    @staticmethod
    def revoke_user_permission(user, action_code: str, revoked_by: User = None) -> bool:
        """
        Revocar un permiso específico de un usuario
        """
        try:
            config = SystemConfiguration.objects.filter(
                key=f'user_permissions_{user.id}'
            ).first()

            if config and config.value:
                permissions = config.value.get('permissions', [])
                if action_code in permissions:
                    permissions.remove(action_code)
                    config.value['permissions'] = permissions
                    config.save()

                    # Limpiar cache
                    cache.delete(f'user_permissions_{user.id}')

                    ActionService.log_user_action(
                        user, 'USER_PERMISSION_REVOKED', str(user.id),
                        {'permission': action_code, 'revoked_by': revoked_by.id if revoked_by else None}
                    )

                    return True

            return False

        except Exception as exc:
            ActionService.log_user_action(
                user, 'USER_PERMISSION_REVOKE_ERROR', str(user.id),
                {'error': str(exc), 'permission': action_code}
            )
            return False

    @staticmethod
    def log_user_action(user, action_code: str, resource_id: Optional[str] = None,
                       details: Optional[Dict] = None):
        """
        Registrar acción del usuario para auditoría
        En producción, esto debería guardar en una tabla de auditoría
        """
        try:
            # Por ahora, usar configuración del sistema como log temporal
            # En producción, crear un modelo UserActionLog

            log_entry = {
                'user_id': user.id,
                'user_email': user.email,
                'action': action_code,
                'resource_id': resource_id,
                'details': details or {},
                'timestamp': timezone.now().isoformat(),
                'ip_address': getattr(user, 'last_login_ip', None)
            }

            # Guardar en configuración temporal (reemplazar con modelo real)
            cache_key = f'user_action_log_{user.id}'
            existing_logs = cache.get(cache_key, [])
            existing_logs.append(log_entry)

            # Mantener solo últimas 50 acciones
            if len(existing_logs) > 50:
                existing_logs = existing_logs[-50:]

            cache.set(cache_key, existing_logs, 86400)  # 24 horas

        except Exception as exc:
            # No fallar si hay error en logging
            pass

    @staticmethod
    def get_recent_user_actions(user, limit: int = 10) -> List[Dict]:
        """
        Obtener acciones recientes del usuario
        """
        try:
            cache_key = f'user_action_log_{user.id}'
            logs = cache.get(cache_key, [])

            # Retornar las más recientes
            return logs[-limit:] if logs else []

        except Exception:
            return []

    @staticmethod
    def get_available_actions() -> Dict[str, Dict]:
        """
        Obtener todas las acciones disponibles organizadas por categoría
        """
        categories = {}
        for action_code, action_info in ActionService.ACTIONS.items():
            category = action_info['category']
            if category not in categories:
                categories[category] = []
            categories[category].append({
                'code': action_code,
                **action_info
            })

        return categories

    @staticmethod
    def get_user_profiles() -> Dict[str, Dict]:
        """
        Obtener perfiles de usuario disponibles
        """
        return ActionService.USER_PROFILES