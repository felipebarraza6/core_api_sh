"""
API ik — Subsistema de Tickets de Soporte + SLA.

Endpoints bajo /api/ik/tickets/
Nada toca el legacy (NotificationsCatchment).
"""

from datetime import datetime, timedelta

from django.db.models import Q, Count, F, Exists, OuterRef
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from .throttles import TicketRateThrottle
from rest_framework import status
from rest_framework.pagination import PageNumberPagination

from api.core.models import (
    SupportTicket,
    SupportTicketTask,
    TicketCategory,
    TicketComment,
    TicketCommentLike,
    TicketAttachment,
    TicketActivityLog,
    TicketNotification,
    SLAConfig,
    CatchmentPoint,
)
from api.core.serializers.tickets import (
    SupportTicketListSerializer,
    SupportTicketDetailSerializer,
    SupportTicketWriteSerializer,
    SupportTicketTaskSerializer,
    SupportTicketTaskWriteSerializer,
    TicketCommentSerializer,
    TicketAttachmentSerializer,
    TicketAttachmentWriteSerializer,
    TicketActivityLogSerializer,
    TicketCategorySerializer,
    TicketCategoryWriteSerializer,
    SLAConfigSerializer,
    SLAConfigWriteSerializer,
    TicketDashboardRowSerializer,
    FileDriveSerializer,
    TicketNotificationSerializer,
)
from api.core.signals.tickets import (
    _notify_category_operators,
    _notify_scheduled_date_cancelled,
    _notify_scheduled_date_confirmed,
    _notify_comment_mentions,
    _notify_ticket_assigned,
    _notify_ticket_references,
    _notify_ticket_status_changed,
    _ticket_involved_users,
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
    Usa el primer punto vinculado para inferir cliente/proyecto.
    """
    point = ticket.points.first()
    client = point.project.client if point and point.project else None
    project = point.project if point else None
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
    """Busca SLA y calcula deadlines respetando horario hábil si aplica.

    Los tickets con origen interno se tratan como borradores o eventos
    internos; no reciben SLA hasta que sean convertidos/pasados a origen
    cliente u operaciones.
    """
    if ticket.origin == "INTERNO":
        ticket.sla_config = None
        ticket.sla_deadline_response = None
        ticket.sla_deadline_resolution = None
        return ticket

    sla = _find_sla_config(ticket)
    if sla:
        ticket.sla_config = sla
        now = timezone.now()
        if sla.business_hours_only:
            from api.core.utils.business_hours import add_business_hours
            ticket.sla_deadline_response = add_business_hours(
                now, sla.response_time_hours
            )
            ticket.sla_deadline_resolution = add_business_hours(
                now, sla.resolution_time_hours
            )
        else:
            ticket.sla_deadline_response = now + timedelta(hours=sla.response_time_hours)
            ticket.sla_deadline_resolution = now + timedelta(hours=sla.resolution_time_hours)
    else:
        ticket.sla_config = None
        ticket.sla_deadline_response = None
        ticket.sla_deadline_resolution = None
    return ticket


# Estados donde el reloj del SLA queda pausado (no corre ni se marca vencido).
SLA_PAUSED_STATUSES = {"ESPERA_CLIENTE", "ESPERA_PROVEEDOR"}


def _sync_sla_pause(ticket, old_status, new_status):
    """Pausa/reanuda el reloj SLA al entrar/salir de estados de espera.

    Al entrar en espera se guarda `sla_paused_at` y el ticket deja de
    contarse como vencido. Al salir, los deadlines se desplazan hacia el
    futuro por el tiempo que estuvo pausado y se limpia `sla_paused_at`.

    Devuelve la lista de campos modificados (para `update_fields`).
    """
    now = timezone.now()
    fields = []
    was_paused = old_status in SLA_PAUSED_STATUSES
    is_paused = new_status in SLA_PAUSED_STATUSES

    if is_paused and not ticket.sla_paused_at:
        ticket.sla_paused_at = now
        fields.append("sla_paused_at")
    elif was_paused and not is_paused and ticket.sla_paused_at:
        elapsed = now - ticket.sla_paused_at
        if ticket.sla_deadline_response:
            ticket.sla_deadline_response += elapsed
            fields.append("sla_deadline_response")
        if ticket.sla_deadline_resolution:
            ticket.sla_deadline_resolution += elapsed
            fields.append("sla_deadline_resolution")
        ticket.sla_paused_at = None
        fields.append("sla_paused_at")
    return fields


def _log_activity(ticket, user, field_name, old_value, new_value):
    """Registra un cambio en el ticket."""
    TicketActivityLog.objects.create(
        ticket=ticket,
        user=user,
        field_name=field_name,
        old_value=str(old_value)[:500] if old_value is not None else None,
        new_value=str(new_value)[:500] if new_value is not None else None,
    )


def _mark_sla_responded(ticket, user):
    """Marca la primera respuesta SLA con la primera accion de staff.

    Una accion de staff (cambio de estado, asignacion, fecha agendada,
    reporte de visita o comentario) cuenta como respuesta del soporte.
    """
    if not (user.is_staff or user.is_superuser):
        return ticket
    if not ticket.sla_responded_at:
        ticket.sla_responded_at = timezone.now()
        ticket.save(update_fields=["sla_responded_at"])
        _log_activity(ticket, user, "sla_responded_at", None, ticket.sla_responded_at)
    return ticket


def _resolve_work_order_category(value):
    """
    Valida un id de categoría de orden de trabajo (tipo WORK_ORDER y activa).
    Retorna la TicketCategory, o None si es inválida/inexistente.
    """
    if value is None:
        return None
    try:
        return TicketCategory.objects.filter(
            id=int(value),
            category_type="WORK_ORDER",
            parent__isnull=False,
            is_active=True,
        ).first()
    except (ValueError, TypeError):
        return None


ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".xls",
    ".doc", ".docx", ".txt", ".csv",
}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


def _validate_upload(file_obj):
    """Valida tipo y tamaño de un archivo subido. Retorna error o None."""
    import os
    ext = os.path.splitext(file_obj.name.lower())[1]
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return (
            f"Tipo de archivo no permitido. Extensiones válidas: "
            f"{', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
        )
    if file_obj.size > MAX_UPLOAD_SIZE:
        return "El archivo excede el tamaño máximo permitido (10 MB)."
    return None


# ============================================================================
# ENDPOINTS
# ============================================================================

class TicketPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000


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
        category_type_filter = request.query_params.get("category_type")
        priority_filter = request.query_params.get("priority")
        assigned_to = request.query_params.get("assigned_to")
        ticket_id_filter = request.query_params.get("id")
        point_id = request.query_params.get("point_id") or request.query_params.get("point_catchment")
        project_id = request.query_params.get("project_id")
        scheduled_date = request.query_params.get("scheduled_date")
        has_visit_report = request.query_params.get("has_visit_report")
        search = request.query_params.get("search")

        # Staff ve tickets de sus puntos + tickets de operaciones sin punto
        if user.is_staff or user.is_superuser:
            qs = SupportTicket.objects.filter(
                Q(points__id__in=accessible_ids) | Q(origin="OPERACIONES"),
                is_active=True,
            ).select_related(
                "created_by", "assigned_to", "category",
            ).prefetch_related(
                "points", "points__project", "points__project__client", "comments"
            ).distinct()
        else:
            qs = SupportTicket.objects.filter(
                points__id__in=accessible_ids,
                is_active=True,
            ).select_related(
                "created_by", "assigned_to", "category",
            ).prefetch_related(
                "points", "points__project", "points__project__client", "comments"
            ).distinct()

        if status_filter:
            qs = qs.filter(status=status_filter)
        if origin_filter:
            qs = qs.filter(origin=origin_filter)
        if category_filter:
            # Filtrar por categoria exacta o por cualquiera de sus subcategorias.
            qs = qs.filter(
                Q(category_id=category_filter) | Q(category__parent_id=category_filter)
            )
        if category_type_filter:
            qs = qs.filter(category__category_type=category_type_filter.upper())
        if priority_filter:
            qs = qs.filter(priority=priority_filter)
        if assigned_to:
            qs = qs.filter(assigned_to_id=assigned_to)
        if ticket_id_filter:
            # Búsqueda parcial: id=4 también encuentra 44, 143, 443, etc.
            qs = qs.filter(id__icontains=ticket_id_filter)
        if point_id:
            qs = qs.filter(points__id=point_id)
        if project_id:
            try:
                qs = qs.filter(points__project_id=int(project_id))
            except (ValueError, TypeError):
                return Response(
                    {"error": "project_id debe ser un entero válido."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        if scheduled_date:
            qs = qs.filter(scheduled_date=scheduled_date)
        if has_visit_report is not None:
            if has_visit_report.lower() in ("true", "1", "yes"):
                qs = qs.exclude(visit_report__isnull=True).exclude(visit_report__exact="")
            elif has_visit_report.lower() in ("false", "0", "no"):
                qs = qs.filter(visit_report__isnull=True) | qs.filter(visit_report__exact="")
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )

        # Filtro por rango de fecha de creación
        created_from = request.query_params.get("created_from")
        created_to = request.query_params.get("created_to")
        if created_from:
            try:
                created_from_dt = timezone.make_aware(
                    datetime.combine(datetime.fromisoformat(created_from), datetime.min.time())
                )
                qs = qs.filter(created__gte=created_from_dt)
            except (ValueError, TypeError):
                return Response(
                    {"error": "created_from debe tener formato YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        if created_to:
            try:
                created_to_dt = timezone.make_aware(
                    datetime.combine(datetime.fromisoformat(created_to), datetime.max.time())
                )
                qs = qs.filter(created__lte=created_to_dt)
            except (ValueError, TypeError):
                return Response(
                    {"error": "created_to debe tener formato YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        qs = qs.order_by("-created")

        # Paginación
        paginator = TicketPagination()
        result_page = paginator.paginate_queryset(qs, request)
        serializer = SupportTicketListSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        user = request.user
        data = request.data.copy()
        accessible_ids = _get_accessible_point_ids(user)

        # Determinar origen; solo staff puede crear tickets de operaciones
        origin = data.get("origin", "CLIENTE")
        if origin == "OPERACIONES" and not (user.is_staff or user.is_superuser):
            return Response(
                {"error": "Solo staff puede crear tickets de operaciones."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Validar formato de puntos solo si se envían (los tickets generales
        # pueden no estar ligados a ningún punto).
        point_ids = data.get("points", [])
        if point_ids:
            if not isinstance(point_ids, list):
                return Response({"error": "points debe ser una lista de IDs."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                point_ids_int = [int(pid) for pid in point_ids]
            except (ValueError, TypeError):
                return Response({"error": "Cada point_id debe ser un entero válido."}, status=status.HTTP_400_BAD_REQUEST)

            accessible_ids = _get_accessible_point_ids(user)
            unauthorized = [pid for pid in point_ids_int if pid not in accessible_ids]
            if unauthorized:
                return Response({"error": "No tienes acceso a algunos puntos."}, status=status.HTTP_403_FORBIDDEN)

        # Si el usuario no es staff, forzar origin=CLIENTE y source=APP_CLIENTE
        if not (user.is_staff or user.is_superuser):
            data["origin"] = "CLIENTE"
            data["source"] = "APP_CLIENTE"

        serializer = SupportTicketWriteSerializer(data=data)
        if serializer.is_valid():
            ticket = serializer.save(created_by=user)
            ticket = _apply_sla_to_ticket(ticket)
            update_fields = [
                "sla_config", "sla_deadline_response", "sla_deadline_resolution"
            ]
            # Si se crea ya en estado de espera, pausar el SLA desde el inicio.
            if ticket.status in SLA_PAUSED_STATUSES and not ticket.sla_paused_at:
                ticket.sla_paused_at = timezone.now()
                update_fields.append("sla_paused_at")
            ticket.save(update_fields=update_fields)
            _log_activity(ticket, user, "CREACIÓN", None, "Ticket creado")
            _notify_category_operators(ticket.id)
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
                "created_by", "assigned_to", "sla_config", "category",
            ).prefetch_related(
                "points", "points__project", "points__project__client",
                "comments", "comments__author",
                "activity_logs", "activity_logs__user",
                "attachments",
            ).get(pk=pk)
        except SupportTicket.DoesNotExist:
            return None

        # Staff tambien accede a tickets de operaciones sin punto
        if user.is_staff or user.is_superuser:
            if ticket.origin != "OPERACIONES" and not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        else:
            if not ticket.points.filter(id__in=accessible_ids).exists():
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
        allowed_fields = ["title", "description"]
        if user.is_staff or user.is_superuser:
            allowed_fields.extend([
                "points", "assigned_to", "status", "is_active",
                "scheduled_date", "visit_report", "priority", "category",
                "work_order_category",
                "origin", "source",
            ])

        data = {k: v for k, v in request.data.items() if k in allowed_fields}

        # Guardar valores antiguos para log
        old_values = {}
        for field in data:
            old_values[field] = getattr(ticket, field, None)

        # Preservar puntos actuales para el recálculo de SLA si no se envían
        old_points = set(ticket.points.values_list("id", flat=True))

        serializer = SupportTicketWriteSerializer(ticket, data=data, partial=True)
        if serializer.is_valid():
            updated_ticket = serializer.save()

            # Logs de actividad
            changed_any = False
            for field, old_val in old_values.items():
                new_val = getattr(updated_ticket, field, None)
                if str(old_val) != str(new_val):
                    _log_activity(updated_ticket, user, field, old_val, new_val)
                    changed_any = True

            # Cualquier actualizacion de staff cuenta como primera respuesta SLA
            if changed_any:
                _mark_sla_responded(updated_ticket, user)

            # Recalcular SLA si cambiaron factores determinantes
            sla_fields = {"category", "priority", "points", "origin"}
            if sla_fields & set(data.keys()):
                # Si cambió origin de INTERNO a CLIENTE/OPERACIONES, o cambiaron
                # puntos, se debe re-evaluar la configuración SLA.
                updated_ticket = _apply_sla_to_ticket(updated_ticket)
                updated_ticket.save(update_fields=[
                    "sla_config", "sla_deadline_response", "sla_deadline_resolution"
                ])

            # Si cambió a RESUELTO, registrar fecha
            if updated_ticket.status == "RESUELTO" and not updated_ticket.resolved_at:
                updated_ticket.resolved_at = timezone.now()
                if not updated_ticket.sla_resolved_at:
                    updated_ticket.sla_resolved_at = timezone.now()
                if not updated_ticket.sla_responded_at:
                    updated_ticket.sla_responded_at = updated_ticket.resolved_at
                updated_ticket.save(update_fields=["resolved_at", "sla_resolved_at", "sla_responded_at"])
                _log_activity(updated_ticket, user, "resolved_at", None, updated_ticket.resolved_at)

            # Si cambió a CERRADO, registrar fecha
            if updated_ticket.status == "CERRADO" and not updated_ticket.closed_at:
                updated_ticket.closed_at = timezone.now()
                if not updated_ticket.resolved_at:
                    updated_ticket.resolved_at = timezone.now()
                if not updated_ticket.sla_resolved_at:
                    updated_ticket.sla_resolved_at = timezone.now()
                if not updated_ticket.sla_responded_at:
                    updated_ticket.sla_responded_at = updated_ticket.resolved_at
                updated_ticket.save(update_fields=["closed_at", "resolved_at", "sla_resolved_at", "sla_responded_at"])
                _log_activity(updated_ticket, user, "closed_at", None, updated_ticket.closed_at)

            # Pausar/reanudar el reloj SLA al entrar/salir de estados de espera
            if "status" in data:
                pause_fields = _sync_sla_pause(
                    updated_ticket, old_values.get("status"), updated_ticket.status
                )
                if pause_fields:
                    updated_ticket.save(update_fields=pause_fields)

            # Notificación por correo en cambios de estado y/o asignación
            if "status" in data and str(old_values.get("status")) != str(updated_ticket.status):
                _notify_ticket_status_changed(
                    updated_ticket, user, old_values.get("status"), updated_ticket.status
                )
            if "assigned_to" in data:
                old_assignee_id = getattr(old_values.get("assigned_to"), "id", None)
                if old_assignee_id != updated_ticket.assigned_to_id and updated_ticket.assigned_to_id:
                    from api.core.models import User
                    new_assignee = User.objects.get(id=updated_ticket.assigned_to_id)
                    _notify_ticket_assigned(updated_ticket, user, new_assignee)

            return Response(
                SupportTicketDetailSerializer(updated_ticket, context={"request": request}).data
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """
        DELETE /api/ik/tickets/<id>/  → eliminación lógica (solo staff/superuser).
        """
        user = request.user
        if not (user.is_staff or user.is_superuser):
            return Response(
                {"error": "No tiene permisos para eliminar tickets."},
                status=status.HTTP_403_FORBIDDEN
            )

        ticket = self._get_ticket(pk, user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if not ticket.is_active:
            return Response(
                {"error": "El ticket ya ha sido eliminado."},
                status=status.HTTP_400_BAD_REQUEST
            )

        ticket.is_active = False
        ticket.save(update_fields=["is_active"])
        _log_activity(ticket, user, "is_active", True, False)

        return Response(status=status.HTTP_204_NO_CONTENT)


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
            ticket = SupportTicket.objects.get(pk=pk)
        except SupportTicket.DoesNotExist:
            return None

        if user.is_staff or user.is_superuser:
            if ticket.origin != "OPERACIONES" and not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        else:
            if not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        return ticket

    def get(self, request, pk):
        user = request.user
        ticket = self._get_ticket(pk, user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        qs = ticket.comments.select_related("author").prefetch_related("attachments")
        # Clientes no ven notas internas
        if not (user.is_staff or user.is_superuser):
            qs = qs.filter(is_internal=False)

        # Anotar me gusta para evitar N+1
        qs = qs.annotate(
            like_count=Count("likes", distinct=True),
            liked_by_me=Exists(
                TicketCommentLike.objects.filter(
                    comment_id=OuterRef("pk"), user_id=user.id
                )
            ),
        )

        qs = qs.order_by("created")
        paginator = PageNumberPagination()
        result_page = paginator.paginate_queryset(qs, request)
        serializer = TicketCommentSerializer(
            result_page, many=True, context={"request": request}
        )
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

        # Hilos: validar que el comentario padre pertenezca al mismo ticket
        # y que un cliente no responda a una nota interna.
        save_kwargs = {"author": user}
        parent_id = request.data.get("parent_id")
        if parent_id is not None:
            try:
                parent_id = int(parent_id)
            except (TypeError, ValueError):
                return Response(
                    {"error": "parent_id debe ser un id de comentario."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                parent = TicketComment.objects.get(pk=parent_id, ticket=ticket)
            except TicketComment.DoesNotExist:
                return Response(
                    {"error": "El comentario padre debe pertenecer al mismo ticket."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not (user.is_staff or user.is_superuser) and parent.is_internal:
                return Response(
                    {"error": "Comentario no encontrado."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            save_kwargs["parent_id"] = parent_id

        serializer = TicketCommentSerializer(data=data)
        if serializer.is_valid():
            comment = serializer.save(**save_kwargs)
            is_internal = comment.is_internal

            # Notificar menciones @usuario del comentario (email + in-app).
            _notify_comment_mentions(comment, ticket, user)
            # Notificar referencias a otros tickets #<id> (email + in-app).
            _notify_ticket_references(comment, ticket, user)

            # Si es la primera respuesta de staff y no es interna, marcar SLA respondido
            if (
                (user.is_staff or user.is_superuser)
                and not is_internal
                and not ticket.sla_responded_at
            ):
                ticket.sla_responded_at = timezone.now()
                ticket.save(update_fields=["sla_responded_at"])
                _log_activity(ticket, user, "sla_responded_at", None, ticket.sla_responded_at)

            # Si el comentario incluye cambio de estado
            status_change = data.get("status_change")
            if status_change and (user.is_staff or user.is_superuser):
                valid_statuses = [c[0] for c in SupportTicket.STATUS_CHOICES]
                if status_change not in valid_statuses:
                    return Response(
                        {"error": "Estado inválido."}, status=status.HTTP_400_BAD_REQUEST
                    )

                # Categoría OT: obligatoria al entrar a EN_ORDEN_TRABAJO; al salir se limpia.
                old_work_order_category = ticket.work_order_category
                if status_change == "EN_ORDEN_TRABAJO":
                    woc = (
                        _resolve_work_order_category(request.data.get("work_order_category"))
                        if request.data.get("work_order_category") is not None
                        else ticket.work_order_category
                    )
                    if woc is None:
                        return Response(
                            {
                                "error": (
                                    "Debe seleccionar una categoría de orden de trabajo "
                                    "(work_order_category) para pasar a EN_ORDEN_TRABAJO."
                                )
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:
                    woc = None

                old_status = ticket.status
                ticket.status = status_change
                ticket.work_order_category = woc
                update_fields = ["status"]
                if old_work_order_category != ticket.work_order_category:
                    update_fields.append("work_order_category")

                # Pausar/reanudar el reloj SLA al entrar/salir de espera
                update_fields.extend(_sync_sla_pause(ticket, old_status, status_change))

                terminal_statuses = ("RESUELTO", "CERRADO", "CANCELADO")

                if status_change in terminal_statuses:
                    if not ticket.resolved_at:
                        ticket.resolved_at = timezone.now()
                        update_fields.append("resolved_at")
                else:
                    if ticket.resolved_at:
                        ticket.resolved_at = None
                        update_fields.append("resolved_at")

                if status_change in ("RESUELTO", "CERRADO") and not ticket.sla_resolved_at:
                    ticket.sla_resolved_at = timezone.now()
                    update_fields.append("sla_resolved_at")

                if status_change == "CERRADO":
                    if not ticket.closed_at:
                        ticket.closed_at = timezone.now()
                        update_fields.append("closed_at")
                else:
                    if ticket.closed_at:
                        ticket.closed_at = None
                        update_fields.append("closed_at")

                ticket.save(update_fields=update_fields)
                _log_activity(ticket, user, "status", old_status, status_change)
                if old_work_order_category != ticket.work_order_category:
                    _log_activity(
                        ticket, user, "work_order_category",
                        old_work_order_category, ticket.work_order_category,
                    )
                _mark_sla_responded(ticket, user)
                if status_change != old_status:
                    _notify_ticket_status_changed(ticket, user, old_status, status_change)

            return Response(
                TicketCommentSerializer(comment, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TicketCommentDetailView(APIView):
    """
    DELETE /api/ik/tickets/<id>/comments/<cid>/ → eliminar un comentario.

    Permisos: staff/superuser (cualquier comentario) o el autor del comentario.
    Un cliente nunca puede eliminar notas internas, aunque sea su autor.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [TicketRateThrottle]

    def _get_ticket(self, pk, user):
        accessible_ids = _get_accessible_point_ids(user)
        try:
            ticket = SupportTicket.objects.get(pk=pk)
        except SupportTicket.DoesNotExist:
            return None

        if user.is_staff or user.is_superuser:
            if ticket.origin != "OPERACIONES" and not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        else:
            if not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        return ticket

    def delete(self, request, pk, cid):
        user = request.user
        ticket = self._get_ticket(pk, user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        try:
            comment = TicketComment.objects.get(pk=cid, ticket=ticket)
        except TicketComment.DoesNotExist:
            return Response({"error": "Comentario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        is_staff = user.is_staff or user.is_superuser
        is_author = comment.author_id == user.id
        if not (is_staff or is_author):
            return Response(
                {"error": "No tiene permisos para eliminar este comentario."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Clientes nunca eliminan notas internas, aunque sean el autor.
        if not is_staff and comment.is_internal:
            return Response(
                {"error": "No tiene permisos para eliminar este comentario."},
                status=status.HTTP_403_FORBIDDEN,
            )

        snippet = comment.content[:200]
        comment.delete()
        _log_activity(ticket, user, "comment_deleted", snippet, None)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TicketCommentLikeView(APIView):
    """
    POST /api/ik/tickets/<id>/comments/<cid>/like/ → dar/quitar "me gusta".

    Hace toggle: si ya había like lo quita, si no lo agrega.
    Solo puede dar like quien puede ver el comentario (clientes no a notas internas).
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [TicketRateThrottle]

    def _get_ticket(self, pk, user):
        accessible_ids = _get_accessible_point_ids(user)
        try:
            ticket = SupportTicket.objects.get(pk=pk)
        except SupportTicket.DoesNotExist:
            return None

        if user.is_staff or user.is_superuser:
            if ticket.origin != "OPERACIONES" and not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        else:
            if not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        return ticket

    def post(self, request, pk, cid):
        user = request.user
        ticket = self._get_ticket(pk, user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        try:
            comment = TicketComment.objects.get(pk=cid, ticket=ticket)
        except TicketComment.DoesNotExist:
            return Response({"error": "Comentario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        # Clientes no pueden dar like a notas internas
        if not (user.is_staff or user.is_superuser) and comment.is_internal:
            return Response({"error": "Comentario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        like, created = TicketCommentLike.objects.get_or_create(
            comment=comment, user=user
        )
        if not created:
            like.delete()

        return Response(
            {
                "ok": True,
                "liked": created,
                "like_count": comment.likes.count(),
            },
            status=status.HTTP_200_OK,
        )


class TicketMentionableUsersView(APIView):
    """
    GET /api/ik/tickets/<id>/mentionable_users/ → usuarios que se pueden
    etiquetar con @ en los comentarios de este ticket (involucrados).
    Ideal para el autocomplete del frontend.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [TicketRateThrottle]

    def _get_ticket(self, pk, user):
        accessible_ids = _get_accessible_point_ids(user)
        try:
            ticket = SupportTicket.objects.get(pk=pk)
        except SupportTicket.DoesNotExist:
            return None

        if user.is_staff or user.is_superuser:
            if ticket.origin != "OPERACIONES" and not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        else:
            if not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        return ticket

    def get(self, request, pk):
        user = request.user
        ticket = self._get_ticket(pk, user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        users = _ticket_involved_users(ticket)
        data = [
            {
                "id": u.id,
                "username": u.username,
                "full_name": u.get_full_name(),
                "email": u.email,
            }
            for u in sorted(users, key=lambda u: (u.first_name or "", u.last_name or "", u.username))
        ]
        return Response({"users": data})


class TicketNotificationsView(APIView):
    """
    GET  /api/ik/tickets/notifications/?unread_only=true → lista mis notificaciones in-app.
    POST /api/ik/tickets/notifications/mark-read/       → marca leídas ({"ids": [...]} o {"id": x}).
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [TicketRateThrottle]

    def get(self, request):
        user = request.user
        qs = TicketNotification.objects.filter(user=user).select_related("ticket", "comment")
        unread_only = request.query_params.get("unread_only") in ("true", "1", "True")
        if unread_only:
            qs = qs.filter(is_read=False)

        unread_count = TicketNotification.objects.filter(user=user, is_read=False).count()

        paginator = PageNumberPagination()
        result_page = paginator.paginate_queryset(qs, request)
        serializer = TicketNotificationSerializer(result_page, many=True)
        data = paginator.get_paginated_response(serializer.data).data
        data["unread_count"] = unread_count
        return Response(data)

    def post(self, request):
        user = request.user
        ids = request.data.get("ids") or []
        single_id = request.data.get("id")
        if single_id is not None:
            ids = [single_id]
        if not ids:
            return Response(
                {"error": "Debe enviar ids o id."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        TicketNotification.objects.filter(id__in=ids, user=user).update(is_read=True)
        unread_count = TicketNotification.objects.filter(user=user, is_read=False).count()
        return Response({"ok": True, "unread_count": unread_count})


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
            ticket = SupportTicket.objects.filter(
                Q(pk=pk) & (Q(points__id__in=accessible_ids) | Q(origin="OPERACIONES"))
            ).distinct().get()
        except SupportTicket.DoesNotExist:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        assigned_to_id = request.data.get("assigned_to")
        if assigned_to_id is not None:
            try:
                assigned_to_id = int(assigned_to_id)
            except (ValueError, TypeError):
                return Response({"error": "assigned_to debe ser un entero válido."}, status=status.HTTP_400_BAD_REQUEST)
            from api.core.models import User
            if not User.objects.filter(id=assigned_to_id, is_active=True).exists():
                return Response(
                    {"error": "Usuario asignado no existe o está inactivo."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        old_assignee = ticket.assigned_to_id
        ticket.assigned_to_id = assigned_to_id
        ticket.save(update_fields=["assigned_to"])
        _log_activity(ticket, user, "assigned_to", old_assignee, assigned_to_id)
        _mark_sla_responded(ticket, user)

        if assigned_to_id is not None and assigned_to_id != old_assignee:
            from api.core.models import User
            new_assignee = User.objects.get(id=assigned_to_id)
            _notify_ticket_assigned(ticket, user, new_assignee)

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
            ticket = SupportTicket.objects.filter(
                Q(pk=pk) & (Q(points__id__in=accessible_ids) | Q(origin="OPERACIONES"))
            ).distinct().get()
        except SupportTicket.DoesNotExist:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("status")
        if new_status not in [c[0] for c in SupportTicket.STATUS_CHOICES]:
            return Response({"error": "Estado inválido."}, status=status.HTTP_400_BAD_REQUEST)

        # Categoría OT: obligatoria al entrar a EN_ORDEN_TRABAJO; al salir se limpia.
        old_work_order_category = ticket.work_order_category
        if new_status == "EN_ORDEN_TRABAJO":
            woc = (
                _resolve_work_order_category(request.data.get("work_order_category"))
                if request.data.get("work_order_category") is not None
                else ticket.work_order_category
            )
            if woc is None:
                return Response(
                    {
                        "error": (
                            "Debe seleccionar una categoría de orden de trabajo "
                            "(work_order_category) para pasar a EN_ORDEN_TRABAJO."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            woc = None

        old_status = ticket.status
        ticket.status = new_status
        ticket.work_order_category = woc

        update_fields = ["status"]
        if old_work_order_category != ticket.work_order_category:
            update_fields.append("work_order_category")
        # Pausar/reanudar el reloj SLA al entrar/salir de espera
        update_fields.extend(_sync_sla_pause(ticket, old_status, new_status))
        terminal_statuses = ("RESUELTO", "CERRADO", "CANCELADO")

        if new_status in terminal_statuses:
            if not ticket.resolved_at:
                ticket.resolved_at = timezone.now()
                update_fields.append("resolved_at")
        else:
            if ticket.resolved_at:
                ticket.resolved_at = None
                update_fields.append("resolved_at")

        if new_status in ("RESUELTO", "CERRADO") and not ticket.sla_resolved_at:
            ticket.sla_resolved_at = timezone.now()
            update_fields.append("sla_resolved_at")

        if new_status == "CERRADO":
            if not ticket.closed_at:
                ticket.closed_at = timezone.now()
                update_fields.append("closed_at")
        else:
            if ticket.closed_at:
                ticket.closed_at = None
                update_fields.append("closed_at")

        ticket.save(update_fields=update_fields)
        _log_activity(ticket, user, "status", old_status, new_status)
        if old_work_order_category != ticket.work_order_category:
            _log_activity(
                ticket, user, "work_order_category",
                old_work_order_category, ticket.work_order_category,
            )
        _mark_sla_responded(ticket, user)

        if new_status != old_status:
            _notify_ticket_status_changed(ticket, user, old_status, new_status)

        return Response({"detail": f"Estado cambiado a {new_status}."})


class TicketConvertToClientView(APIView):
    """
    POST /api/ik/tickets/<id>/convert-to-client/
    Convierte un ticket de origen INTERNO (alerta/evento del sistema)
    a origen CLIENTE para que entre en el flujo real de soporte/SLA.
    """
    throttle_classes = [TicketRateThrottle]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if not (user.is_staff or user.is_superuser):
            return Response(
                {"error": "Solo staff puede convertir tickets."},
                status=status.HTTP_403_FORBIDDEN,
            )

        accessible_ids = _get_accessible_point_ids(user)
        try:
            ticket = SupportTicket.objects.filter(
                Q(pk=pk) & (Q(points__id__in=accessible_ids) | Q(origin="OPERACIONES"))
            ).distinct().get()
        except SupportTicket.DoesNotExist:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if ticket.origin == "CLIENTE":
            return Response(
                {"detail": "El ticket ya es de origen CLIENTE."},
                status=status.HTTP_200_OK,
            )

        if ticket.origin != "INTERNO":
            return Response(
                {"error": f"Solo se pueden convertir tickets de origen INTERNO. Origen actual: {ticket.origin}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_origin = ticket.origin
        ticket.origin = "CLIENTE"
        ticket.save(update_fields=["origin"])
        _log_activity(ticket, user, "origin", old_origin, "CLIENTE")

        ticket = _apply_sla_to_ticket(ticket)
        ticket.save(update_fields=[
            "sla_config", "sla_deadline_response", "sla_deadline_resolution",
        ])

        return Response(
            SupportTicketDetailSerializer(ticket, context={"request": request}).data
        )


class TicketConfirmScheduledDateView(APIView):
    """
    POST /api/ik/tickets/<id>/confirm-scheduled-date/

    Confirma la fecha planificada (scheduled_date) de una OT (orden de trabajo).

    Solo puede confirmar un usuario autenticado con acceso al ticket (staff o
    involucrado en los puntos vinculados). Requiere que el ticket tenga una
    fecha planificada asignada. Al confirmar se envía una notificación por
    correo a quien confirma y a los involucrados del ticket.
    """
    throttle_classes = [TicketRateThrottle]
    permission_classes = [IsAuthenticated]

    def _get_ticket(self, pk, user):
        accessible_ids = _get_accessible_point_ids(user)
        try:
            ticket = SupportTicket.objects.select_related(
                "created_by", "assigned_to", "category",
            ).prefetch_related("points").get(pk=pk)
        except SupportTicket.DoesNotExist:
            return None

        if user.is_staff or user.is_superuser:
            if ticket.origin != "OPERACIONES" and not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        else:
            if not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        return ticket

    def post(self, request, pk):
        user = request.user
        ticket = self._get_ticket(pk, user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if not ticket.scheduled_date:
            return Response(
                {"error": "El ticket no tiene una fecha planificada asignada."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if ticket.scheduled_date_confirmed:
            return Response(
                SupportTicketDetailSerializer(ticket, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )

        old_value = ticket.scheduled_date_confirmed
        ticket.scheduled_date_confirmed = True
        ticket.scheduled_date_confirmed_by = user
        ticket.scheduled_date_confirmed_at = timezone.now()
        ticket.save(update_fields=[
            "scheduled_date_confirmed",
            "scheduled_date_confirmed_by",
            "scheduled_date_confirmed_at",
        ])
        _log_activity(ticket, user, "scheduled_date_confirmed", old_value, True)
        _notify_scheduled_date_confirmed(ticket, user)

        return Response(
            SupportTicketDetailSerializer(ticket, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class TicketCancelScheduledDateView(APIView):
    """
    POST /api/ik/tickets/<id>/cancel-scheduled-date/

    Cancela la fecha planificada (scheduled_date) de una OT (orden de trabajo).

    Solo puede cancelar un usuario autenticado con acceso al ticket (staff o
    involucrado en los puntos vinculados). Requiere que el ticket tenga una
    fecha planificada asignada. Si la fecha estaba confirmada, queda
    desconfirmada (la cancelación la deja en espera de re-agendar). Al cancelar
    se envía una notificación por correo a quien cancela y a los involucrados.
    El motivo es opcional.

    El endpoint es idempotente: si la fecha ya estaba cancelada, no se vuelve
    a enviar el correo ni se registra una nueva cancelación.
    """
    throttle_classes = [TicketRateThrottle]
    permission_classes = [IsAuthenticated]

    def _get_ticket(self, pk, user):
        accessible_ids = _get_accessible_point_ids(user)
        try:
            ticket = SupportTicket.objects.select_related(
                "created_by", "assigned_to", "category",
            ).prefetch_related("points").get(pk=pk)
        except SupportTicket.DoesNotExist:
            return None

        if user.is_staff or user.is_superuser:
            if ticket.origin != "OPERACIONES" and not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        else:
            if not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        return ticket

    def post(self, request, pk):
        user = request.user
        ticket = self._get_ticket(pk, user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if not ticket.scheduled_date:
            return Response(
                {"error": "El ticket no tiene una fecha planificada asignada."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if ticket.scheduled_date_cancelled:
            return Response(
                SupportTicketDetailSerializer(ticket, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )

        reason = request.data.get("reason", "").strip() or None

        old_value = ticket.scheduled_date_cancelled
        ticket.scheduled_date_cancelled = True
        ticket.scheduled_date_cancelled_by = user
        ticket.scheduled_date_cancelled_at = timezone.now()
        ticket.scheduled_date_cancelled_reason = reason

        update_fields = [
            "scheduled_date_cancelled",
            "scheduled_date_cancelled_by",
            "scheduled_date_cancelled_at",
            "scheduled_date_cancelled_reason",
        ]

        # Cancelar una fecha confirmada la deja en espera de re-agendar.
        if ticket.scheduled_date_confirmed:
            ticket.scheduled_date_confirmed = False
            ticket.scheduled_date_confirmed_by = None
            ticket.scheduled_date_confirmed_at = None
            update_fields.extend([
                "scheduled_date_confirmed",
                "scheduled_date_confirmed_by",
                "scheduled_date_confirmed_at",
            ])

        ticket.save(update_fields=update_fields)
        _log_activity(ticket, user, "scheduled_date_cancelled", old_value, True)
        _notify_scheduled_date_cancelled(ticket, user)

        return Response(
            SupportTicketDetailSerializer(ticket, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class TicketStatsView(APIView):
    """
    GET /api/ik/tickets/stats/
    Dashboard de soporte: conteos por estado, categoria, prioridad, origen y compliance.
    """
    throttle_classes = [TicketRateThrottle]
    permission_classes = [IsAuthenticated]

    def _count_by(self, qs, field):
        """Cuenta registros agrupados por un campo, usando distinct=True."""
        return {
            item[field]: item["count"]
            for item in qs.order_by().values(field).annotate(count=Count("id", distinct=True))
        }

    def get(self, request):
        user = request.user
        accessible_ids = _get_accessible_point_ids(user)
        # No usar .distinct() previo: el join con points duplica filas y
        # values().annotate() necesita Count(..., distinct=True) para contar bien.
        # El SLA de soporte considera solo tickets CLIENTE (no OPERACIONES/INTERNO).
        base_qs = SupportTicket.objects.filter(
            points__id__in=accessible_ids,
            is_active=True,
            origin="CLIENTE",
        )

        by_status = self._count_by(base_qs, "status")
        by_category = self._count_by(base_qs, "category")
        by_priority = self._count_by(base_qs, "priority")
        by_origin = self._count_by(base_qs, "origin")
        by_category_type = self._count_by(base_qs, "category__category_type")

        # Queryset distinct para conteos y filtros puros de ticket
        base_qs_distinct = base_qs.distinct()

        # SLA: vencidos (se excluyen tickets con SLA pausado en estados de espera)
        now = timezone.now()
        open_statuses = [
            "ABIERTO", "EN_ANALISIS", "ESPERA_CLIENTE", "ESPERA_PROVEEDOR", "EN_ORDEN_TRABAJO"
        ]

        overdue_resolution = base_qs_distinct.filter(
            sla_deadline_resolution__lt=now,
            sla_paused_at__isnull=True,
            status__in=open_statuses,
        ).count()
        overdue_response = base_qs_distinct.filter(
            sla_deadline_response__lt=now,
            sla_responded_at__isnull=True,
            sla_paused_at__isnull=True,
            status__in=open_statuses,
        ).count()

        # Compliance (categorias de tipo COMPLIANCE)
        compliance_qs = base_qs_distinct.filter(category__category_type="COMPLIANCE")
        compliance_overdue_resolution = compliance_qs.filter(
            sla_deadline_resolution__lt=now,
            sla_paused_at__isnull=True,
            status__in=open_statuses,
        ).count()
        compliance_overdue_response = compliance_qs.filter(
            sla_deadline_response__lt=now,
            sla_responded_at__isnull=True,
            sla_paused_at__isnull=True,
            status__in=open_statuses,
        ).count()

        return Response({
            "total": base_qs_distinct.count(),
            "by_status": by_status,
            "by_category": by_category,
            "by_category_type": by_category_type,
            "by_priority": by_priority,
            "by_origin": by_origin,
            "sla_overdue_response": overdue_response,
            "sla_overdue_resolution": overdue_resolution,
            "compliance": {
                "total": compliance_qs.count(),
                "by_status": self._count_by(compliance_qs, "status"),
                "sla_overdue_response": compliance_overdue_response,
                "sla_overdue_resolution": compliance_overdue_resolution,
            },
        })


class TicketRankingView(APIView):
    """
    GET /api/ik/tickets/ranking/
    Ranking de personas sobre tickets CLIENTE (SLA de soporte):
      - by_resolved: tickets que cada persona resolvió o cerró (activity log)
      - by_assigned: tickets actualmente asignados a cada persona
      - by_created:  tickets creados por cada persona
    Filtros: created_at__gte / created_at__lte (YYYY-MM-DD), project_id, client_id.
    """

    throttle_classes = [TicketRateThrottle]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        accessible_ids = _get_accessible_point_ids(user)

        # Base: tickets de soporte activos CLIENTE (los que operan SLA).
        base_qs = SupportTicket.objects.filter(
            points__id__in=accessible_ids,
            is_active=True,
            origin="CLIENTE",
        ).distinct()

        created_at_gte = request.query_params.get("created_at__gte")
        created_at_lte = request.query_params.get("created_at__lte")
        if created_at_gte:
            try:
                dt = timezone.make_aware(
                    datetime.combine(datetime.fromisoformat(created_at_gte), datetime.min.time())
                )
                base_qs = base_qs.filter(created__gte=dt)
            except (ValueError, TypeError):
                return Response(
                    {"error": "created_at__gte debe tener formato YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if created_at_lte:
            try:
                dt = timezone.make_aware(
                    datetime.combine(datetime.fromisoformat(created_at_lte), datetime.max.time())
                )
                base_qs = base_qs.filter(created__lte=dt)
            except (ValueError, TypeError):
                return Response(
                    {"error": "created_at__lte debe tener formato YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        project_id = request.query_params.get("project_id")
        if project_id:
            try:
                base_qs = base_qs.filter(points__project_id=int(project_id))
            except (ValueError, TypeError):
                return Response(
                    {"error": "project_id debe ser un entero válido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        client_id = request.query_params.get("client_id")
        if client_id:
            try:
                base_qs = base_qs.filter(points__project__client_id=int(client_id))
            except (ValueError, TypeError):
                return Response(
                    {"error": "client_id debe ser un entero válido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        def _rank_by_user(qs, field):
            """Conteo de tickets agrupado por usuario del campo FK indicado."""
            rows = (
                qs.filter(**{f"{field}__isnull": False})
                .order_by()
                .values(f"{field}__id", f"{field}__first_name", f"{field}__last_name")
                .annotate(total=Count("id", distinct=True))
                .order_by("-total", f"{field}__id")
            )
            return [
                {
                    "user_id": row[f"{field}__id"],
                    "name": " ".join(
                        filter(None, [row[f"{field}__first_name"], row[f"{field}__last_name"]])
                    ),
                    "total": row["total"],
                }
                for row in rows
            ]

        by_assigned = _rank_by_user(base_qs, "assigned_to")
        by_created = _rank_by_user(base_qs, "created_by")

        # SLA vencidos por persona asignada: mismos filtros que el dashboard.
        now = timezone.now()
        open_statuses = [
            "ABIERTO", "EN_ANALISIS", "ESPERA_CLIENTE", "ESPERA_PROVEEDOR", "EN_ORDEN_TRABAJO"
        ]
        by_sla_resolution_overdue = _rank_by_user(
            base_qs.filter(
                sla_deadline_resolution__lt=now,
                sla_resolved_at__isnull=True,
                sla_paused_at__isnull=True,
                status__in=open_statuses,
            ),
            "assigned_to",
        )
        by_sla_response_overdue = _rank_by_user(
            base_qs.filter(
                sla_deadline_response__lt=now,
                sla_responded_at__isnull=True,
                sla_paused_at__isnull=True,
                status__in=open_statuses,
            ),
            "assigned_to",
        )

        # Resueltos: se atribuye al usuario del activity log status -> RESUELTO;
        # los cerrados directo a CERRADO sin pasar por RESUELTO van a quien los cerró.
        base_ids = base_qs.values("id")
        resolved_logs = TicketActivityLog.objects.filter(
            ticket_id__in=base_ids,
            field_name="status",
            new_value="RESUELTO",
        )
        resolved_ids = resolved_logs.values("ticket_id")
        resolved_rows = (
            resolved_logs.order_by()
            .values("user__id", "user__first_name", "user__last_name")
            .annotate(total=Count("ticket_id", distinct=True))
            .order_by("-total", "user__id")
        )
        cerrado_rows = (
            TicketActivityLog.objects.filter(
                ticket_id__in=base_ids,
                field_name="status",
                new_value="CERRADO",
            )
            .exclude(ticket_id__in=resolved_ids)
            .order_by()
            .values("user__id", "user__first_name", "user__last_name")
            .annotate(total=Count("ticket_id", distinct=True))
        )

        merged = {}
        for rows in (resolved_rows, cerrado_rows):
            for row in rows:
                uid = row["user__id"]
                entry = merged.setdefault(
                    uid,
                    {
                        "user_id": uid,
                        "name": " ".join(
                            filter(None, [row["user__first_name"], row["user__last_name"]])
                        ),
                        "total": 0,
                    },
                )
                entry["total"] += row["total"]
        by_resolved = sorted(merged.values(), key=lambda x: (-x["total"], x["user_id"]))

        return Response({
            "by_resolved": by_resolved,
            "by_assigned": by_assigned,
            "by_created": by_created,
            "by_sla_resolution_overdue": by_sla_resolution_overdue,
            "by_sla_response_overdue": by_sla_response_overdue,
            "metadata": {
                "generated_at": timezone.now().isoformat(),
                "filters_applied": {
                    "created_at__gte": created_at_gte,
                    "created_at__lte": created_at_lte,
                    "project_id": project_id,
                    "client_id": client_id,
                },
            },
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
            ticket = SupportTicket.objects.get(pk=pk)
        except SupportTicket.DoesNotExist:
            return None

        if user.is_staff or user.is_superuser:
            if ticket.origin != "OPERACIONES" and not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        else:
            if not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        return ticket

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


class TicketTasksView(APIView):
    """
    GET  /api/ik/tickets/<id>/tasks/  → listar tareas del ticket
    POST /api/ik/tickets/<id>/tasks/  → crear tarea (solo staff)
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [TicketRateThrottle]

    def _get_ticket(self, pk, user):
        accessible_ids = _get_accessible_point_ids(user)
        try:
            ticket = SupportTicket.objects.get(pk=pk)
        except SupportTicket.DoesNotExist:
            return None

        if user.is_staff or user.is_superuser:
            if ticket.origin != "OPERACIONES" and not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        else:
            if not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        return ticket

    def get(self, request, pk):
        ticket = self._get_ticket(pk, request.user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        qs = ticket.tasks.select_related(
            "assigned_to", "created_by"
        ).prefetch_related("attachments")

        status_filter = request.query_params.get("status")
        assigned_to = request.query_params.get("assigned_to")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if assigned_to:
            qs = qs.filter(assigned_to_id=assigned_to)

        qs = qs.order_by("-created")
        serializer = SupportTicketTaskSerializer(qs, many=True, context={"request": request})
        return Response({"tasks": serializer.data})

    def post(self, request, pk):
        user = request.user
        if not (user.is_staff or user.is_superuser):
            return Response(
                {"error": "Solo staff puede crear tareas."},
                status=status.HTTP_403_FORBIDDEN,
            )

        ticket = self._get_ticket(pk, user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        data["ticket"] = ticket.id

        assigned_to = data.get("assigned_to")
        if assigned_to not in (None, ""):
            try:
                from api.core.models import User
                if not User.objects.filter(id=int(assigned_to), is_active=True).exists():
                    return Response(
                        {"error": "Usuario asignado no existe o está inactivo."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except (ValueError, TypeError):
                return Response(
                    {"error": "assigned_to debe ser un id de usuario válido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = SupportTicketTaskWriteSerializer(data=data)
        if serializer.is_valid():
            task = serializer.save(created_by=user)
            return Response(
                SupportTicketTaskSerializer(task, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TicketTaskDetailView(APIView):
    """
    GET    /api/ik/tasks/<id>/  → detalle de tarea
    PATCH  /api/ik/tasks/<id>/  → editar tarea (solo staff)
    DELETE /api/ik/tasks/<id>/  → eliminar tarea (staff o el creador)
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [TicketRateThrottle]

    def _get_task(self, pk, user):
        try:
            task = SupportTicketTask.objects.select_related(
                "ticket", "assigned_to", "created_by",
            ).prefetch_related("attachments").get(pk=pk)
        except SupportTicketTask.DoesNotExist:
            return None

        accessible_ids = _get_accessible_point_ids(user)
        if user.is_staff or user.is_superuser:
            if task.ticket.origin != "OPERACIONES" and not task.ticket.points.filter(id__in=accessible_ids).exists():
                return None
        else:
            if not task.ticket.points.filter(id__in=accessible_ids).exists():
                return None
        return task

    def get(self, request, pk):
        task = self._get_task(pk, request.user)
        if not task:
            return Response({"error": "Tarea no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SupportTicketTaskSerializer(task, context={"request": request})
        return Response(serializer.data)

    def patch(self, request, pk):
        user = request.user
        if not (user.is_staff or user.is_superuser):
            return Response(
                {"error": "Solo staff puede editar tareas."},
                status=status.HTTP_403_FORBIDDEN,
            )
        task = self._get_task(pk, user)
        if not task:
            return Response({"error": "Tarea no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        allowed_fields = ["title", "description", "status", "priority", "assigned_to", "due_date"]
        data = {k: v for k, v in request.data.items() if k in allowed_fields}

        serializer = SupportTicketTaskWriteSerializer(task, data=data, partial=True)
        if serializer.is_valid():
            task = serializer.save()
            return Response(
                SupportTicketTaskSerializer(task, context={"request": request}).data
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        user = request.user
        task = self._get_task(pk, user)
        if not task:
            return Response({"error": "Tarea no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        is_staff = user.is_staff or user.is_superuser
        is_creator = task.created_by_id == user.id
        if not (is_staff or is_creator):
            return Response(
                {"error": "Solo staff o el creador puede eliminar la tarea."},
                status=status.HTTP_403_FORBIDDEN,
            )
        task.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TicketCommentAttachmentsView(APIView):
    """
    POST /api/ik/tickets/<id>/comments/<cid>/attachments/  → adjuntar archivo a un comentario
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [TicketRateThrottle]

    def _get_ticket(self, pk, user):
        accessible_ids = _get_accessible_point_ids(user)
        try:
            ticket = SupportTicket.objects.get(pk=pk)
        except SupportTicket.DoesNotExist:
            return None

        if user.is_staff or user.is_superuser:
            if ticket.origin != "OPERACIONES" and not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        else:
            if not ticket.points.filter(id__in=accessible_ids).exists():
                return None
        return ticket

    def post(self, request, pk, cid):
        user = request.user
        ticket = self._get_ticket(pk, user)
        if not ticket:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        try:
            comment = TicketComment.objects.get(pk=cid, ticket=ticket)
        except TicketComment.DoesNotExist:
            return Response({"error": "Comentario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        # Clientes no ven ni adjuntan a notas internas
        if not (user.is_staff or user.is_superuser) and comment.is_internal:
            return Response({"error": "Comentario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "No se envió archivo."}, status=status.HTTP_400_BAD_REQUEST)

        error = _validate_upload(file_obj)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        import os
        attachment = TicketAttachment.objects.create(
            ticket=ticket,
            comment=comment,
            file=file_obj,
            original_name=os.path.basename(file_obj.name),
            uploaded_by=user,
        )
        serializer = TicketAttachmentSerializer(attachment, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class TicketTaskAttachmentsView(APIView):
    """
    POST /api/ik/tasks/<id>/attachments/  → adjuntar archivo a una tarea (solo staff)
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [TicketRateThrottle]

    def post(self, request, pk):
        user = request.user
        if not (user.is_staff or user.is_superuser):
            return Response(
                {"error": "Solo staff puede adjuntar archivos a tareas."},
                status=status.HTTP_403_FORBIDDEN,
            )

        accessible_ids = _get_accessible_point_ids(user)
        try:
            task = SupportTicketTask.objects.select_related("ticket").get(pk=pk)
        except SupportTicketTask.DoesNotExist:
            return Response({"error": "Tarea no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if task.ticket.origin != "OPERACIONES" and not task.ticket.points.filter(id__in=accessible_ids).exists():
            return Response({"error": "Tarea no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "No se envió archivo."}, status=status.HTTP_400_BAD_REQUEST)

        error = _validate_upload(file_obj)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        import os
        attachment = TicketAttachment.objects.create(
            ticket=task.ticket,
            task=task,
            file=file_obj,
            original_name=os.path.basename(file_obj.name),
            uploaded_by=user,
        )
        serializer = TicketAttachmentSerializer(attachment, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class FilesDriveView(APIView):
    """
    GET /api/ik/files/  → "drive": todos los archivos con su contexto.

    Cada archivo indica a qué ticket, comentario o tarea pertenece.
    Filtros: ticket_id, project_id, client_id, contexto (comentario|tarea),
    search (nombre de archivo).
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [TicketRateThrottle]

    def get(self, request):
        user = request.user
        accessible_ids = _get_accessible_point_ids(user)

        qs = TicketAttachment.objects.select_related(
            "uploaded_by", "comment", "task", "task__assigned_to",
        ).prefetch_related(
            "ticket__points", "ticket__points__project", "ticket__points__project__client"
        ).filter(ticket__points__id__in=accessible_ids).distinct()

        ticket_id = request.query_params.get("ticket_id")
        project_id = request.query_params.get("project_id")
        client_id = request.query_params.get("client_id")
        contexto = request.query_params.get("contexto")
        search = request.query_params.get("search")

        if ticket_id:
            qs = qs.filter(ticket_id=ticket_id)
        if project_id:
            try:
                qs = qs.filter(ticket__points__project_id=int(project_id))
            except (ValueError, TypeError):
                return Response(
                    {"error": "project_id debe ser un entero válido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if client_id:
            try:
                qs = qs.filter(ticket__points__project__client_id=int(client_id))
            except (ValueError, TypeError):
                return Response(
                    {"error": "client_id debe ser un entero válido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if contexto:
            if contexto.lower() == "comentario":
                qs = qs.filter(comment__isnull=False)
            elif contexto.lower() == "tarea":
                qs = qs.filter(task__isnull=False)
            else:
                return Response(
                    {"error": "contexto debe ser 'comentario' o 'tarea'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if search:
            qs = qs.filter(original_name__icontains=search)

        qs = qs.order_by("-created")

        paginator = TicketPagination()
        result_page = paginator.paginate_queryset(qs, request)
        serializer = FileDriveSerializer(result_page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class TicketMyDeskView(APIView):
    """
    GET /api/ik/tickets/my_desk/

    Tickets relevantes para el usuario autenticado:
      - Tickets donde esta asignado como responsable.
      - Tickets en categorias donde figura como operador.
      - Tickets que el usuario creo (aunque no este asignado a el).

    Filtros de scope (query params):
      - scope=assigned   → solo tickets asignados al usuario
      - scope=category   → solo tickets de categorias donde es operador
      - sin scope        → los tres anteriores (comportamiento por defecto)

    Staff ve tickets de origen CLIENTE y OPERACIONES;
    clientes normales solo ven tickets de origen CLIENTE.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [TicketRateThrottle]

    def get(self, request):
        user = request.user

        # Staff ve tickets cliente y operaciones; clientes solo tickets cliente
        allowed_origins = ["CLIENTE", "OPERACIONES"] if (user.is_staff or user.is_superuser) else ["CLIENTE"]

        scope = request.query_params.get("scope")
        if scope == "assigned":
            qs = SupportTicket.objects.filter(
                assigned_to=user,
                is_active=True,
                origin__in=allowed_origins,
            )
        elif scope == "category":
            qs = SupportTicket.objects.filter(
                category__operators=user,
                is_active=True,
                origin__in=allowed_origins,
            )
        else:
            qs = SupportTicket.objects.filter(
                Q(assigned_to=user)
                | Q(category__operators=user)
                | Q(created_by=user),
                is_active=True,
                origin__in=allowed_origins,
            )

        qs = qs.select_related(
            "created_by", "assigned_to", "category",
        ).prefetch_related(
            "points", "points__project", "points__project__client", "comments"
        ).distinct()

        # Filtros opcionales
        status_filter = request.query_params.get("status")
        priority_filter = request.query_params.get("priority")
        category_filter = request.query_params.get("category")
        search = request.query_params.get("search")
        scheduled_date = request.query_params.get("scheduled_date")

        if status_filter:
            qs = qs.filter(status=status_filter)
        if priority_filter:
            qs = qs.filter(priority=priority_filter)
        if category_filter:
            # Filtrar por categoria exacta o por cualquiera de sus subcategorias.
            qs = qs.filter(
                Q(category_id=category_filter) | Q(category__parent_id=category_filter)
            )
        if scheduled_date:
            qs = qs.filter(scheduled_date=scheduled_date)
        if search:
            qs = qs.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )

        # Filtro por rango de fecha de creación (misma lógica que el listado general).
        # Se aplica ANTES de la paginación; usa datetimes con zona horaria del
        # servidor para no cortar mal el rango (no mezcla __date con datetime).
        created_from = request.query_params.get("created_from")
        created_to = request.query_params.get("created_to")
        if created_from:
            try:
                created_from_dt = timezone.make_aware(
                    datetime.combine(datetime.fromisoformat(created_from), datetime.min.time())
                )
                qs = qs.filter(created__gte=created_from_dt)
            except (ValueError, TypeError):
                return Response(
                    {"error": "created_from debe tener formato YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        if created_to:
            try:
                created_to_dt = timezone.make_aware(
                    datetime.combine(datetime.fromisoformat(created_to), datetime.max.time())
                )
                qs = qs.filter(created__lte=created_to_dt)
            except (ValueError, TypeError):
                return Response(
                    {"error": "created_to debe tener formato YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        qs = qs.order_by("-created")

        paginator = TicketPagination()
        result_page = paginator.paginate_queryset(qs, request)
        serializer = SupportTicketListSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)


class IsStaffOrReadOnly(IsAuthenticated):
    """Permite lectura a usuarios autenticados; escritura solo a staff."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return request.user.is_staff or request.user.is_superuser


class SLAConfigListCreateView(APIView):
    """
    GET  /api/ik/sla-configs/ → listar (solo staff)
    POST /api/ik/sla-configs/ → crear (solo staff)
    """

    permission_classes = [IsAdminUser]
    throttle_classes = [TicketRateThrottle]

    def get(self, request):
        qs = SLAConfig.objects.filter(is_active=True).select_related(
            "client", "project", "category", "escalation_user"
        )
        client_id = request.query_params.get("client_id")
        project_id = request.query_params.get("project_id")
        category_id = request.query_params.get("category_id")
        priority = request.query_params.get("priority")

        if client_id:
            qs = qs.filter(client_id=client_id)
        if project_id:
            qs = qs.filter(project_id=project_id)
        if category_id:
            qs = qs.filter(category_id=category_id)
        if priority:
            qs = qs.filter(priority=priority.upper())

        serializer = SLAConfigSerializer(qs.order_by("-created"), many=True)
        return Response({"results": serializer.data})

    def post(self, request):
        serializer = SLAConfigWriteSerializer(data=request.data)
        if serializer.is_valid():
            sla = serializer.save()
            return Response(SLAConfigSerializer(sla).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SLAConfigDetailView(APIView):
    """
    GET    /api/ik/sla-configs/<id>/ → detalle (solo staff)
    PATCH  /api/ik/sla-configs/<id>/ → editar (solo staff)
    DELETE /api/ik/sla-configs/<id>/ → eliminar (solo staff)
    """

    permission_classes = [IsAdminUser]
    throttle_classes = [TicketRateThrottle]

    def _get_sla(self, pk):
        try:
            return SLAConfig.objects.get(pk=pk)
        except SLAConfig.DoesNotExist:
            return None

    def get(self, request, pk):
        sla = self._get_sla(pk)
        if not sla:
            return Response({"error": "SLA no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SLAConfigSerializer(sla)
        return Response(serializer.data)

    def patch(self, request, pk):
        sla = self._get_sla(pk)
        if not sla:
            return Response({"error": "SLA no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SLAConfigWriteSerializer(sla, data=request.data, partial=True)
        if serializer.is_valid():
            sla = serializer.save()
            return Response(SLAConfigSerializer(sla).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        sla = self._get_sla(pk)
        if not sla:
            return Response({"error": "SLA no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        sla.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TicketCategoryListCreateView(APIView):
    """
    GET  /api/ik/ticket-categories/ → listar (todos los usuarios autenticados)
    POST /api/ik/ticket-categories/ → crear (solo staff)
    """

    permission_classes = [IsStaffOrReadOnly]
    throttle_classes = [TicketRateThrottle]

    def get(self, request):
        qs = TicketCategory.objects.filter(is_active=True)

        category_type = request.query_params.get("category_type")
        if category_type:
            qs = qs.filter(category_type=category_type.upper())

        parent_id = request.query_params.get("parent_id")
        if parent_id:
            try:
                qs = qs.filter(parent_id=int(parent_id))
            except (ValueError, TypeError):
                return Response(
                    {"error": "parent_id debe ser un entero válido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif request.query_params.get("top_only", "").lower() in ("true", "1", "yes"):
            qs = qs.filter(parent__isnull=True)

        serializer = TicketCategorySerializer(qs.order_by("category_type", "name"), many=True)
        return Response({"categories": serializer.data})

    def post(self, request):
        serializer = TicketCategoryWriteSerializer(data=request.data)
        if serializer.is_valid():
            category = serializer.save()
            return Response(
                TicketCategorySerializer(category).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TicketCategoryDetailView(APIView):
    """
    GET    /api/ik/ticket-categories/<id>/ → detalle
    PATCH  /api/ik/ticket-categories/<id>/ → editar (solo staff)
    DELETE /api/ik/ticket-categories/<id>/ → desactivar (solo staff)
    """

    permission_classes = [IsStaffOrReadOnly]
    throttle_classes = [TicketRateThrottle]

    def _get_category(self, pk):
        try:
            return TicketCategory.objects.get(pk=pk)
        except TicketCategory.DoesNotExist:
            return None

    def get(self, request, pk):
        category = self._get_category(pk)
        if not category:
            return Response({"error": "Categoría no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        serializer = TicketCategorySerializer(category)
        return Response(serializer.data)

    def patch(self, request, pk):
        category = self._get_category(pk)
        if not category:
            return Response({"error": "Categoría no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        serializer = TicketCategoryWriteSerializer(category, data=request.data, partial=True)
        if serializer.is_valid():
            category = serializer.save()
            return Response(TicketCategorySerializer(category).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        category = self._get_category(pk)
        if not category:
            return Response({"error": "Categoría no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        # Desactivar en lugar de borrar para no romper tickets históricos
        category.is_active = False
        category.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)
class TicketDashboardView(APIView):
    """
    GET /api/ik/tickets/dashboard/

    Dashboard unificado de soporte: KPIs, gráficos y tablas críticas.
    Filtros:
      - created_at__gte / created_at__lte: rango de creación (YYYY-MM-DD)
      - assigned_to: id de usuario asignado
      - project_id: id de proyecto (por punto vinculado)
      - client_id: id de cliente (por punto vinculado)
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [TicketRateThrottle]

    def get(self, request):
        user = request.user
        accessible_ids = _get_accessible_point_ids(user)

        # Base: tickets de soporte activos. El SLA de soporte considera solo
        # tickets CLIENTE: OPERACIONES e INTERNO quedan fuera.
        base_qs = SupportTicket.objects.filter(
            points__id__in=accessible_ids,
            is_active=True,
            origin="CLIENTE",
        ).distinct()

        # Filtros de fecha
        created_at_gte = request.query_params.get("created_at__gte")
        created_at_lte = request.query_params.get("created_at__lte")
        if created_at_gte:
            try:
                dt = timezone.make_aware(
                    datetime.combine(datetime.fromisoformat(created_at_gte), datetime.min.time())
                )
                base_qs = base_qs.filter(created__gte=dt)
            except (ValueError, TypeError):
                return Response(
                    {"error": "created_at__gte debe tener formato YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if created_at_lte:
            try:
                dt = timezone.make_aware(
                    datetime.combine(datetime.fromisoformat(created_at_lte), datetime.max.time())
                )
                base_qs = base_qs.filter(created__lte=dt)
            except (ValueError, TypeError):
                return Response(
                    {"error": "created_at__lte debe tener formato YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Filtros de asignación/proyecto/cliente
        assigned_to = request.query_params.get("assigned_to")
        if assigned_to:
            try:
                base_qs = base_qs.filter(assigned_to_id=int(assigned_to))
            except (ValueError, TypeError):
                return Response(
                    {"error": "assigned_to debe ser un entero válido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        project_id = request.query_params.get("project_id")
        if project_id:
            try:
                base_qs = base_qs.filter(points__project_id=int(project_id))
            except (ValueError, TypeError):
                return Response(
                    {"error": "project_id debe ser un entero válido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        client_id = request.query_params.get("client_id")
        if client_id:
            try:
                base_qs = base_qs.filter(points__project__client_id=int(client_id))
            except (ValueError, TypeError):
                return Response(
                    {"error": "client_id debe ser un entero válido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # "Tickets reales" = origin CLIENTE (los que operan SLA/soporte)
        real_qs = base_qs

        now = timezone.now()
        tomorrow = now + timedelta(hours=24)

        open_statuses = [
            "ABIERTO", "EN_ANALISIS", "ESPERA_CLIENTE", "ESPERA_PROVEEDOR", "EN_ORDEN_TRABAJO"
        ]

        # Una orden de trabajo es un ticket en estado EN_ORDEN_TRABAJO o cuya
        # categoría (o categoría de OT) es de tipo WORK_ORDER. No basta con
        # category__category_type: al pasar a EN_ORDEN_TRABAJO la categoría
        # original se conserva y la WORK_ORDER va en work_order_category.
        work_order_q = (
            Q(status="EN_ORDEN_TRABAJO")
            | Q(category__category_type="WORK_ORDER")
            | Q(work_order_category__category_type="WORK_ORDER")
        )

        # =========================================================================
        # KPIs
        # =========================================================================
        kpis = {
            "tickets": real_qs.count(),
            "active_tickets": real_qs.filter(status="ABIERTO").count(),
            "sla_resolution_overdue": real_qs.filter(
                sla_deadline_resolution__lt=now,
                sla_resolved_at__isnull=True,
                sla_paused_at__isnull=True,
                status__in=open_statuses,
            ).count(),
            "sla_response_overdue": real_qs.filter(
                sla_deadline_response__lt=now,
                sla_responded_at__isnull=True,
                sla_paused_at__isnull=True,
                status__in=open_statuses,
            ).count(),
            "compliance_overdue": real_qs.filter(
                category__category_type="COMPLIANCE",
                status="ABIERTO",
                sla_deadline_resolution__lt=now,
                sla_resolved_at__isnull=True,
                sla_paused_at__isnull=True,
            ).count(),
            "work_orders_total": real_qs.filter(work_order_q).count(),
            "work_orders_with_visit": real_qs.filter(work_order_q).filter(
                Q(scheduled_date__isnull=False)
                | Q(visit_report__isnull=False)
                | Q(visit_report__gt="")
            ).count(),
        }

        # =========================================================================
        # Charts
        # =========================================================================
        def _count_by(qs, field):
            # order_by() limpia el Meta.ordering ('-created'): si no, con el
            # .distinct() heredado Django agrega `created` al SELECT/GROUP BY y
            # cada estado/prioridad termina contando 1.
            return {
                item[field]: item["count"]
                for item in qs.order_by().values(field).annotate(count=Count("id", distinct=True))
                if item[field] is not None
            }

        charts = {
            "by_status": _count_by(real_qs, "status"),
            "by_priority": _count_by(real_qs, "priority"),
            "by_category_type": _count_by(
                real_qs.filter(category__isnull=False), "category__category_type"
            ),
            "by_origin": _count_by(base_qs, "origin"),
            "compliance_by_status": _count_by(
                real_qs.filter(category__category_type="COMPLIANCE", status="ABIERTO"),
                "status",
            ),
            "work_orders_by_status": _count_by(
                real_qs.filter(work_order_q),
                "status",
            ),
        }

        # =========================================================================
        # Tablas
        # =========================================================================
        def _serialize_table(qs, limit=10):
            return TicketDashboardRowSerializer(
                qs.select_related("assigned_to", "category").order_by(
                    F("sla_deadline_resolution").asc(nulls_last=True)
                )[:limit],
                many=True,
            ).data

        sla_resolution_overdue_qs = real_qs.filter(
            sla_deadline_resolution__lt=now,
            sla_resolved_at__isnull=True,
            sla_paused_at__isnull=True,
            status__in=open_statuses,
        )
        sla_response_overdue_qs = real_qs.filter(
            sla_deadline_response__lt=now,
            sla_responded_at__isnull=True,
            sla_paused_at__isnull=True,
            status__in=open_statuses,
        )
        compliance_overdue_qs = real_qs.filter(
            category__category_type="COMPLIANCE",
            status="ABIERTO",
            sla_deadline_resolution__lt=now,
            sla_resolved_at__isnull=True,
            sla_paused_at__isnull=True,
        )
        upcoming_deadlines_qs = real_qs.filter(
            sla_deadline_resolution__gte=now,
            sla_deadline_resolution__lte=tomorrow,
            sla_resolved_at__isnull=True,
        )

        tables = {
            "sla_resolution_overdue": _serialize_table(sla_resolution_overdue_qs, 10),
            "sla_response_overdue": _serialize_table(sla_response_overdue_qs, 10),
            "compliance_overdue": _serialize_table(compliance_overdue_qs, 10),
            "upcoming_deadlines": _serialize_table(upcoming_deadlines_qs, 10),
        }

        return Response({
            "kpis": kpis,
            "charts": charts,
            "tables": tables,
            "metadata": {
                "generated_at": now.isoformat(),
                "filters_applied": {
                    "created_at__gte": created_at_gte,
                    "created_at__lte": created_at_lte,
                    "assigned_to": assigned_to,
                    "project_id": project_id,
                    "client_id": client_id,
                },
            },
        })
