"""
Paginación condicional para API Legacy.

Permite agregar paginación a viewsets existentes sin romper compatibilidad
con frontend que espera arrays planos.

Si la request NO tiene ?page= ni ?limit= → retorna array plano (comportamiento anterior).
Si la request SÍ tiene ?page= o ?limit= → retorna respuesta paginada {"count", "results"}.
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class ConditionalPagination(PageNumberPagination):
    """
    Paginador que solo se activa cuando hay parámetros de paginación explícitos.

    Uso:
        class MyViewSet(ConditionalPaginationMixin, viewsets.ViewSet):
            pagination_class = ConditionalPagination
            # ...
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        # Solo paginar si hay parámetros de paginación explícitos
        if 'page' not in request.query_params and 'limit' not in request.query_params:
            return None
        return super().paginate_queryset(queryset, request, view)


class ConditionalPaginationMixin:
    """
    Mixin para viewsets que quieren paginación condicional.

    Si la request tiene ?page= o ?limit=, retorna respuesta paginada.
    Si no, retorna la lista completa (comportamiento legacy).
    """
    pagination_class = ConditionalPagination

    def get_paginated_response_if_requested(self, data, request):
        """
        Retorna respuesta paginada solo si se pidió paginación.
        Si no, retorna array plano.
        """
        if 'page' in request.query_params or 'limit' in request.query_params:
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(data, request, view=self)
            if page is not None:
                return paginator.get_paginated_response(page)
        return Response(data)
