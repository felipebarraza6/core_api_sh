"""
SmartHydro App Chat API
========================
Endpoint REST autenticado para el chatbot inteligente.

- Recibe mensajes del usuario autenticado
- Infiere contexto de cliente/proyecto desde sus puntos de captación
- Mantiene historial conversacional vía Redis
- Responde usando el motor existente (Gemini + Tools + Intent Router)

Uso:
    POST /api/chat/
    {
        "message": "¿Cómo está el caudal de P4?",
        "conversation_id": "optional-uuid"
    }

Respuesta:
    {
        "response": "El caudal de P4 (Iansa) es 12.5 L/s...",
        "context": {
            "client": "Iansa",
            "project": "Proyecto Norte",
            "point": "P4"
        },
        "timestamp": "2025-01-15T10:30:00Z"
    }
"""

import json
import uuid
import logging
from datetime import datetime

from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.core.models import CatchmentPoint, User
from api.core.chatbot.llm import (
    resolve_intent_and_respond,
    get_conversation_context,
    save_conversation_context,
)
from api.core.chatbot.tools_scoped import NOT_FOUND_MSG, ACCESS_DENIED_MSG

logger = logging.getLogger(__name__)


class ChatRequestSerializer(serializers.Serializer):
    """Validador de entrada para el endpoint de chat."""
    message = serializers.CharField(required=True, min_length=1, max_length=2000)
    conversation_id = serializers.CharField(required=False, allow_blank=True, max_length=64)


