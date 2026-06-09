"""
API ik — Subsistema de Tickets de Soporte + SLA.

Endpoints bajo /api/ik/tickets/
Nada toca el legacy (NotificationsCatchment).
"""

from datetime import timedelta

from django.db.models import Q, Count
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .throttles import TicketRateThrottle
from rest_framework import status
from rest_framework.pagination import PageNumberPagination

from api.core.models import (
    SupportTicket,
    TicketComment,
    TicketAttachment,
    TicketActivityLog,
    SLAConfig,
    CatchmentPoint,
)
from api.core.serializers.tickets import (
    SupportTicketListSerializer,
    SupportTicketDetailSerializer,
    SupportTicketWriteSerializer,
    TicketCommentSerializer,
    TicketAttachmentSerializer,
    TicketActivityLogSerializer,
)


# ============================================================================
# HELPERS
# ============================================================================

def _get_accessible_point_ids(user):
    """Devuelve IDs de puntos accesibles para el usuario."""
    if user.is_staff or user.is_superuser:
        return set(CatchmentPoint.objects.values_list("id", flat=True))
    return set(
        CatchmentPoint.objects.filter(
            Q(owner_user=user) | Q(users_viewers=user)
        ).values_list("id", flat=True)
    )


def _find_sla_config(ticket):
    """
    Busca la SLAConfig más específica para un ticket.
    Orden de prioridad: más campos coincidentes = más específico.
    """
    point = ticket.point_catchment
    client = point.project.client if point.project else None
    project = point.project
    category = ticket.category
    priority = ticket.priority

    qs = SLAConfig.objects.filter(is_active=True)

    # Construir querysets candidatos ordenados por especificidad
    candidates = []

    # 1. Más específico: cliente + proyecto + categoría + prioridad
    if client and project and category and priority:
        c = qs.filter(client=client, project=project, category=category, priority=priority).first()
        if c:
            return c

    # 2. cliente + proyecto + categoría
    if client and project and category:
        c = qs.filter(client=client, project=project, category=category, priority__isnull=True).first()
        if c:
            return c

    # 3. cliente + proyecto + prioridad
    if client and project and priority:
        c = qs.filter(client=client, project=project, category__isnull=True, priority=priority).first()
        if c:
            return c

    # 4. cliente + proyecto
    if client and project:
        c = qs.filter(client=client, project=project, category__isnull=True, priority__isnull=True).first()
        if c:
            return c

    # 5. cliente + categoría + prioridad
    if client and category and priority:
        c = qs.filter(client=client, project__isnull=True, category=category, priority=priority).first()
        if c:
            return c

    # 6. cliente + categoría
    if client and category:
        c = qs.filter(client=client, project__isnull=True, category=category, priority__isnull=True).first()
        if c:
            return c

    # 7. cliente + prioridad
    if client and priority:
        c = qs.filter(client=client, project__isnull=True, category__isnull=True, priority=priority).first()
        if c:
            return c

    # 8. solo cliente
    if client:
        c = qs.filter(client=client, project__isnull=True, category__isnull=True, priority__isnull=True).first()
        if c:
            return c

    # 9. proyecto + categoría + prioridad
    if project and category and priority:
        c = qs.filter(client__isnull=True, project=project, category=category, priority=priority).first()
        if c:
            return c

    # 10. categoría + prioridad (global)
    if category and priority:
        c = qs.filter(client__isnull=True, project__isnull=True, category=category, priority=priority).first()
        if c:
            return c

    # 11. solo categoría
    if category:
        c = qs.filter(client__isnull=True, project__isnull=True, category=category, priority__isnull=True).first()
        if c:
            return c

    # 12. solo prioridad
    if priority:
        c = qs.filter(client__isnull=True, project__isnull=True, category__isnull=True, priority=priority).first()
        if c:
            return c

    # 13. Global (todo null)
    c = qs.filter(client__isnull=True, project__isnull=True, category__isnull=True, priority__isnull=True).first()
    return c


def _apply_sla_to_ticket(ticket):
    """Busca SLA y calcula deadlines."""
    sla = _find_sla_config(ticket)
    if sla:
        ticket.sla_config = sla
        now = ticket.created or timezone.now()
        ticket.sla_deadline_response = now + timedelta(hours=sla.response_time_hours)
        ticket.sla_deadline_resolution = now + timedelta(hours=sla.resolution_time_hours)
    else:
        ticket.sla_config = None
        ticket.sla_deadline_response = None
        ticket.sla_deadline_resolution = None
    return ticket


def _log_activity(ticket, user, field_name, old_value, new_value):
    """Registra un cambio en el ticket."""
    TicketActivityLog.objects.create(
        ticket=ticket,
        user=user,
        field_name=field_name,
        old_value=str(old_value)[:500] if old_value is not None else None,
        new_value=str(new_value)[:500] if new_value is not None else None,
    )


