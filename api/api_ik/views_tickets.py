"""
API ik — Subsistema de Tickets de Soporte + SLA.

Endpoints bajo /api/ik/tickets/
Nada toca el legacy (NotificationsCatchment).
"""

from datetime import datetime, timedelta

from django.db.models import Q, Count, F
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from .throttles import TicketRateThrottle
from rest_framework import status
from rest_framework.pagination import PageNumberPagination

from api.core.models import (
    SupportTicket,
    TicketCategory,
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
    TicketCategorySerializer,
    TicketCategoryWriteSerializer,
    SLAConfigSerializer,
    SLAConfigWriteSerializer,
    TicketDashboardRowSerializer,
)
from api.core.signals.tickets import _notify_category_operators


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
        now = ticket.created or timezone.now()
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

        # Validar puntos solo si no es ticket de operaciones
        point_ids = data.get("points", [])
        if origin != "OPERACIONES":
            if not isinstance(point_ids, list):
                return Response({"error": "points debe ser una lista de IDs."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                point_ids_int = [int(pid) for pid in point_ids]
            except (ValueError, TypeError):
                return Response({"error": "Cada point_id debe ser un entero válido."}, status=status.HTTP_400_BAD_REQUEST)

            if not point_ids_int:
                return Response({"error": "Debe enviar al menos un punto."}, status=status.HTTP_400_BAD_REQUEST)

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
            ticket.save(update_fields=[
                "sla_config", "sla_deadline_response", "sla_deadline_resolution"
            ])
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
            for field, old_val in old_values.items():
                new_val = getattr(updated_ticket, field, None)
                if str(old_val) != str(new_val):
                    _log_activity(updated_ticket, user, field, old_val, new_val)

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
                updated_ticket.save(update_fields=["resolved_at", "sla_resolved_at"])
                _log_activity(updated_ticket, user, "resolved_at", None, updated_ticket.resolved_at)

            # Si cambió a CERRADO, registrar fecha
            if updated_ticket.status == "CERRADO" and not updated_ticket.closed_at:
                updated_ticket.closed_at = timezone.now()
                if not updated_ticket.resolved_at:
                    updated_ticket.resolved_at = timezone.now()
                if not updated_ticket.sla_resolved_at:
                    updated_ticket.sla_resolved_at = timezone.now()
                updated_ticket.save(update_fields=["closed_at", "resolved_at", "sla_resolved_at"])
                _log_activity(updated_ticket, user, "closed_at", None, updated_ticket.closed_at)

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
            is_internal = comment.is_internal

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

                old_status = ticket.status
                ticket.status = status_change
                update_fields = ["status"]

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
            ticket = SupportTicket.objects.get(
                Q(pk=pk) & (Q(points__id__in=accessible_ids) | Q(origin="OPERACIONES"))
            )
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
            ticket = SupportTicket.objects.get(
                Q(pk=pk) & (Q(points__id__in=accessible_ids) | Q(origin="OPERACIONES"))
            )
        except SupportTicket.DoesNotExist:
            return Response({"error": "Ticket no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("status")
        if new_status not in [c[0] for c in SupportTicket.STATUS_CHOICES]:
            return Response({"error": "Estado inválido."}, status=status.HTTP_400_BAD_REQUEST)

        old_status = ticket.status
        ticket.status = new_status

        update_fields = ["status"]
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

        return Response({"detail": f"Estado cambiado a {new_status}."})


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
            for item in qs.values(field).annotate(count=Count("id", distinct=True))
        }

    def get(self, request):
        user = request.user
        accessible_ids = _get_accessible_point_ids(user)
        # No usar .distinct() previo: el join con points duplica filas y
        # values().annotate() necesita Count(..., distinct=True) para contar bien.
        if user.is_staff or user.is_superuser:
            base_qs = SupportTicket.objects.filter(
                Q(points__id__in=accessible_ids) | Q(origin="OPERACIONES"),
                is_active=True,
            )
        else:
            base_qs = SupportTicket.objects.filter(
                points__id__in=accessible_ids,
                is_active=True,
            )

        by_status = self._count_by(base_qs, "status")
        by_category = self._count_by(base_qs, "category")
        by_priority = self._count_by(base_qs, "priority")
        by_origin = self._count_by(base_qs, "origin")
        by_category_type = self._count_by(base_qs, "category__category_type")

        # Queryset distinct para conteos y filtros puros de ticket
        base_qs_distinct = base_qs.distinct()

        # SLA: vencidos
        now = timezone.now()
        open_statuses = [
            "ABIERTO", "EN_ANALISIS", "ESPERA_CLIENTE", "ESPERA_PROVEEDOR", "EN_ORDEN_TRABAJO"
        ]

        overdue_resolution = base_qs_distinct.filter(
            sla_deadline_resolution__lt=now,
            status__in=open_statuses,
        ).count()
        overdue_response = base_qs_distinct.filter(
            sla_deadline_response__lt=now,
            sla_responded_at__isnull=True,
            status__in=open_statuses,
        ).count()

        # Compliance (categorias de tipo COMPLIANCE)
        compliance_qs = base_qs_distinct.filter(category__category_type="COMPLIANCE")
        compliance_overdue_resolution = compliance_qs.filter(
            sla_deadline_resolution__lt=now,
            status__in=open_statuses,
        ).count()
        compliance_overdue_response = compliance_qs.filter(
            sla_deadline_response__lt=now,
            sla_responded_at__isnull=True,
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


class TicketMyDeskView(APIView):
    """
    GET /api/ik/tickets/my_desk/

    Tickets relevantes para el usuario autenticado:
      - Tickets donde esta asignado como responsable.
      - Tickets en categorias donde figura como operador.

    Filtros de scope (query params):
      - scope=assigned   → solo tickets asignados al usuario
      - scope=category   → solo tickets de categorias donde es operador
      - sin scope        → ambos (comportamiento por defecto)

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
                Q(assigned_to=user) | Q(category__operators=user),
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

        # Base: tickets activos accesibles. Staff también ve OPERACIONES.
        if user.is_staff or user.is_superuser:
            base_qs = SupportTicket.objects.filter(
                Q(points__id__in=accessible_ids) | Q(origin="OPERACIONES"),
                is_active=True,
            ).distinct()
        else:
            base_qs = SupportTicket.objects.filter(
                points__id__in=accessible_ids,
                is_active=True,
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
        real_qs = base_qs.filter(origin="CLIENTE")

        now = timezone.now()
        tomorrow = now + timedelta(hours=24)

        # =========================================================================
        # KPIs
        # =========================================================================
        kpis = {
            "tickets": real_qs.count(),
            "active_tickets": real_qs.filter(status="ABIERTO").count(),
            "sla_resolution_overdue": real_qs.filter(
                sla_deadline_resolution__lt=now,
                sla_resolved_at__isnull=True,
            ).count(),
            "sla_response_overdue": real_qs.filter(
                sla_deadline_response__lt=now,
                sla_responded_at__isnull=True,
            ).count(),
            "compliance_overdue": real_qs.filter(
                category__category_type="COMPLIANCE",
                status="ABIERTO",
                sla_deadline_resolution__lt=now,
                sla_resolved_at__isnull=True,
            ).count(),
            "work_orders_total": real_qs.filter(
                category__category_type="WORK_ORDER"
            ).count(),
            "work_orders_with_visit": real_qs.filter(
                category__category_type="WORK_ORDER"
            ).filter(
                Q(scheduled_date__isnull=False)
                | Q(visit_report__isnull=False)
            ).exclude(visit_report="").count(),
        }

        # =========================================================================
        # Charts
        # =========================================================================
        def _count_by(qs, field):
            return {
                item[field]: item["count"]
                for item in qs.values(field).annotate(count=Count("id", distinct=True))
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
                real_qs.filter(category__category_type="WORK_ORDER"),
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
        )
        sla_response_overdue_qs = real_qs.filter(
            sla_deadline_response__lt=now,
            sla_responded_at__isnull=True,
        )
        compliance_overdue_qs = real_qs.filter(
            category__category_type="COMPLIANCE",
            status="ABIERTO",
            sla_deadline_resolution__lt=now,
            sla_resolved_at__isnull=True,
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