class ChatbotAppView(APIView):
    """
    Endpoint de chat inteligente para la aplicación SmartHydro.

    - Autenticación requerida (Token o Session)
    - Contexto de cliente/proyecto inferido automáticamente
    - Historial conversacional persistente en Redis (TTL 15 min)
    """
    permission_classes = [IsAuthenticated]

    def _get_user_context(self, user: User) -> dict:
        """
        Infiere el contexto de negocio del usuario a partir de sus puntos
        de captación (como owner o viewer).

        Returns:
            dict con 'clients', 'projects', 'points' y preferencias.
        """
        context = {
            "clients": [],
            "projects": [],
            "points": [],
            "primary_client": None,
            "primary_project": None,
            "is_staff": user.is_staff or user.is_superuser,
        }

        # Superusuarios ven todo, no restringimos contexto
        if context["is_staff"]:
            return context

        # Buscar puntos donde el usuario es owner o viewer
        points = CatchmentPoint.objects.filter(
            Q(owner_user=user) | Q(users_viewers=user)
        ).select_related("project", "project__client").distinct()

        clients_map = {}
        projects_map = {}
        points_list = []

        for p in points:
            client_name = None
            project_name = None

            if p.project:
                project_name = p.project.name
                projects_map[project_name] = True
                if p.project.client:
                    client_name = p.project.client.name
                    clients_map[client_name] = True

            points_list.append({
                "id": p.id,
                "title": p.title,
                "project": project_name,
                "client": client_name,
            })

        context["clients"] = list(clients_map.keys())
        context["projects"] = list(projects_map.keys())
        context["points"] = points_list

        # Determinar cliente primario (el más frecuente o único)
        if len(context["clients"]) == 1:
            context["primary_client"] = context["clients"][0]
        elif len(context["clients"]) > 1:
            # Si hay múltiples, elegir el que tenga más puntos
            from collections import Counter
            client_counts = Counter(
                p["client"] for p in points_list if p["client"]
            )
            if client_counts:
                context["primary_client"] = client_counts.most_common(1)[0][0]

        # Determinar proyecto primario
        if len(context["projects"]) == 1:
            context["primary_project"] = context["projects"][0]

        return context

    def _build_system_context(self, user_context: dict) -> str:
        """
        Construye el texto de contexto que se inyecta al prompt del chatbot
        para que conozca el alcance del usuario.
        """
        parts = []

        if user_context.get("primary_client"):
            parts.append(f"Cliente principal: {user_context['primary_client']}.")

        if user_context.get("primary_project"):
            parts.append(f"Proyecto principal: {user_context['primary_project']}.")

        if user_context.get("clients"):
            if len(user_context["clients"]) <= 5:
                parts.append(f"Clientes asociados: {', '.join(user_context['clients'])}.")
            else:
                parts.append(f"El usuario tiene {len(user_context['clients'])} clientes asociados.")

        if user_context.get("points"):
            point_titles = [p['title'] for p in user_context['points'][:10]]
            parts.append(f"Puntos a los que tiene acceso: {', '.join(point_titles)}.")
            if len(user_context['points']) > 10:
                parts.append(f"(y {len(user_context['points']) - 10} más).")

        if user_context.get("is_staff"):
            parts.append("El usuario es staff/admin y puede consultar cualquier cliente o punto del sistema.")

        if not parts:
            parts.append("El usuario no tiene puntos asociados explícitamente.")

        return " ".join(parts)

    def _resolve_conversation_id(self, request_data: dict, user: User) -> str:
        """Genera o reutiliza un ID de conversación único por usuario."""
        provided = request_data.get("conversation_id", "").strip()
        if provided:
            # Sanitizar: solo alfanumérico, guiones y guiones bajos
            safe_id = "".join(c for c in provided if c.isalnum() or c in "-_")
            return f"appchat:{user.id}:{safe_id}"
        # Fallback: conversación anónima por usuario (sin ID explícito)
        return f"appchat:{user.id}:default"

    def _is_not_found_or_denied(self, text: str) -> bool:
        """Detecta si la respuesta indica que no se encontró info o no hay acceso."""
        if not text:
            return True
        lower = text.lower()
        indicators = [
            "no encontré",
            "no encontré información",
            "no tienes acceso",
            "punto no encontrado",
            "cliente no encontrado",
            "no se encontraron",
            "no hay puntos",
            "no se detectaron",
        ]
        return any(ind in lower for ind in indicators)

    def _build_ticket_response(self, original: str) -> str:
        """Envuelve una respuesta vacía/not-found con una sugerencia de ticket."""
        return (
            f"{original}\n\n"
            "🎫 *¿Necesitas ayuda adicional?*\n"
            "No encontré esa información en tus puntos asociados, o puede que requiera "
            "revisión manual por parte del equipo de soporte.\n\n"
            "¿Te gustaría abrir un ticket? Puedes hacerlo desde el menú de soporte de la app."
        )

    def post(self, request, *args, **kwargs):
        """Procesa un mensaje de chat desde la app."""
        serializer = ChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Datos inválidos", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        message = serializer.validated_data["message"].strip()
        user = request.user
        conversation_id = self._resolve_conversation_id(serializer.validated_data, user)

        try:
            # 1. Obtener contexto conversacional previo (Redis)
            chat_context = get_conversation_context(conversation_id)

            # 2. Obtener contexto de negocio del usuario
            user_context = self._get_user_context(user)

            # 3. Si no hay cliente en el contexto conversacional, pre-cargar el primario
            if not chat_context.get("last_client") and user_context.get("primary_client"):
                chat_context["last_client"] = user_context["primary_client"]

            if not chat_context.get("last_project") and user_context.get("primary_project"):
                chat_context["last_project"] = user_context["primary_project"]

            # Guardar contexto enriquecido para que el LLM lo use
            save_conversation_context(conversation_id, chat_context)

            # 4. Inyectar contexto de sistema al mensaje si es la primera interacción
            #    o si el usuario no ha mencionado un cliente explícitamente
            enriched_message = message
            if (
                not chat_context.get("user_has_mentioned_client")
                and user_context.get("primary_client")
                and len(message) < 100
            ):
                # Solo enriquecer mensajes cortos donde el usuario no ha
                # establecido un cliente previo en la conversación
                system_ctx = self._build_system_context(user_context)
                enriched_message = (
                    f"[Contexto del usuario: {system_ctx}] "
                    f"Pregunta: {message}"
                )
                # Marcar que ya inyectamos contexto para no repetirlo
                chat_context["system_context_injected"] = True
                save_conversation_context(conversation_id, chat_context)

            # 5. Llamar al motor de chatbot existente
            #    resolve_intent_and_respond usa el contexto Redis para mantener
            #    la conversación (last_client, last_point, etc.)
            #    Se pasa el usuario para aplicar filtro de alcance (scoped tools).
            response_text = resolve_intent_and_respond(
                user_text=enriched_message,
                user_name=user.get_full_name() or user.email or "Usuario",
                user_id=conversation_id,
                user=user,
            )

            # 5b. Si la respuesta es "no encontré" y el usuario no es staff,
            #     sugerir abrir ticket de soporte.
            if not (user.is_staff or user.is_superuser):
                if self._is_not_found_or_denied(response_text):
                    response_text = self._build_ticket_response(response_text)

            # 6. Refrescar contexto post-respuesta para devolverlo al frontend
            updated_context = get_conversation_context(conversation_id)

            # 7. Detectar si el usuario mencionó un cliente en este mensaje
            if user_context.get("clients"):
                for client_name in user_context["clients"]:
                    if client_name.lower() in message.lower():
                        updated_context["user_has_mentioned_client"] = True
                        save_conversation_context(conversation_id, updated_context)
                        break

            # 8. Construir respuesta JSON limpia para la app
            response_data = {
                "response": response_text,
                "context": {
                    "client": updated_context.get("last_client"),
                    "project": updated_context.get("last_project"),
                    "point": updated_context.get("last_point"),
                },
                "conversation_id": conversation_id.split(":")[-1],
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error en ChatbotAppView: {e}", exc_info=True)
            return Response(
                {
                    "error": "Ocurrió un error procesando tu mensaje.",
                    "detail": str(e) if user.is_staff else None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