# ============================================================================
# ENDPOINTS
# ============================================================================

class TicketsListCreateView(APIView):
    """
    GET  /api/ik/tickets/      → listar tickets accesibles
    POST /api/ik/tickets/      → crear ticket
    """
    permission_classes = [IsAuthenticated]

    throttle_classes = [TicketRateThrottle]
    def get(self, request):
        user = request.user
        accessible_ids = _get_accessible_point_ids(user)

        # Filtros opcionales
        status_filter = request.query_params.get("status")
        origin_filter = request.query_params.get("origin")
        category_filter = request.query_params.get("category")
        priority_filter = request.query_params.get("priority")
        assigned_to = request.query_params.get("assigned_to")
        point_id = request.query_params.get("point_catchment")
        search = request.query_params.get("search")

        qs = SupportTicket.objects.filter(
            point_catchment_id__in=accessible_ids,
            is_active=True,
        ).select_related(
            "point_catchment", "point_catchment__project", "point_catchment__project__client",
            "created_by", "assigned_to",
        ).prefetch_related("comments")

        if status_filter:
            qs = qs.filter(status=status_filter)
        if origin_filter:
            qs = qs.filter(origin=origin_filter)
        if category_filter:
            qs = qs.filter(category=category_filter)
        if priority_filter:
            qs = qs.filter(priority=priority_filter)
        if assigned_to:
            qs = qs.filter(assigned_to_id=assigned_to)
        if point_id:
            qs = qs.filter(point_catchment_id=point_id)
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )

        qs = qs.order_by("-created")

        # Paginación
        paginator = PageNumberPagination()
        result_page = paginator.paginate_queryset(qs, request)
        serializer = SupportTicketListSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        user = request.user
        data = request.data.copy()

        # Validar que el punto sea accesible
        point_id = data.get("point_catchment")
        accessible_ids = _get_accessible_point_ids(user)
        if point_id:
            try:
                point_id_int = int(point_id)
            except (ValueError, TypeError):
                return Response({"error": "point_id debe ser un entero válido."}, status=status.HTTP_400_BAD_REQUEST)
            if point_id_int not in accessible_ids:
                return Response({"error": "No tienes acceso a este punto."}, status=status.HTTP_403_FORBIDDEN)

        # Si el usuario no es staff, forzar origin=CLIENTE y source=APP_CLIENTE
        if not (user.is_staff or user.is_superuser):
            data["origin"] = "CLIENTE"
            data["source"] = "APP_CLIENTE"

        serializer = SupportTicketWriteSerializer(data=data)
        if serializer.is_valid():
            ticket = serializer.save(created_by=user)
            ticket = _apply_sla_to_ticket(ticket)
            ticket.save(update_fields=[
                "sla_config", "sla_deadline_response", "sla_deadline_resolution"
            ])
            _log_activity(ticket, user, "CREACIÓN", None, "Ticket creado")
            return Response(
                SupportTicketDetailSerializer(ticket, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TicketDetailUpdateView(APIView):
    """
    GET    /api/ik/tickets/<id>/  → detalle
    PATCH  /api/ik/tickets/<id>/  → actualizar parcial
    """
    permission_classes = [IsAuthenticated]

    throttle_classes = [TicketRateThrottle]
    def _get_ticket(self, pk, user):
        accessible_ids = _get_accessible_point_ids(user)
        try:
            ticket = SupportTicket.objects.select_related(
                "point_catchment", "point_catchment__project", "point_catchment__project__client",
                "created_by", "assigned_to", "sla_config",
            ).prefetch_related(
                "comments", "comments__author",
                "activity_logs", "activity_logs__user",
                "attachments",
            ).get(pk=pk, point_catchment_id__in=accessible_ids)
        except SupportTicket.DoesNotExist:
            return None
        return ticket

    def get(self, request, pk):
        ticket = self._get_ticket(pk, request.user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SupportTicketDetailSerializer(ticket, context={"request": request})
        return Response(serializer.data)

    def patch(self, request, pk):
        user = request.user
        ticket = self._get_ticket(pk, user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        # Clientes solo pueden actualizar ciertos campos
        allowed_fields = ["title", "description", "priority", "category"]
        if user.is_staff or user.is_superuser:
            allowed_fields.extend(["assigned_to", "status", "is_active"])

        data = {k: v for k, v in request.data.items() if k in allowed_fields}

        # Guardar valores antiguos para log
        old_values = {}
        for field in data:
            old_values[field] = getattr(ticket, field, None)

        serializer = SupportTicketWriteSerializer(ticket, data=data, partial=True)
        if serializer.is_valid():
            updated_ticket = serializer.save()

            # Logs de actividad
            for field, old_val in old_values.items():
                new_val = getattr(updated_ticket, field, None)
                if str(old_val) != str(new_val):
                    _log_activity(updated_ticket, user, field, old_val, new_val)

            # Si cambió a RESUELTO, registrar fecha
            if updated_ticket.status == "RESUELTO" and not updated_ticket.resolved_at:
                updated_ticket.resolved_at = timezone.now()
                updated_ticket.save(update_fields=["resolved_at"])
                _log_activity(updated_ticket, user, "resolved_at", None, updated_ticket.resolved_at)

            # Si cambió a CERRADO, registrar fecha
            if updated_ticket.status == "CERRADO" and not updated_ticket.closed_at:
                updated_ticket.closed_at = timezone.now()
                if not updated_ticket.resolved_at:
                    updated_ticket.resolved_at = timezone.now()
                updated_ticket.save(update_fields=["closed_at", "resolved_at"])
                _log_activity(updated_ticket, user, "closed_at", None, updated_ticket.closed_at)

            return Response(
                SupportTicketDetailSerializer(updated_ticket, context={"request": request}).data
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TicketCommentsView(APIView):
    """
    GET  /api/ik/tickets/<id>/comments/  → listar comentarios
    POST /api/ik/tickets/<id>/comments/  → agregar comentario
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [TicketRateThrottle]

    def _get_ticket(self, pk, user):
        accessible_ids = _get_accessible_point_ids(user)
        try:
            return SupportTicket.objects.get(pk=pk, point_catchment_id__in=accessible_ids)
        except SupportTicket.DoesNotExist:
            return None

    def get(self, request, pk):
        user = request.user
        ticket = self._get_ticket(pk, user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        qs = ticket.comments.select_related("author").prefetch_related("attachments")
        # Clientes no ven notas internas
        if not (user.is_staff or user.is_superuser):
            qs = qs.filter(is_internal=False)

        qs = qs.order_by("created")
        paginator = PageNumberPagination()
        result_page = paginator.paginate_queryset(qs, request)
        serializer = TicketCommentSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, pk):
        user = request.user
        ticket = self._get_ticket(pk, user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        data["ticket"] = ticket.id

        # Clientes no pueden crear notas internas
        if not (user.is_staff or user.is_superuser):
            data["is_internal"] = False

        serializer = TicketCommentSerializer(data=data)
        if serializer.is_valid():
            comment = serializer.save(author=user)

            # Si es la primera respuesta de staff, marcar SLA respondido
            if (user.is_staff or user.is_superuser) and not ticket.sla_responded_at:
                ticket.sla_responded_at = timezone.now()
                ticket.save(update_fields=["sla_responded_at"])
                _log_activity(ticket, user, "sla_responded_at", None, ticket.sla_responded_at)

            # Si el comentario incluye cambio de estado
            status_change = data.get("status_change")
            if status_change and (user.is_staff or user.is_superuser):
                old_status = ticket.status
                ticket.status = status_change
                ticket.save(update_fields=["status"])
                _log_activity(ticket, user, "status", old_status, status_change)

            return Response(TicketCommentSerializer(comment).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TicketAssignView(APIView):
    """
    POST /api/ik/tickets/<id>/assign/
    Body: {"assigned_to": user_id}
    """
    throttle_classes = [TicketRateThrottle]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if not (user.is_staff or user.is_superuser):
            return Response({"error": "Solo staff puede asignar tickets."}, status=status.HTTP_403_FORBIDDEN)

        accessible_ids = _get_accessible_point_ids(user)
        try:
            ticket = SupportTicket.objects.get(pk=pk, point_catchment_id__in=accessible_ids)
        except SupportTicket.DoesNotExist:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        assigned_to_id = request.data.get("assigned_to")
        if assigned_to_id is not None:
            try:
                assigned_to_id = int(assigned_to_id)
            except (ValueError, TypeError):
                return Response({"error": "assigned_to debe ser un entero válido."}, status=status.HTTP_400_BAD_REQUEST)
            from api.core.models import User
            if not User.objects.filter(id=assigned_to_id).exists():
                return Response({"error": "Usuario asignado no existe."}, status=status.HTTP_400_BAD_REQUEST)

        old_assignee = ticket.assigned_to_id
        ticket.assigned_to_id = assigned_to_id
        ticket.save(update_fields=["assigned_to"])
        _log_activity(ticket, user, "assigned_to", old_assignee, assigned_to_id)

        return Response({"detail": "Ticket asignado correctamente."})


class TicketStatusChangeView(APIView):
    """
    POST /api/ik/tickets/<id>/status/
    Body: {"status": "RESUELTO"}
    """
    throttle_classes = [TicketRateThrottle]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if not (user.is_staff or user.is_superuser):
            return Response({"error": "Solo staff puede cambiar estado."}, status=status.HTTP_403_FORBIDDEN)

        accessible_ids = _get_accessible_point_ids(user)
        try:
            ticket = SupportTicket.objects.get(pk=pk, point_catchment_id__in=accessible_ids)
        except SupportTicket.DoesNotExist:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("status")
        if new_status not in [c[0] for c in SupportTicket.STATUS_CHOICES]:
            return Response({"error": "Estado inválido."}, status=status.HTTP_400_BAD_REQUEST)

        old_status = ticket.status
        ticket.status = new_status

        update_fields = ["status"]
        if new_status == "RESUELTO" and not ticket.resolved_at:
            ticket.resolved_at = timezone.now()
            update_fields.append("resolved_at")
        if new_status == "CERRADO":
            if not ticket.resolved_at:
                ticket.resolved_at = timezone.now()
                update_fields.append("resolved_at")
            if not ticket.closed_at:
                ticket.closed_at = timezone.now()
                update_fields.append("closed_at")

        ticket.save(update_fields=update_fields)
        _log_activity(ticket, user, "status", old_status, new_status)

        return Response({"detail": f"Estado cambiado a {new_status}."})


class TicketStatsView(APIView):
    """
    GET /api/ik/tickets/stats/
    Dashboard de soporte: conteos por estado, categoría, prioridad, origen.
    """
    throttle_classes = [TicketRateThrottle]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        accessible_ids = _get_accessible_point_ids(user)
        base_qs = SupportTicket.objects.filter(
            point_catchment_id__in=accessible_ids,
            is_active=True,
        )

        by_status = {
            item["status"]: item["count"]
            for item in base_qs.values("status").annotate(count=Count("id"))
        }
        by_category = {
            item["category"]: item["count"]
            for item in base_qs.values("category").annotate(count=Count("id"))
        }
        by_priority = {
            item["priority"]: item["count"]
            for item in base_qs.values("priority").annotate(count=Count("id"))
        }
        by_origin = {
            item["origin"]: item["count"]
            for item in base_qs.values("origin").annotate(count=Count("id"))
        }

        # SLA: vencidos (resolución)
        now = timezone.now()
        overdue_resolution = base_qs.filter(
            sla_deadline_resolution__lt=now,
            status__in=["ABIERTO", "EN_ANALISIS", "ESPERA_CLIENTE", "ESPERA_PROVEEDOR"],
        ).count()
        overdue_response = base_qs.filter(
            sla_deadline_response__lt=now,
            sla_responded_at__isnull=True,
            status__in=["ABIERTO", "EN_ANALISIS", "ESPERA_CLIENTE", "ESPERA_PROVEEDOR"],
        ).count()

        return Response({
            "total": base_qs.count(),
            "by_status": by_status,
            "by_category": by_category,
            "by_priority": by_priority,
            "by_origin": by_origin,
            "sla_overdue_response": overdue_response,
            "sla_overdue_resolution": overdue_resolution,
        })


class TicketAttachmentsView(APIView):
    """
    GET  /api/ik/tickets/<id>/attachments/  → listar adjuntos del ticket
    POST /api/ik/tickets/<id>/attachments/  → subir adjunto al ticket
    """
    throttle_classes = [TicketRateThrottle]
    permission_classes = [IsAuthenticated]

    def _get_ticket(self, pk, user):
        accessible_ids = _get_accessible_point_ids(user)
        try:
            return SupportTicket.objects.get(pk=pk, point_catchment_id__in=accessible_ids)
        except SupportTicket.DoesNotExist:
            return None

    def get(self, request, pk):
        ticket = self._get_ticket(pk, request.user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        qs = ticket.attachments.select_related("uploaded_by")
        serializer = TicketAttachmentSerializer(qs, many=True, context={"request": request})
        return Response({"attachments": serializer.data})

    def post(self, request, pk):
        user = request.user
        ticket = self._get_ticket(pk, user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "No se envió archivo."}, status=status.HTTP_400_BAD_REQUEST)

        # Validación de tipo y tamaño
        ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".xls", ".doc", ".docx", ".txt", ".csv"}
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

        import os
        ext = os.path.splitext(file_obj.name.lower())[1]
        if ext not in ALLOWED_EXTENSIONS:
            return Response(
                {"error": f"Tipo de archivo no permitido. Extensiones válidas: {', '.join(ALLOWED_EXTENSIONS)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if file_obj.size > MAX_FILE_SIZE:
            return Response(
                {"error": "El archivo excede el tamaño máximo permitido (10 MB)."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Sanitizar nombre original
        safe_name = os.path.basename(file_obj.name)

        attachment = TicketAttachment.objects.create(
            ticket=ticket,
            file=file_obj,
            original_name=safe_name,
            uploaded_by=user,
        )
        serializer = TicketAttachmentSerializer(attachment, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)
