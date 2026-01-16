"""
API IK Views - Optimized Endpoints
===================================

Vistas optimizadas que retornan solo los datos necesarios.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate

from api.core.models import User


class OptimizedLoginView(APIView):
    """
    Login optimizado que retorna solo datos esenciales.
    
    POST /api/ik/login/
    Body: { "email": "...", "password": "..." }
    
    Response (éxito):
    {
        "access_token": "...",
        "user": {
            "id": 1,
            "email": "...",
            "username": "...",
            "first_name": "...",
            "is_staff": false
        },
        "points_summary": {
            "total": 5,
            "ids": [1, 2, 3, 4, 5]
        }
    }
    
    La API original (/api/users/login/) retorna TODOS los datos de cada punto.
    Esta versión retorna solo IDs, que luego puedes cargar bajo demanda.
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get('email', '').strip()
        password = request.data.get('password', '')
        
        if not email or not password:
            return Response(
                {"error": "Email y contraseña son requeridos"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Buscar usuario por email
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"error": "Credenciales inválidas"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Verificar contraseña
        if not user.check_password(password):
            return Response(
                {"error": "Credenciales inválidas"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Obtener o crear token
        token, _ = Token.objects.get_or_create(user=user)
        
        # Obtener IDs de puntos (sin cargar todos los datos)
        owned_point_ids = list(user.owned_catchment_points.values_list('id', flat=True))
        viewed_point_ids = list(user.viewed_catchment_points.values_list('id', flat=True))
        all_point_ids = list(set(owned_point_ids + viewed_point_ids))
        
        return Response({
            "access_token": token.key,
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_staff": user.is_staff,
            },
            "points_summary": {
                "total": len(all_point_ids),
                "owned_ids": owned_point_ids,
                "viewed_ids": viewed_point_ids,
                "all_ids": all_point_ids
            }
        })
