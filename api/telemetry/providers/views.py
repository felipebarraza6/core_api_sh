"""
Provider Management Views

REST API endpoints for managing telemetry providers dynamically.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from django.shortcuts import get_object_or_404

from .models import TelemetryProvider, CatchmentPointProvider
from . import get_provider_manager
from ..models.catchment_points import CatchmentPoint


class ProviderListView(APIView):
    """
    List all available telemetry providers.

    GET /api/providers/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all active providers."""
        manager = get_provider_manager()
        providers = manager.get_all_providers()

        data = []
        for name, provider in providers.items():
            data.append({
                'id': provider.id,
                'name': provider.name,
                'display_name': provider.display_name,
                'provider_type': provider.provider_type,
                'description': provider.description,
                'is_active': provider.is_active,
                'base_url': provider.base_url,
                'auth_method': provider.auth_method,
                'version': provider.version
            })

        return Response({
            'count': len(data),
            'results': data
        })


class ProviderDetailView(APIView):
    """
    Provider details and management.

    GET /api/providers/{name}/
    PUT /api/providers/{name}/
    DELETE /api/providers/{name}/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, provider_name):
        """Get provider details."""
        manager = get_provider_manager()
        provider = manager.get_provider(provider_name)

        if not provider:
            return Response(
                {"error": "Provider not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Test connection
        test_result = manager.test_provider_connection(provider_name)

        data = {
            'id': provider.id,
            'name': provider.name,
            'display_name': provider.display_name,
            'description': provider.description,
            'provider_type': provider.provider_type,
            'base_url': provider.base_url,
            'auth_method': provider.auth_method,
            'auth_config': provider.auth_config,
            'endpoint_template': provider.endpoint_template,
            'request_template': provider.request_template,
            'response_mapping': provider.response_mapping,
            'is_active': provider.is_active,
            'version': provider.version,
            'connection_test': test_result
        }

        return Response(data)

    def put(self, request, provider_name):
        """Update provider configuration."""
        manager = get_provider_manager()
        provider = manager.get_provider(provider_name)

        if not provider:
            return Response(
                {"error": "Provider not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Update allowed fields
        updateable_fields = [
            'display_name', 'description', 'base_url', 'auth_method',
            'auth_config', 'endpoint_template', 'request_template',
            'response_mapping', 'is_active', 'version'
        ]

        for field in updateable_fields:
            if field in request.data:
                setattr(provider, field, request.data[field])

        try:
            provider.full_clean()
            provider.save()

            # Refresh manager cache
            manager.refresh_cache()

            return Response({"message": "Provider updated successfully"})

        except Exception as e:
            return Response(
                {"error": f"Update failed: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def provider_status(request):
    """
    Get status of all providers.

    GET /api/providers/status/
    """
    manager = get_provider_manager()
    status_data = manager.get_provider_status()

    return Response({
        'providers': status_data,
        'total_active': len([p for p in status_data.values() if p['provider'].is_active])
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def test_provider(request, provider_name):
    """
    Test connection to a provider.

    POST /api/providers/{name}/test/
    """
    manager = get_provider_manager()

    test_result = manager.test_provider_connection(provider_name)

    return Response({
        'provider': provider_name,
        'test_result': test_result
    })


class PointProviderConfigView(APIView):
    """
    Manage provider configurations for a specific point.

    GET /api/points/{point_id}/providers/ - List configs
    POST /api/points/{point_id}/providers/ - Create config
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, point_id):
        """List all provider configurations for a point."""
        # Verify user has access to this point
        point = get_object_or_404(
            CatchmentPoint.objects.filter(
                id=point_id
            ).filter(
                # User owns the point or has viewer access
                owner_user=request.user
            ) | CatchmentPoint.objects.filter(
                id=point_id,
                users_viewers=request.user
            ),
            id=point_id
        )

        configs = CatchmentPointProvider.objects.filter(
            point=point
        ).select_related('provider')

        data = []
        for config in configs:
            data.append({
                'id': config.id,
                'provider': {
                    'name': config.provider.name,
                    'display_name': config.provider.display_name,
                    'provider_type': config.provider.provider_type
                },
                'point_code': config.point_code,
                'is_active': config.is_active,
                'priority': config.priority,
                'last_success': config.last_success,
                'last_error': config.last_error,
                'error_count': config.error_count,
                'consecutive_successes': config.consecutive_successes,
                'is_healthy': config.is_healthy,
                'config_override': config.config_override,
                'device_config': config.device_config
            })

        return Response({
            'point_id': point_id,
            'point_title': point.title,
            'configs': data
        })

    def post(self, request, point_id):
        """Create new provider configuration for the point."""
        # Verify user has access to this point
        point = get_object_or_404(
            CatchmentPoint.objects.filter(
                id=point_id,
                owner_user=request.user
            ),
            id=point_id
        )

        required_fields = ['provider_name', 'point_code']
        for field in required_fields:
            if field not in request.data:
                return Response(
                    {"error": f"Required field: {field}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

        manager = get_provider_manager()

        try:
            config = manager.create_provider_config(
                point_id=point_id,
                provider_name=request.data['provider_name'],
                config={
                    'point_code': request.data['point_code'],
                    'config_override': request.data.get('config_override', {}),
                    'device_config': request.data.get('device_config', {}),
                    'priority': request.data.get('priority', 0)
                }
            )

            return Response({
                'id': config.id,
                'message': 'Provider configuration created successfully',
                'config': {
                    'provider': config.provider.name,
                    'point_code': config.point_code,
                    'is_active': config.is_active,
                    'priority': config.priority
                }
            }, status=status.HTTP_201_CREATED)

        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class PointProviderConfigDetailView(APIView):
    """
    Manage specific provider configuration.

    GET /api/points/{point_id}/providers/{config_id}/
    PUT /api/points/{point_id}/providers/{config_id}/
    DELETE /api/points/{point_id}/providers/{config_id}/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, point_id, config_id):
        """Get specific provider configuration."""
        # Verify user has access to this point
        point = get_object_or_404(
            CatchmentPoint.objects.filter(
                id=point_id
            ).filter(
                owner_user=request.user
            ) | CatchmentPoint.objects.filter(
                id=point_id,
                users_viewers=request.user
            ),
            id=point_id
        )

        config = get_object_or_404(
            CatchmentPointProvider,
            id=config_id,
            point=point
        )

        data = {
            'id': config.id,
            'provider': {
                'name': config.provider.name,
                'display_name': config.provider.display_name,
                'provider_type': config.provider.provider_type
            },
            'point_code': config.point_code,
            'is_active': config.is_active,
            'priority': config.priority,
            'last_success': config.last_success,
            'last_error': config.last_error,
            'error_count': config.error_count,
            'consecutive_successes': config.consecutive_successes,
            'is_healthy': config.is_healthy,
            'config_override': config.config_override,
            'device_config': config.device_config
        }

        return Response(data)

    def put(self, request, point_id, config_id):
        """Update provider configuration."""
        # Verify user has access to this point
        point = get_object_or_404(
            CatchmentPoint.objects.filter(
                id=point_id,
                owner_user=request.user
            ),
            id=point_id
        )

        config = get_object_or_404(
            CatchmentPointProvider,
            id=config_id,
            point=point
        )

        manager = get_provider_manager()

        try:
            updated_config = manager.update_provider_config(
                config_id=config_id,
                updates=request.data
            )

            return Response({
                'message': 'Configuration updated successfully',
                'config': {
                    'id': updated_config.id,
                    'is_active': updated_config.is_active,
                    'priority': updated_config.priority,
                    'point_code': updated_config.point_code
                }
            })

        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def delete(self, request, point_id, config_id):
        """Delete provider configuration."""
        # Verify user has access to this point
        point = get_object_or_404(
            CatchmentPoint.objects.filter(
                id=point_id,
                owner_user=request.user
            ),
            id=point_id
        )

        config = get_object_or_404(
            CatchmentPointProvider,
            id=config_id,
            point=point
        )

        manager = get_provider_manager()
        success = manager.disable_provider_config(config_id)

        if success:
            return Response({
                'message': 'Provider configuration disabled successfully'
            })
        else:
            return Response(
                {"error": "Configuration not found"},
                status=status.HTTP_404_NOT_FOUND
            )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def fetch_point_data(request, point_id, provider_name=None):
    """
    Fetch telemetry data for a point from its providers.

    POST /api/points/{point_id}/data/fetch/
    Body: {"variable_type": "CAUDAL", "provider": "nettra"}
    """
    # Verify user has access to this point
    point = get_object_or_404(
        CatchmentPoint.objects.filter(
            id=point_id
        ).filter(
            owner_user=request.user
        ) | CatchmentPoint.objects.filter(
            id=point_id,
            users_viewers=request.user
        ),
        id=point_id
    )

    manager = get_provider_manager()
    variable_type = request.data.get('variable_type')
    requested_provider = request.data.get('provider', provider_name)

    # Get best provider or specific one
    if requested_provider:
        provider_configs = CatchmentPointProvider.objects.filter(
            point=point,
            provider__name=requested_provider,
            is_active=True
        )
        provider_config = provider_configs.first()
    else:
        provider_config = manager.get_best_provider_for_point(point_id, variable_type)

    if not provider_config:
        return Response(
            {"error": "No suitable provider found for this point"},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        handler = manager.get_handler(provider_config.provider.name)
        if not handler:
            return Response(
                {"error": "Provider handler not available"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Fetch data
        data = handler.fetch_data(
            provider_config,
            variable_type=variable_type
        )

        # Record success
        provider_config.record_success()

        return Response({
            'point_id': point_id,
            'point_title': point.title,
            'provider': provider_config.provider.name,
            'data': data
        })

    except Exception as e:
        # Record error
        provider_config.record_error(str(e))

        return Response(
            {"error": f"Data fetch failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )