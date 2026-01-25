from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from api.dynamic_registry.models import SystemModule
from api.dynamic_registry.serializers import SystemModuleSerializer

class RegistryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Endpoint público (autenticado) para obtener la configuración
    de módulos dinámicos del sistema.
    """
    queryset = SystemModule.objects.filter(is_active=True).prefetch_related(
        'views', 'views__actions'
    ).order_by('order')
    permissions_classes = [permissions.IsAuthenticated]
    serializer_class = SystemModuleSerializer
    lookup_field = 'slug'

    @action(detail=False, methods=['get'])
    def menu(self, request):
        """
        Retorna solo la estructura del menú principal (sin vistas detalladas).
        Optimizado para carga inicial.
        """
        modules = self.filter_queryset(self.get_queryset())
        
        # Filtro básico de permisos (TODO: Refinar con Guardian o Logic compleja)
        # Por ahora asumimos que si required_permissions está vacío, es público
        
        user_perms = request.user.get_all_permissions()
        
        filtered = []
        for mod in modules:
            if not mod.required_permissions:
                filtered.append(mod)
                continue
                
            # Verificar si el usuario tiene AL MENOS UNO de los permisos requeridos
            # O todos? La lógica OR es más flexible para menús.
            has_perm = any(p in user_perms for p in mod.required_permissions)
            if has_perm or request.user.is_superuser:
                filtered.append(mod)
        
        data = [
            {
                'name': m.name,
                'slug': m.slug,
                'icon': m.icon,
                'order': m.order
            }
            for m in filtered
        ]
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        """
        Retorna la configuración completa de UN módulo, incluyendo sus vistas.
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
from django.apps import apps
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, Avg, Count, Max, Min
from rest_framework import viewsets, permissions, serializers, exceptions, mixins, status
from rest_framework.response import Response # Explicit import
from django.shortcuts import get_object_or_404
from api.dynamic_registry.models import AuditLog

# ... existing imports ...

class DynamicModelSerializer(serializers.ModelSerializer):
    """Serializer genérico que se construye al vuelo."""
    class Meta:
        model = None
        fields = '__all__'

class DataProxyViewSet(mixins.CreateModelMixin,
                       mixins.RetrieveModelMixin,
                       mixins.UpdateModelMixin,
                       mixins.DestroyModelMixin,
                       mixins.ListModelMixin,
                       viewsets.GenericViewSet):
    """
    Proxy universal para consultar y modificar modelos de Django dinámicamente.
    URL: /api/registry/proxy/{app_label}/{model_name}/
    Soporta: GET (List/Retrieve), POST (Create), PUT/PATCH (Update), DELETE (Destroy).
    Incluye Auditoría Automática.
    """
    permission_classes = [permissions.IsAuthenticated]

    def _get_model(self, app_label, model_name):
        try:
            return apps.get_model(app_label, model_name)
        except LookupError:
            raise exceptions.NotFound(f"Model {app_label}.{model_name} not found")

    def _check_model_permissions(self, user, model, action_type='view'):
        """
        Verificar si el usuario tiene permiso:
        view_{model}, add_{model}, change_{model}, delete_{model}
        """
        perm_codename = f"{model._meta.app_label}.{action_type}_{model._meta.model_name}"
        if not user.has_perm(perm_codename) and not user.is_superuser:
            raise exceptions.PermissionDenied(f"Missing permission: {perm_codename}")

    def _get_serializer_class(self, model_class):
        """Crear una clase serializer al vuelo para el modelo."""
        meta_class = type('Meta', (), {'model': model_class, 'fields': '__all__'})
        serializer_name = f"{model_class.__name__}ProxySerializer"
        return type(serializer_name, (DynamicModelSerializer,), {'Meta': meta_class})

    def _log_audit(self, request, action, obj, payload=None):
        """Registrar operación en AuditLog"""
        try:
            resource = f"{obj._meta.app_label}.{obj._meta.model_name}"
            pk = str(obj.pk)
            
            # Simple User Agent & IP extraction
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')
            
            AuditLog.objects.create(
                user=request.user,
                action=action,
                resource=resource,
                resource_id=pk,
                payload=payload or {},
                ip_address=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
        except Exception as e:
            # Audit failure should not block the transaction but should be logged
            print(f"AUDIT WARN: Failed to log {action} on {obj}: {e}")

    # --- ViewSet Overrides ---

    def list(self, request, app_label, model_name):
        model = self._get_model(app_label, model_name)
        self._check_model_permissions(request.user, model, 'view')
        
        queryset = model.objects.all()
        
        # 1. Filtros básicos (k=v)
        # Excluir params reservados para control
        reserved_params = ['page', 'aggregate', 'field', 'group_by']
        filters = {k: v for k, v in request.query_params.items() if k not in reserved_params}
        
        if filters:
            try:
                # Soporte básico para lookups (ej: status__icontains=active)
                # Esto es peligroso si no se sanitiza, pero útil en entorno controlado.
                # Idealmente usar DjangoFilterBackend.
                queryset = queryset.filter(**filters)
            except Exception as e:
                raise exceptions.ValidationError(f"Filter error: {str(e)}")

        # 2. Agregaciones (Sum/Avg/Count)
        aggregate_func = request.query_params.get('aggregate')
        aggregate_field = request.query_params.get('field')
        
        if aggregate_func:
            if not aggregate_field and aggregate_func != 'count':
                raise exceptions.ValidationError("Param 'field' is required for aggregation (except count).")
                
            try:
                if aggregate_func == 'count':
                    value = queryset.count()
                elif aggregate_func == 'sum':
                    value = queryset.aggregate(res=Sum(aggregate_field))['res']
                elif aggregate_func == 'avg':
                    value = queryset.aggregate(res=Avg(aggregate_field))['res']
                elif aggregate_func == 'max':
                    value = queryset.aggregate(res=Max(aggregate_field))['res']
                elif aggregate_func == 'min':
                    value = queryset.aggregate(res=Min(aggregate_field))['res']
                else:
                    raise exceptions.ValidationError(f"Unknown aggregation: {aggregate_func}")
                
                return Response({'value': value, 'type': 'aggregation', 'func': aggregate_func})
            except Exception as e:
                 raise exceptions.ValidationError(f"Aggregation failed: {str(e)}")

        # 3. Listado Estándar (si no hay agregación)
        # Paginación (Manual simple por ahora)
        page = int(request.query_params.get('page', 1))
        page_size = 50
        start = (page - 1) * page_size
        end = start + page_size
        
        total = queryset.count()
        data = queryset[start:end]
        
        Serializer = self._get_serializer_class(model)
        serializer = Serializer(data, many=True)
        
        return Response({
            'count': total,
            'page': page,
            'results': serializer.data
        })

    def retrieve(self, request, app_label, model_name, pk=None):
        model = self._get_model(app_label, model_name)
        self._check_model_permissions(request.user, model, 'view')
        
        obj = get_object_or_404(model, pk=pk)
        Serializer = self._get_serializer_class(model)
        serializer = Serializer(obj)
        
        return Response(serializer.data)

    def create(self, request, app_label, model_name):
        model = self._get_model(app_label, model_name)
        self._check_model_permissions(request.user, model, 'add')
        
        Serializer = self._get_serializer_class(model)
        serializer = Serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        
        self._log_audit(request, 'CREATE', obj, payload=serializer.data)
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, app_label, model_name, pk=None, **kwargs):
        model = self._get_model(app_label, model_name)
        self._check_model_permissions(request.user, model, 'change')
        
        obj = get_object_or_404(model, pk=pk)
        Serializer = self._get_serializer_class(model)
        
        partial = kwargs.get('partial', False) # Handle PATCH
        serializer = Serializer(obj, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # Capture old state if needed, here just logging new state
        obj = serializer.save()
        
        self._log_audit(request, 'UPDATE', obj, payload=request.data)
        
        return Response(serializer.data)

    def partial_update(self, request, app_label, model_name, pk=None, **kwargs):
        kwargs['partial'] = True
        return self.update(request, app_label, model_name, pk, **kwargs)

    def destroy(self, request, app_label, model_name, pk=None):
        model = self._get_model(app_label, model_name)
        self._check_model_permissions(request.user, model, 'delete')
        
        obj = get_object_or_404(model, pk=pk)
        
        # Log BEFORE delete to catch the ID
        self._log_audit(request, 'DELETE', obj, payload={'pk': pk})
        
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
