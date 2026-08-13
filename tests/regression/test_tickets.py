"""
Tests de regresión para el subsistema de Tickets de Soporte + SLA.
"""

from io import StringIO

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.core.models import (
    Client, ProjectCatchments, CatchmentPoint, SLAConfig, TicketCategory,
    SupportTicket, SupportTicketTask, TicketComment, TicketCommentLike, TicketAttachment, TicketActivityLog,
    TicketNotification,
    AlertRule, AlertTrigger, SystemEvent,
)

User = get_user_model()

TEST_MIDDLEWARE = [
    m for m in [
        "django.middleware.security.SecurityMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware",
        "django.middleware.gzip.GZipMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "corsheaders.middleware.CorsMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]
]


def _create_ticket_with_point(point, **kwargs):
    """Helper para crear un ticket vinculado a un punto."""
    ticket = SupportTicket.objects.create(**kwargs)
    ticket.points.add(point)
    return ticket


class TicketModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="tech@smarthydro.cl", password="pass", username="tech"
        )
        self.client_obj = Client.objects.create(name="Cliente Test")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Test", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Test", project=self.project, owner_user=self.user
        )
        self.cat_conectividad = TicketCategory.objects.get(
            category_type="HARDWARE", name="Conectividad"
        )

    def test_create_support_ticket(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="No hay datos",
            description="El punto lleva 2 horas sin datos",
            created_by=self.user,
            status="ABIERTO",
            priority="ALTA",
            category=self.cat_conectividad,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        self.assertEqual(ticket.status, "ABIERTO")
        self.assertEqual(ticket.origin, "CLIENTE")
        self.assertEqual(ticket.points.first(), self.point)

    def test_sla_config_matching(self):
        sla = SLAConfig.objects.create(
            client=self.client_obj,
            category=self.cat_conectividad,
            priority="ALTA",
            response_time_hours=2,
            resolution_time_hours=8,
        )
        ticket = _create_ticket_with_point(
            self.point,
            title="Falla",
            description="...",
            priority="ALTA",
            category=self.cat_conectividad,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        from api.api_ik.views_tickets import _find_sla_config
        matched = _find_sla_config(ticket)
        self.assertIsNotNone(matched)
        self.assertEqual(matched.response_time_hours, 2)

    def test_comment_internal_hidden(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Falla",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        TicketComment.objects.create(
            ticket=ticket, author=self.user, content="Nota interna", is_internal=True
        )
        TicketComment.objects.create(
            ticket=ticket, author=self.user, content="Visible", is_internal=False
        )
        self.assertEqual(ticket.comments.filter(is_internal=True).count(), 1)
        self.assertEqual(ticket.comments.filter(is_internal=False).count(), 1)

    def test_activity_log_created(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Falla",
            description="...",
            origin="INTERNO",
            source="SISTEMA",
        )
        TicketActivityLog.objects.create(
            ticket=ticket, user=self.user, field_name="status",
            old_value="ABIERTO", new_value="EN_ANALISIS",
        )
        self.assertEqual(ticket.activity_logs.count(), 1)


class TicketAutoCreationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="admin@smarthydro.cl", password="pass", username="admin"
        )
        self.client_obj = Client.objects.create(name="Cliente Auto")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Auto", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Auto", project=self.project, owner_user=self.user
        )
        self.cat_conectividad = TicketCategory.objects.get(
            category_type="HARDWARE", name="Conectividad"
        )

    def test_alert_trigger_creates_ticket(self):
        """Reproduce el flujo real: trigger creado con notification_sent=False,
        luego el dispatcher lo marca como enviado."""
        rule = AlertRule.objects.create(
            name="Desconexión P1",
            point_catchment=self.point,
            target_type="DISCONNECTION",
            severity="ALERT",
        )
        trigger = AlertTrigger.objects.create(
            alert_rule=rule,
            triggered_at=timezone.now(),
            point_catchment=self.point,
            notification_sent=False,
        )
        self.assertIsNone(
            SupportTicket.objects.filter(alert_trigger=trigger).first()
        )

        trigger.notification_sent = True
        trigger.notification_sent_at = timezone.now()
        trigger.save(update_fields=["notification_sent", "notification_sent_at"])

        ticket = SupportTicket.objects.filter(alert_trigger=trigger).first()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.category, self.cat_conectividad)
        self.assertEqual(ticket.origin, "INTERNO")
        self.assertEqual(ticket.source, "ALERTA_AUTO")

    def test_alert_trigger_does_not_duplicate_ticket(self):
        """Marcar notification_sent=True varias veces no debe duplicar el ticket."""
        rule = AlertRule.objects.create(
            name="Desconexión P1 dup",
            point_catchment=self.point,
            target_type="DISCONNECTION",
            severity="ALERT",
        )
        trigger = AlertTrigger.objects.create(
            alert_rule=rule,
            triggered_at=timezone.now(),
            point_catchment=self.point,
            notification_sent=False,
        )
        trigger.notification_sent = True
        trigger.notification_sent_at = timezone.now()
        trigger.save(update_fields=["notification_sent", "notification_sent_at"])
        trigger.save(update_fields=["notification_sent", "notification_sent_at"])

        self.assertEqual(SupportTicket.objects.filter(alert_trigger=trigger).count(), 1)

    def test_system_event_critical_creates_ticket(self):
        event = SystemEvent.objects.create(
            event_type="DISCONNECTION",
            point_catchment=self.point,
            title="Desconexión crítica",
            message="Sin datos por 48h",
            severity="CRITICAL",
        )
        ticket = SupportTicket.objects.filter(system_event=event).first()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.priority, "CRITICA")
        self.assertEqual(ticket.origin, "INTERNO")


@override_settings(
    MIDDLEWARE=TEST_MIDDLEWARE,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class TicketAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="api@smarthydro.cl", password="pass", username="apiuser", is_staff=True
        )
        self.client_obj = Client.objects.create(name="Cliente API")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto API", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto API", project=self.project, owner_user=self.user
        )
        self.cat_telemetria = TicketCategory.objects.get(
            category_type="HARDWARE", name="Telemetría"
        )
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_create_ticket_via_api(self):
        response = self.client.post(
            "/api/ik/tickets/",
            {
                "points": [self.point.id],
                "title": "Falla API",
                "description": "Desde test",
                "category": self.cat_telemetria.id,
                "priority": "MEDIA",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Falla API")
        self.assertEqual(data["status"], "ABIERTO")

    def test_create_client_ticket_without_points(self):
        """Un ticket de origen CLIENTE/App Cliente puede crearse sin puntos (ticket general)."""
        response = self.client.post(
            "/api/ik/tickets/",
            {
                "title": "Ticket general",
                "description": "Problema general, no ligado a un punto",
                "origin": "CLIENTE",
                "source": "APP_CLIENTE",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["points"], [])

    def test_create_client_ticket_with_point_without_client(self):
        """Un ticket CLIENTE también admite puntos sin cliente asignado (sigue siendo válido)."""
        no_client_project = ProjectCatchments.objects.create(name="Proyecto sin cliente")
        no_client_point = CatchmentPoint.objects.create(
            title="Punto sin cliente", project=no_client_project, owner_user=self.user
        )
        response = self.client.post(
            "/api/ik/tickets/",
            {
                "points": [no_client_point.id],
                "title": "Ticket cliente con punto",
                "description": "Válido aunque el punto no tenga cliente",
                "origin": "CLIENTE",
                "source": "APP_CLIENTE",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual([p["id"] for p in response.json()["points"]], [no_client_point.id])

    def test_list_tickets_via_api(self):
        _create_ticket_with_point(
            self.point,
            title="Ticket 1",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.get("/api/ik/tickets/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)

    def test_list_tickets_filter_by_project_id(self):
        """Filtrar tickets por project_id debe retornar solo los del proyecto."""
        other_project = ProjectCatchments.objects.create(
            name="Otro Proyecto", client=self.client_obj
        )
        other_point = CatchmentPoint.objects.create(
            title="Otro Punto", project=other_project, owner_user=self.user
        )
        _create_ticket_with_point(
            self.point,
            title="Ticket Proyecto API",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        _create_ticket_with_point(
            other_point,
            title="Ticket Otro Proyecto",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )

        response = self.client.get(f"/api/ik/tickets/?project_id={self.project.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["title"], "Ticket Proyecto API")

    def test_list_tickets_filter_by_invalid_project_id(self):
        """project_id no numérico debe retornar 400."""
        response = self.client.get("/api/ik/tickets/?project_id=not-an-id")
        self.assertEqual(response.status_code, 400)
        self.assertIn("project_id", response.json().get("error", "").lower())

    def test_list_tickets_filter_by_parent_category_includes_subcategories(self):
        """Filtrar por categoria padre debe incluir tickets de subcategorias."""
        sub_cat = TicketCategory.objects.create(
            category_type="HARDWARE",
            name="Sub Telemetria",
            parent=self.cat_telemetria,
        )
        _create_ticket_with_point(
            self.point,
            title="Ticket subcategoria",
            description="...",
            category=sub_cat,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.get(f"/api/ik/tickets/?category={self.cat_telemetria.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["title"], "Ticket subcategoria")

    def test_list_tickets_filter_by_id_icontains(self):
        """Filtrar por ?id= busca coincidencia parcial sobre el id del ticket.

        Si el ticket es 443 y se busca 4, debe devolver todos los que tengan
        un 4 en su id (443, 45, 104, ...).
        """
        t1 = _create_ticket_with_point(
            self.point,
            title="Ticket filtro id 1",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        t2 = _create_ticket_with_point(
            self.point,
            title="Ticket filtro id 2",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        token = str(t1.id)

        response = self.client.get(f"/api/ik/tickets/?id={token}")
        self.assertEqual(response.status_code, 200)
        matched = [r["id"] for r in response.json()["results"]]

        expected = {
            rid for rid in (t1.id, t2.id) if token in str(rid)
        }
        self.assertEqual(set(matched), expected)

    def test_change_status_via_api(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket status",
            description="...",
            origin="INTERNO",
            source="SISTEMA",
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "RESUELTO"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "RESUELTO")
        self.assertIsNotNone(ticket.resolved_at)

    def test_add_comment_via_api(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket comment",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "Revisando el caso", "status_change": "EN_ANALISIS"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "EN_ANALISIS")

    def test_delete_comment_via_api(self):
        """Staff puede eliminar un comentario del ticket."""
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket borrar comentario",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        comment = TicketComment.objects.create(
            ticket=ticket, author=self.user, content="Comentario a eliminar"
        )
        response = self.client.delete(
            f"/api/ik/tickets/{ticket.id}/comments/{comment.id}/"
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(TicketComment.objects.filter(pk=comment.id).exists())
        self.assertTrue(
            TicketActivityLog.objects.filter(
                ticket=ticket, field_name="comment_deleted"
            ).exists()
        )

    def test_delete_comment_forbidden_for_non_author_client(self):
        """Cliente no autor no puede eliminar un comentario ajeno."""
        author = User.objects.create_user(
            email="author@smarthydro.cl", password="pass", username="authoruser"
        )
        other = User.objects.create_user(
            email="other@smarthydro.cl", password="pass", username="otherclient"
        )
        self.point.users_viewers.add(other)
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket permisos comentario",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        comment = TicketComment.objects.create(
            ticket=ticket, author=author, content="Comentario ajeno"
        )

        client = APIClient()
        token = Token.objects.create(user=other)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = client.delete(
            f"/api/ik/tickets/{ticket.id}/comments/{comment.id}/"
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(TicketComment.objects.filter(pk=comment.id).exists())

    def test_delete_comment_own_by_author(self):
        """El autor (cliente) puede eliminar su propio comentario."""
        author = User.objects.create_user(
            email="ownerauthor@smarthydro.cl", password="pass", username="ownerauthor"
        )
        self.point.users_viewers.add(author)
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket autor borra",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        comment = TicketComment.objects.create(
            ticket=ticket, author=author, content="Mi comentario"
        )

        client = APIClient()
        token = Token.objects.create(user=author)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = client.delete(
            f"/api/ik/tickets/{ticket.id}/comments/{comment.id}/"
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(TicketComment.objects.filter(pk=comment.id).exists())

    def test_delete_comment_not_found(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket comentario inexistente",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.delete(
            f"/api/ik/tickets/{ticket.id}/comments/999999/"
        )
        self.assertEqual(response.status_code, 404)

    def test_comment_mention_notifies_involved_user(self):
        from django.core import mail
        mentionee = User.objects.create_user(
            email="mentionee@smarthydro.cl", password="pass", username="mentionee"
        )
        self.point.users_viewers.add(mentionee)
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket mención",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        mail.outbox = []
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "Hola @mentionee, revisa esto"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            TicketNotification.objects.filter(user=mentionee, ticket=ticket).exists()
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(mentionee.email, mail.outbox[0].to)

    def test_comment_mention_respects_notify_email_false(self):
        from django.core import mail
        quiet = User.objects.create_user(
            email="quiet@smarthydro.cl", password="pass", username="quiet",
            notify_email=False,
        )
        self.point.users_viewers.add(quiet)
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket mención silenciosa",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        mail.outbox = []
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "Hola @quiet"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            TicketNotification.objects.filter(user=quiet, ticket=ticket).exists()
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_comment_mention_ignores_non_involved_user(self):
        from django.core import mail
        stranger = User.objects.create_user(
            email="stranger@smarthydro.cl", password="pass", username="stranger"
        )
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket mención ajena",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        mail.outbox = []
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "Hola @stranger"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(
            TicketNotification.objects.filter(user=stranger).exists()
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_comment_author_not_notified_by_own_mention(self):
        from django.core import mail
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket auto-mención",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        mail.outbox = []
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "Hola @apiuser"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(
            TicketNotification.objects.filter(user=self.user).exists()
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_mentionable_users_endpoint(self):
        colleague = User.objects.create_user(
            email="colleague@smarthydro.cl", password="pass", username="colleague"
        )
        self.point.users_viewers.add(colleague)
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket etiquetables",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.get(f"/api/ik/tickets/{ticket.id}/mentionable_users/")
        self.assertEqual(response.status_code, 200)
        usernames = [u["username"] for u in response.json()["users"]]
        self.assertIn("colleague", usernames)
        self.assertIn("apiuser", usernames)

    def test_comment_reply_creates_thread(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket hilos",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        parent = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "Comentario raíz"},
            format="json",
        ).json()
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "Respuesta", "parent_id": parent["id"]},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["parent_id"], parent["id"])
        reply = TicketComment.objects.get(id=response.json()["id"])
        self.assertEqual(reply.parent_id, parent["id"])

    def test_comment_reply_rejects_parent_from_other_ticket(self):
        ticket1 = _create_ticket_with_point(
            self.point,
            title="T1", description="...", origin="CLIENTE", source="APP_CLIENTE",
        )
        ticket2 = _create_ticket_with_point(
            self.point,
            title="T2", description="...", origin="CLIENTE", source="APP_CLIENTE",
        )
        parent = self.client.post(
            f"/api/ik/tickets/{ticket1.id}/comments/",
            {"content": "Raíz"},
            format="json",
        ).json()
        response = self.client.post(
            f"/api/ik/tickets/{ticket2.id}/comments/",
            {"content": "Respuesta inválida", "parent_id": parent["id"]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_comment_list_includes_parent_and_reply_count(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket conteo",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        parent = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "Raíz"},
            format="json",
        ).json()
        self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "Respuesta", "parent_id": parent["id"]},
            format="json",
        )
        response = self.client.get(f"/api/ik/tickets/{ticket.id}/comments/")
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        root = next(c for c in results if c["id"] == parent["id"])
        self.assertEqual(root["reply_count"], 1)
        self.assertTrue(any(c["parent_id"] == parent["id"] for c in results))

    def test_comment_ticket_reference_notifies_involved(self):
        from django.core import mail
        colleague = User.objects.create_user(
            email="refcolleague@smarthydro.cl", password="pass", username="refcolleague"
        )
        self.point.users_viewers.add(colleague)
        source = _create_ticket_with_point(
            self.point,
            title="Fuente", description="...", origin="CLIENTE", source="APP_CLIENTE",
        )
        target = _create_ticket_with_point(
            self.point,
            title="Target", description="...", origin="CLIENTE", source="APP_CLIENTE",
        )
        mail.outbox = []
        response = self.client.post(
            f"/api/ik/tickets/{source.id}/comments/",
            {"content": f"Relacionado con #{target.id}"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            TicketNotification.objects.filter(
                user=colleague,
                ticket=target,
                notification_type="REFERENCE",
            ).exists()
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(colleague.email, mail.outbox[0].to)

    def test_detail_with_multiple_accessible_points(self):
        """Ticket con varios puntos accesibles no debe lanzar MultipleObjectsReturned."""
        other_point = CatchmentPoint.objects.create(
            title="Otro Punto API", project=self.project, owner_user=self.user
        )
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket multipunto",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        ticket.points.add(other_point)

        response = self.client.get(f"/api/ik/tickets/{ticket.id}/")
        self.assertEqual(response.status_code, 200)

        response = self.client.get(f"/api/ik/tickets/{ticket.id}/comments/")
        self.assertEqual(response.status_code, 200)

        response = self.client.get(f"/api/ik/tickets/{ticket.id}/attachments/")
        self.assertEqual(response.status_code, 200)

    def test_ticket_stats_via_api(self):
        _create_ticket_with_point(
            self.point,
            title="Ticket stats",
            description="...",
            status="ABIERTO",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.get("/api/ik/tickets/stats/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertIn("by_status", data)

    def test_create_ticket_invalid_point_id(self):
        """points con ID no numérico debe retornar 400, no 500."""
        response = self.client.post(
            "/api/ik/tickets/",
            {
                "points": ["not-an-id"],
                "title": "Falla",
                "description": "...",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("point_id", response.json().get("error", "").lower())

    def test_assign_ticket_invalid_user(self):
        """Asignar a usuario inexistente debe retornar 400, no 500."""
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket assign",
            description="...",
            origin="INTERNO",
            source="SISTEMA",
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/assign/",
            {"assigned_to": 99999},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("usuario", response.json().get("error", "").lower())

    def test_assign_ticket_with_multiple_points_does_not_500(self):
        """Asignar un ticket con varios puntos no debe lanzar MultipleObjectsReturned."""
        other_point = CatchmentPoint.objects.create(
            title="Otro Punto API", project=self.project, owner_user=self.user
        )
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket multipunto",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        ticket.points.add(other_point)

        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/assign/",
            {"assigned_to": self.user.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.assigned_to_id, self.user.id)

    def test_upload_attachment_invalid_extension(self):
        """Subir archivo con extensión inválida debe retornar 400."""
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket attach",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad_file = SimpleUploadedFile("virus.exe", b"malicious content", content_type="application/x-msdownload")
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/attachments/",
            {"file": bad_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("tipo", response.json().get("error", "").lower())

    def test_upload_attachment_success(self):
        """Subir archivo permitido debe retornar 201 y el adjunto."""
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket attach ok",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        from django.core.files.uploadedfile import SimpleUploadedFile
        good_file = SimpleUploadedFile("reporte.pdf", b"contenido valido", content_type="application/pdf")
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/attachments/",
            {"file": good_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["original_name"], "reporte.pdf")
        self.assertTrue(data["file_url"].endswith(".pdf"))

    def test_upload_attachment_exceeds_max_size(self):
        """Subir archivo mayor a 10 MB debe retornar 400."""
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket attach big",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        from django.core.files.uploadedfile import SimpleUploadedFile
        big_file = SimpleUploadedFile("grande.pdf", b"x" * (10 * 1024 * 1024 + 1), content_type="application/pdf")
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/attachments/",
            {"file": big_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("tamaño", response.json().get("error", "").lower())

    # =========================================================================
    # Tareas por ticket + "drive" de archivos
    # =========================================================================

    def test_create_task_via_api_sets_created_stage(self):
        """Al crear tarea, created_stage = estado del ticket en ese momento."""
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket tarea",
            description="...",
            status="EN_ORDEN_TRABAJO",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/tasks/",
            {"title": "Revisar sensor", "priority": "ALTA"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Revisar sensor")
        self.assertEqual(data["created_stage"], "EN_ORDEN_TRABAJO")
        self.assertEqual(data["status"], "PENDIENTE")
        self.assertEqual(data["ticket"], ticket.id)

    def test_create_task_requires_staff(self):
        """Un cliente (no staff) no puede crear tareas."""
        client_user = User.objects.create_user(
            email="client@task.cl", password="pass", username="clienttask"
        )
        self.point.owner_user = client_user
        self.point.save()
        token = Token.objects.create(user=client_user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket cliente",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = client.post(
            f"/api/ik/tickets/{ticket.id}/tasks/",
            {"title": "Tarea no permitida"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_list_tasks_via_api(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket con tareas",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        SupportTicketTask.objects.create(
            ticket=ticket, title="Tarea 1", created_stage="ABIERTO", created_by=self.user
        )
        SupportTicketTask.objects.create(
            ticket=ticket, title="Tarea 2", created_stage="ABIERTO", created_by=self.user
        )
        response = self.client.get(f"/api/ik/tickets/{ticket.id}/tasks/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["tasks"]), 2)

    def test_task_detail_patch(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket patch tarea",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        task = SupportTicketTask.objects.create(
            ticket=ticket, title="Tarea", created_stage="ABIERTO", created_by=self.user
        )
        response = self.client.patch(
            f"/api/ik/tasks/{task.id}/",
            {"status": "EN_PROGRESO"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "EN_PROGRESO")

    def test_task_delete(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket delete tarea",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        task = SupportTicketTask.objects.create(
            ticket=ticket, title="Tarea borrar", created_stage="ABIERTO", created_by=self.user
        )
        response = self.client.delete(f"/api/ik/tasks/{task.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(SupportTicketTask.objects.filter(id=task.id).exists())

    def test_task_delete_forbidden_for_non_creator_client(self):
        """Un cliente que no es staff ni creador de la tarea no puede eliminarla."""
        creator = User.objects.create_user(
            email="creator@smarthydro.cl", password="pass", username="creatoruser"
        )
        other = User.objects.create_user(
            email="other@smarthydro.cl", password="pass", username="othertask"
        )
        self.point.users_viewers.add(other)
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket delete tarea cliente",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        task = SupportTicketTask.objects.create(
            ticket=ticket, title="Tarea ajena", created_stage="ABIERTO", created_by=creator
        )
        token = Token.objects.create(user=other)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = client.delete(f"/api/ik/tasks/{task.id}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(SupportTicketTask.objects.filter(id=task.id).exists())

    def test_task_delete_by_creator_non_staff(self):
        """El creador de la tarea puede eliminarla aunque no sea staff."""
        creator = User.objects.create_user(
            email="creator2@smarthydro.cl", password="pass", username="creator2"
        )
        self.point.users_viewers.add(creator)
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket delete tarea creador",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        task = SupportTicketTask.objects.create(
            ticket=ticket, title="Tarea propia", created_stage="ABIERTO", created_by=creator
        )
        token = Token.objects.create(user=creator)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = client.delete(f"/api/ik/tasks/{task.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(SupportTicketTask.objects.filter(id=task.id).exists())

    def test_ticket_detail_includes_tasks(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket detail tasks",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        SupportTicketTask.objects.create(
            ticket=ticket, title="Tarea detalle", created_stage="ABIERTO", created_by=self.user
        )
        response = self.client.get(f"/api/ik/tickets/{ticket.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["tasks"]), 1)

    def test_attach_file_to_comment(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket adjunto comentario",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        comment = TicketComment.objects.create(
            ticket=ticket, author=self.user, content="Evidencia adjunta"
        )
        good_file = SimpleUploadedFile("evidencia.png", b"img", content_type="image/png")
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/{comment.id}/attachments/",
            {"file": good_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["comment"], comment.id)
        self.assertEqual(data["ticket"], ticket.id)

    def test_attach_file_to_task(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket adjunto tarea",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        task = SupportTicketTask.objects.create(
            ticket=ticket, title="Tarea adjunto", created_stage="ABIERTO", created_by=self.user
        )
        good_file = SimpleUploadedFile("plano.pdf", b"pdf", content_type="application/pdf")
        response = self.client.post(
            f"/api/ik/tasks/{task.id}/attachments/",
            {"file": good_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["task"], task.id)
        self.assertEqual(data["ticket"], ticket.id)

    def test_files_drive_lists_all_contexts(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket drive",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        comment = TicketComment.objects.create(
            ticket=ticket, author=self.user, content="Nota con adjunto"
        )
        task = SupportTicketTask.objects.create(
            ticket=ticket, title="Tarea drive", created_stage="ABIERTO", created_by=self.user
        )
        TicketAttachment.objects.create(
            ticket=ticket, comment=comment,
            file=SimpleUploadedFile("foto.png", b"f", content_type="image/png"),
            original_name="foto.png", uploaded_by=self.user,
        )
        TicketAttachment.objects.create(
            ticket=ticket, task=task,
            file=SimpleUploadedFile("informe.pdf", b"i", content_type="application/pdf"),
            original_name="informe.pdf", uploaded_by=self.user,
        )

        response = self.client.get("/api/ik/files/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        for row in data["results"]:
            self.assertIn("ticket_id", row)
            self.assertIn("ticket_title", row)
            self.assertTrue(row["comment_id"] or row["task_id"])

    def test_files_drive_filter_by_contexto_and_search(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket drive filtros",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        comment = TicketComment.objects.create(
            ticket=ticket, author=self.user, content="Nota con adjunto"
        )
        TicketAttachment.objects.create(
            ticket=ticket, comment=comment,
            file=SimpleUploadedFile("foto.png", b"f", content_type="image/png"),
            original_name="foto.png", uploaded_by=self.user,
        )

        response = self.client.get("/api/ik/files/?contexto=comentario")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

        response = self.client.get("/api/ik/files/?contexto=tarea")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

        response = self.client.get("/api/ik/files/?contexto=invalido")
        self.assertEqual(response.status_code, 400)

        response = self.client.get("/api/ik/files/?search=foto")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class TicketCommentLikeAPITests(TestCase):
    """Me gusta en comentarios de tickets (toggle + conteo + permisos)."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="likestaff@smarthydro.cl", password="pass", username="likestaff", is_staff=True
        )
        self.client_user = User.objects.create_user(
            email="likeclient@smarthydro.cl", password="pass", username="likeclient"
        )
        self.client_obj = Client.objects.create(name="Cliente Like")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Like", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Like", project=self.project, owner_user=self.client_user
        )
        self.staff_token = Token.objects.create(user=self.staff)
        self.client_token = Token.objects.create(user=self.client_user)
        self.staff_client = APIClient()
        self.staff_client.credentials(HTTP_AUTHORIZATION=f"Token {self.staff_token.key}")
        self.user_client = APIClient()
        self.user_client.credentials(HTTP_AUTHORIZATION=f"Token {self.client_token.key}")

    def _ticket_with_comment(self, is_internal=False):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket like",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        comment = TicketComment.objects.create(
            ticket=ticket, author=self.staff, content="Comentario para like",
            is_internal=is_internal,
        )
        return ticket, comment

    def test_like_toggle_on_and_off(self):
        ticket, comment = self._ticket_with_comment()
        url = f"/api/ik/tickets/{ticket.id}/comments/{comment.id}/like/"

        r1 = self.staff_client.post(url, format="json")
        self.assertEqual(r1.status_code, 200)
        data = r1.json()
        self.assertTrue(data["liked"])
        self.assertEqual(data["like_count"], 1)
        self.assertTrue(
            TicketCommentLike.objects.filter(comment=comment, user=self.staff).exists()
        )

        r2 = self.staff_client.post(url, format="json")
        self.assertEqual(r2.status_code, 200)
        data = r2.json()
        self.assertFalse(data["liked"])
        self.assertEqual(data["like_count"], 0)
        self.assertFalse(
            TicketCommentLike.objects.filter(comment=comment, user=self.staff).exists()
        )

    def test_like_count_counts_multiple_users(self):
        ticket, comment = self._ticket_with_comment()
        url = f"/api/ik/tickets/{ticket.id}/comments/{comment.id}/like/"
        self.staff_client.post(url, format="json")
        r = self.user_client.post(url, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["like_count"], 2)

    def test_list_shows_like_count_and_liked_by_me(self):
        ticket, comment = self._ticket_with_comment()
        url = f"/api/ik/tickets/{ticket.id}/comments/{comment.id}/like/"
        self.staff_client.post(url, format="json")

        response = self.staff_client.get(f"/api/ik/tickets/{ticket.id}/comments/")
        self.assertEqual(response.status_code, 200)
        comment_data = response.json()["results"][0]
        self.assertEqual(comment_data["id"], comment.id)
        self.assertEqual(comment_data["like_count"], 1)
        self.assertTrue(comment_data["liked_by_me"])

        response_other = self.user_client.get(f"/api/ik/tickets/{ticket.id}/comments/")
        self.assertEqual(response_other.status_code, 200)
        self.assertEqual(response_other.json()["results"][0]["like_count"], 1)
        self.assertFalse(response_other.json()["results"][0]["liked_by_me"])

    def test_client_cannot_like_internal_note(self):
        ticket, comment = self._ticket_with_comment(is_internal=True)
        url = f"/api/ik/tickets/{ticket.id}/comments/{comment.id}/like/"
        r = self.user_client.post(url, format="json")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(TicketCommentLike.objects.filter(comment=comment).exists())

    def test_like_missing_comment_returns_404(self):
        ticket, _ = self._ticket_with_comment()
        r = self.staff_client.post(
            f"/api/ik/tickets/{ticket.id}/comments/999999/like/", format="json"
        )
        self.assertEqual(r.status_code, 404)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class OTFlowTicketTests(TestCase):
    """Tests del flujo de Orden de Trabajo."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="staff@smarthydro.cl", password="pass", username="staff", is_staff=True
        )
        self.client_user = User.objects.create_user(
            email="client@smarthydro.cl", password="pass", username="clientuser"
        )
        self.client_obj = Client.objects.create(name="Cliente OT")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto OT", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto OT", project=self.project, owner_user=self.client_user
        )
        self.cat_ot = TicketCategory.objects.get(
            category_type="WORK_ORDER", name="Visita técnica"
        )
        self.staff_token = Token.objects.create(user=self.staff)
        self.client_token = Token.objects.create(user=self.client_user)

    def _client_for(self, user_type):
        client = APIClient()
        token = self.staff_token if user_type == "staff" else self.client_token
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def test_staff_can_set_scheduled_date_and_visit_report(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Falla hardware",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        api_client = self._client_for("staff")
        response = api_client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {
                "status": "EN_ORDEN_TRABAJO",
                "work_order_category": self.cat_ot.id,
                "scheduled_date": "2026-07-15",
                "visit_report": "Se reemplazó el sensor. Quedó operativo.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "EN_ORDEN_TRABAJO")
        self.assertEqual(data["work_order_category"], self.cat_ot.id)
        self.assertEqual(data["scheduled_date"], "2026-07-15")
        self.assertEqual(data["visit_report"], "Se reemplazó el sensor. Quedó operativo.")

    def test_client_cannot_set_scheduled_date(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Falla hardware",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        api_client = self._client_for("client")
        response = api_client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {
                "scheduled_date": "2026-07-15",
                "visit_report": "Intento de edición",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.scheduled_date)
        self.assertIsNone(ticket.visit_report)

    def test_ticket_status_en_orden_trabajo(self):
        self.assertIn(
            "EN_ORDEN_TRABAJO",
            [choice[0] for choice in SupportTicket.STATUS_CHOICES],
        )

    def test_ticket_category_cannot_be_work_order(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Categoría mixta",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        api_client = self._client_for("staff")
        response = api_client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {"category": self.cat_ot.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        ticket.refresh_from_db()
        self.assertNotEqual(ticket.category_id, self.cat_ot.id)

    def test_work_order_category_must_be_subcategory(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="OT sin subcategoría",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        wo_parent = TicketCategory.objects.get(
            category_type="WORK_ORDER", parent__isnull=True
        )
        api_client = self._client_for("staff")
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "EN_ORDEN_TRABAJO", "work_order_category": wo_parent.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        ticket.refresh_from_db()
        self.assertNotEqual(ticket.status, "EN_ORDEN_TRABAJO")

    def test_entering_ot_requires_work_order_category(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Entra a OT",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        api_client = self._client_for("staff")

        # PATCH a EN_ORDEN_TRABAJO sin categoría OT → 400
        response = api_client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {"status": "EN_ORDEN_TRABAJO"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        # Endpoint de estado sin categoría OT → 400
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "EN_ORDEN_TRABAJO"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        ticket.refresh_from_db()
        self.assertNotEqual(ticket.status, "EN_ORDEN_TRABAJO")

    def test_entering_ot_rejects_non_work_order_category(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Entra a OT mal",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        cat_software = TicketCategory.objects.get(category_type="SOFTWARE", name="Software")
        api_client = self._client_for("staff")
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "EN_ORDEN_TRABAJO", "work_order_category": cat_software.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_leaving_ot_clears_work_order_category(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Sale de OT",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        ticket.status = "EN_ORDEN_TRABAJO"
        ticket.work_order_category = self.cat_ot
        ticket.save()

        api_client = self._client_for("staff")
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "RESUELTO"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "RESUELTO")
        self.assertIsNone(ticket.work_order_category)

    def test_ot_keeps_original_category(self):
        cat_software = TicketCategory.objects.get(category_type="SOFTWARE", name="Software")
        ticket = _create_ticket_with_point(
            self.point,
            title="OT conserva categoría original",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            category=cat_software,
        )
        api_client = self._client_for("staff")
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "EN_ORDEN_TRABAJO", "work_order_category": self.cat_ot.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.category, cat_software)
        self.assertEqual(ticket.work_order_category, self.cat_ot)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TicketScheduledDateConfirmationTests(TestCase):
    """Tests de la confirmación de fecha planificada de una OT."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="confirmstaff@smarthydro.cl", password="pass", username="confirmstaff", is_staff=True
        )
        self.client_user = User.objects.create_user(
            email="confirmclient@smarthydro.cl", password="pass", username="confirmclient"
        )
        self.operator = User.objects.create_user(
            email="confirmoper@smarthydro.cl", password="pass", username="confirmoper"
        )
        self.client_obj = Client.objects.create(name="Cliente Conf")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Conf", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Conf", project=self.project, owner_user=self.client_user
        )
        self.cat_wo = TicketCategory.objects.get(
            category_type="WORK_ORDER", name="Orden de Trabajo"
        )
        self.cat_wo.operators.add(self.operator)
        self.staff_token = Token.objects.create(user=self.staff)
        self.client_token = Token.objects.create(user=self.client_user)

    def _client_for(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def _create_ot_ticket(self, **kwargs):
        defaults = {
            "title": "OT prueba",
            "description": "...",
            "origin": "CLIENTE",
            "source": "APP_CLIENTE",
            "category": self.cat_wo,
            "priority": "MEDIA",
            "scheduled_date": "2026-08-10",
        }
        defaults.update(kwargs)
        ticket = SupportTicket.objects.create(**defaults)
        ticket.points.add(self.point)
        return ticket

    def test_confirm_requires_scheduled_date(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="OT sin fecha",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            category=self.cat_wo,
        )
        api_client = self._client_for(self.staff)
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/confirm-scheduled-date/",
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("fecha", response.json().get("error", "").lower())
        ticket.refresh_from_db()
        self.assertFalse(ticket.scheduled_date_confirmed)

    def test_confirm_scheduled_date_sets_fields(self):
        ticket = self._create_ot_ticket()
        api_client = self._client_for(self.client_user)
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/confirm-scheduled-date/",
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["scheduled_date_confirmed"])
        self.assertEqual(data["scheduled_date_confirmed_by"], self.client_user.id)
        self.assertIsNotNone(data["scheduled_date_confirmed_at"])
        ticket.refresh_from_db()
        self.assertTrue(ticket.scheduled_date_confirmed)
        self.assertEqual(ticket.scheduled_date_confirmed_by, self.client_user)
        self.assertIsNotNone(ticket.scheduled_date_confirmed_at)

    def test_confirm_sends_email_to_confirmer_and_involved(self):
        ticket = self._create_ot_ticket(
            title="OT notificable",
            created_by=self.staff,
            assigned_to=self.operator,
        )
        from django.core import mail

        mail.outbox = []
        api_client = self._client_for(self.client_user)
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/confirm-scheduled-date/",
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        recipients = set(mail.outbox[0].to)
        self.assertIn(self.client_user.email, recipients)
        self.assertIn(self.staff.email, recipients)
        self.assertIn(self.operator.email, recipients)
        self.assertIn("Fecha confirmada", mail.outbox[0].subject)

    def test_confirm_is_idempotent_and_sends_single_email(self):
        ticket = self._create_ot_ticket()
        from django.core import mail

        api_client = self._client_for(self.client_user)
        mail.outbox = []
        first = api_client.post(
            f"/api/ik/tickets/{ticket.id}/confirm-scheduled-date/",
            format="json",
        )
        self.assertEqual(first.status_code, 200)
        second = api_client.post(
            f"/api/ik/tickets/{ticket.id}/confirm-scheduled-date/",
            format="json",
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_confirmation_resets_when_scheduled_date_changes(self):
        ticket = self._create_ot_ticket()
        api_client = self._client_for(self.client_user)
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/confirm-scheduled-date/",
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        staff_client = self._client_for(self.staff)
        response = staff_client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {"scheduled_date": "2026-08-15"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.scheduled_date.strftime("%Y-%m-%d"), "2026-08-15")
        self.assertFalse(ticket.scheduled_date_confirmed)
        self.assertIsNone(ticket.scheduled_date_confirmed_by)
        self.assertIsNone(ticket.scheduled_date_confirmed_at)

    def test_user_without_access_cannot_confirm(self):
        outsider = User.objects.create_user(
            email="outsider@smarthydro.cl", password="pass", username="outsider"
        )
        ticket = self._create_ot_ticket()
        api_client = self._client_for(outsider)
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/confirm-scheduled-date/",
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_detail_exposes_confirmation_fields(self):
        ticket = self._create_ot_ticket()
        api_client = self._client_for(self.client_user)
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/confirm-scheduled-date/",
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        detail = api_client.get(f"/api/ik/tickets/{ticket.id}/")
        self.assertEqual(detail.status_code, 200)
        data = detail.json()
        self.assertTrue(data["scheduled_date_confirmed"])
        self.assertEqual(
            data["scheduled_date_confirmed_by_name"],
            self.client_user.get_full_name() or self.client_user.email,
        )


class TicketScheduledDateCancellationTests(TestCase):
    """Tests de la cancelación de fecha planificada de una OT."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="cancelstaff@smarthydro.cl", password="pass", username="cancelstaff", is_staff=True
        )
        self.client_user = User.objects.create_user(
            email="cancelclient@smarthydro.cl", password="pass", username="cancelclient"
        )
        self.operator = User.objects.create_user(
            email="canceloper@smarthydro.cl", password="pass", username="canceloper"
        )
        self.client_obj = Client.objects.create(name="Cliente Cancel")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Cancel", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Cancel", project=self.project, owner_user=self.client_user
        )
        self.cat_wo = TicketCategory.objects.get(
            category_type="WORK_ORDER", name="Orden de Trabajo"
        )
        self.cat_wo.operators.add(self.operator)
        self.staff_token = Token.objects.create(user=self.staff)
        self.client_token = Token.objects.create(user=self.client_user)

    def _client_for(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def _create_ot_ticket(self, **kwargs):
        defaults = {
            "title": "OT cancel",
            "description": "...",
            "origin": "CLIENTE",
            "source": "APP_CLIENTE",
            "category": self.cat_wo,
            "priority": "MEDIA",
            "scheduled_date": "2026-08-10",
        }
        defaults.update(kwargs)
        ticket = SupportTicket.objects.create(**defaults)
        ticket.points.add(self.point)
        return ticket

    def test_cancel_requires_scheduled_date(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="OT sin fecha",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            category=self.cat_wo,
        )
        api_client = self._client_for(self.staff)
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/cancel-scheduled-date/",
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("fecha", response.json().get("error", "").lower())
        ticket.refresh_from_db()
        self.assertFalse(ticket.scheduled_date_cancelled)

    def test_cancel_sets_fields_and_sends_email(self):
        ticket = self._create_ot_ticket(
            title="OT cancelable",
            created_by=self.staff,
            assigned_to=self.operator,
        )
        from django.core import mail

        mail.outbox = []
        api_client = self._client_for(self.client_user)
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/cancel-scheduled-date/",
            {"reason": "Clima adverso"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["scheduled_date_cancelled"])
        self.assertEqual(data["scheduled_date_cancelled_by"], self.client_user.id)
        self.assertIsNotNone(data["scheduled_date_cancelled_at"])
        self.assertEqual(data["scheduled_date_cancelled_reason"], "Clima adverso")

        ticket.refresh_from_db()
        self.assertTrue(ticket.scheduled_date_cancelled)
        self.assertEqual(ticket.scheduled_date_cancelled_by, self.client_user)
        self.assertIsNotNone(ticket.scheduled_date_cancelled_at)
        self.assertEqual(ticket.scheduled_date_cancelled_reason, "Clima adverso")

        self.assertEqual(len(mail.outbox), 1)
        recipients = set(mail.outbox[0].to)
        self.assertIn(self.client_user.email, recipients)
        self.assertIn(self.staff.email, recipients)
        self.assertIn(self.operator.email, recipients)
        self.assertIn("Fecha cancelada", mail.outbox[0].subject)
        self.assertIn("Clima adverso", mail.outbox[0].body)

    def test_cancel_unconfirms_confirmed_date(self):
        ticket = self._create_ot_ticket()
        api_client = self._client_for(self.client_user)
        confirm = api_client.post(
            f"/api/ik/tickets/{ticket.id}/confirm-scheduled-date/",
            format="json",
        )
        self.assertEqual(confirm.status_code, 200)

        cancel = api_client.post(
            f"/api/ik/tickets/{ticket.id}/cancel-scheduled-date/",
            format="json",
        )
        self.assertEqual(cancel.status_code, 200)
        data = cancel.json()
        self.assertTrue(data["scheduled_date_cancelled"])
        self.assertFalse(data["scheduled_date_confirmed"])
        self.assertIsNone(data["scheduled_date_confirmed_by"])
        self.assertIsNone(data["scheduled_date_confirmed_at"])

        ticket.refresh_from_db()
        self.assertTrue(ticket.scheduled_date_cancelled)
        self.assertFalse(ticket.scheduled_date_confirmed)
        self.assertIsNone(ticket.scheduled_date_confirmed_by)
        self.assertIsNone(ticket.scheduled_date_confirmed_at)

    def test_cancel_is_idempotent_and_sends_single_email(self):
        ticket = self._create_ot_ticket()
        from django.core import mail

        api_client = self._client_for(self.client_user)
        mail.outbox = []
        first = api_client.post(
            f"/api/ik/tickets/{ticket.id}/cancel-scheduled-date/",
            format="json",
        )
        self.assertEqual(first.status_code, 200)
        second = api_client.post(
            f"/api/ik/tickets/{ticket.id}/cancel-scheduled-date/",
            format="json",
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_reschedule_resets_cancellation(self):
        ticket = self._create_ot_ticket()
        api_client = self._client_for(self.client_user)
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/cancel-scheduled-date/",
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        staff_client = self._client_for(self.staff)
        response = staff_client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {"scheduled_date": "2026-08-15"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.scheduled_date.strftime("%Y-%m-%d"), "2026-08-15")
        self.assertFalse(ticket.scheduled_date_cancelled)
        self.assertIsNone(ticket.scheduled_date_cancelled_by)
        self.assertIsNone(ticket.scheduled_date_cancelled_at)
        self.assertIsNone(ticket.scheduled_date_cancelled_reason)

    def test_user_without_access_cannot_cancel(self):
        outsider = User.objects.create_user(
            email="canceloutsider@smarthydro.cl", password="pass", username="canceloutsider"
        )
        ticket = self._create_ot_ticket()
        api_client = self._client_for(outsider)
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/cancel-scheduled-date/",
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_detail_exposes_cancellation_fields(self):
        ticket = self._create_ot_ticket()
        api_client = self._client_for(self.client_user)
        response = api_client.post(
            f"/api/ik/tickets/{ticket.id}/cancel-scheduled-date/",
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        detail = api_client.get(f"/api/ik/tickets/{ticket.id}/")
        self.assertEqual(detail.status_code, 200)
        data = detail.json()
        self.assertTrue(data["scheduled_date_cancelled"])
        self.assertEqual(
            data["scheduled_date_cancelled_by_name"],
            self.client_user.get_full_name() or self.client_user.email,
        )


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TicketOperatorNotificationTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            email="operador@smarthydro.cl", password="pass", username="operador"
        )
        self.user = User.objects.create_user(
            email="cliente@smarthydro.cl", password="pass", username="clienteuser"
        )
        self.client_obj = Client.objects.create(name="Cliente Notif")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Notif", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Notif", project=self.project, owner_user=self.user
        )
        self.cat_hardware = TicketCategory.objects.get(
            category_type="HARDWARE", name="Hardware"
        )
        self.cat_hardware.operators.add(self.operator)
        self.cat_hardware.notify_operators_on_create = True
        self.cat_hardware.save()

    def test_notify_category_operators_sends_email(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Falla notificable",
            description="...",
            category=self.cat_hardware,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        from django.core import mail
        from api.core.signals.tickets import _notify_category_operators

        mail.outbox = []
        _notify_category_operators(ticket.id)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.operator.email, mail.outbox[0].to)
        self.assertIn("Falla notificable", mail.outbox[0].subject)

    def test_notify_respects_disabled_flag(self):
        self.cat_hardware.notify_operators_on_create = False
        self.cat_hardware.save()
        ticket = _create_ticket_with_point(
            self.point,
            title="Falla silenciada",
            description="...",
            category=self.cat_hardware,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        from django.core import mail
        from api.core.signals.tickets import _notify_category_operators

        mail.outbox = []
        _notify_category_operators(ticket.id)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class TicketMyDeskTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            email="deskoper@smarthydro.cl", password="pass", username="deskoper", is_staff=True
        )
        self.other_user = User.objects.create_user(
            email="other@smarthydro.cl", password="pass", username="otheruser", is_staff=True
        )
        self.client_obj = Client.objects.create(name="Cliente Desk")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Desk", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Desk", project=self.project, owner_user=self.operator
        )
        self.cat_software = TicketCategory.objects.get(
            category_type="SOFTWARE", name="Software"
        )
        self.cat_software.operators.add(self.operator)
        self.token = Token.objects.create(user=self.operator)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_my_desk_returns_assigned_and_operated_tickets(self):
        """my_desk por defecto muestra asignados + tickets de categorias operadas."""
        assigned_ticket = _create_ticket_with_point(
            self.point,
            title="Asignado a mi",
            description="...",
            assigned_to=self.operator,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        operated_ticket = _create_ticket_with_point(
            self.point,
            title="Categoría que opero",
            description="...",
            category=self.cat_software,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        other_ticket = _create_ticket_with_point(
            self.point,
            title="De otro operador",
            description="...",
            assigned_to=self.other_user,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )

        response = self.client.get("/api/ik/tickets/my_desk/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        titles = {r["title"] for r in data["results"]}
        self.assertIn("Asignado a mi", titles)
        self.assertIn("Categoría que opero", titles)
        self.assertNotIn("De otro operador", titles)

    def test_my_desk_includes_tickets_i_created(self):
        """Tickets creados por el usuario aparecen aunque no esten asignados
        ni en sus categorias."""
        created_ticket = _create_ticket_with_point(
            self.point,
            title="Ticket que cree yo",
            description="...",
            created_by=self.operator,
            assigned_to=self.other_user,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        other_ticket = _create_ticket_with_point(
            self.point,
            title="Ticket de otro",
            description="...",
            created_by=self.other_user,
            assigned_to=self.other_user,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )

        response = self.client.get("/api/ik/tickets/my_desk/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        titles = {r["title"] for r in data["results"]}
        self.assertIn("Ticket que cree yo", titles)
        self.assertNotIn("Ticket de otro", titles)

    def test_my_desk_scope_assigned_only(self):
        """scope=assigned filtra solo tickets asignados al usuario."""
        _create_ticket_with_point(
            self.point,
            title="Asignado a mi",
            description="...",
            assigned_to=self.operator,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        _create_ticket_with_point(
            self.point,
            title="Categoría que opero",
            description="...",
            category=self.cat_software,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )

        response = self.client.get("/api/ik/tickets/my_desk/?scope=assigned")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        titles = {r["title"] for r in data["results"]}
        self.assertIn("Asignado a mi", titles)
        self.assertNotIn("Categoría que opero", titles)

    def test_my_desk_scope_category_only(self):
        """scope=category filtra solo tickets de categorias operadas."""
        _create_ticket_with_point(
            self.point,
            title="Asignado a mi",
            description="...",
            assigned_to=self.operator,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        _create_ticket_with_point(
            self.point,
            title="Categoría que opero",
            description="...",
            category=self.cat_software,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )

        response = self.client.get("/api/ik/tickets/my_desk/?scope=category")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        titles = {r["title"] for r in data["results"]}
        self.assertNotIn("Asignado a mi", titles)
        self.assertIn("Categoría que opero", titles)

    def test_my_desk_filter_by_parent_category_includes_subcategories(self):
        """Filtrar my_desk por categoria padre incluye tickets de subcategorias."""
        sub_cat = TicketCategory.objects.create(
            category_type="SOFTWARE",
            name="Sub Software",
            parent=self.cat_software,
        )
        _create_ticket_with_point(
            self.point,
            title="Ticket subcategoria escritorio",
            description="...",
            category=sub_cat,
            assigned_to=self.operator,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.get(f"/api/ik/tickets/my_desk/?category={self.cat_software.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        titles = {r["title"] for r in data["results"]}
        self.assertIn("Ticket subcategoria escritorio", titles)

    def test_my_desk_filter_by_created_range(self):
        """created_from/created_to filtran por fecha de creación en my_desk."""
        from datetime import timedelta

        old = _create_ticket_with_point(
            self.point,
            title="Ticket viejo",
            description="...",
            assigned_to=self.operator,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        SupportTicket.objects.filter(pk=old.pk).update(
            created=timezone.now() - timedelta(days=30)
        )
        recent = _create_ticket_with_point(
            self.point,
            title="Ticket reciente",
            description="...",
            assigned_to=self.operator,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        SupportTicket.objects.filter(pk=recent.pk).update(
            created=timezone.now() - timedelta(days=1)
        )

        today = timezone.localtime().date()
        response = self.client.get(
            f"/api/ik/tickets/my_desk/?created_from={today - timedelta(days=7)}&created_to={today}"
        )
        self.assertEqual(response.status_code, 200)
        titles = {r["title"] for r in response.json()["results"]}
        self.assertIn("Ticket reciente", titles)
        self.assertNotIn("Ticket viejo", titles)

    def test_my_desk_created_filter_invalid_format(self):
        """created_from en formato inválido retorna 400."""
        response = self.client.get("/api/ik/tickets/my_desk/?created_from=not-a-date")
        self.assertEqual(response.status_code, 400)

    def test_my_desk_created_filter_applies_before_pagination(self):
        """El filtro de fechas se aplica antes de paginar (page_size alto no los trae)."""
        from datetime import timedelta

        for i in range(5):
            old = _create_ticket_with_point(
                self.point,
                title=f"Viejo fuera de rango {i}",
                description="...",
                assigned_to=self.operator,
                origin="CLIENTE",
                source="APP_CLIENTE",
            )
            SupportTicket.objects.filter(pk=old.pk).update(
                created=timezone.now() - timedelta(days=30)
            )
        recent = _create_ticket_with_point(
            self.point,
            title="Solo en rango",
            description="...",
            assigned_to=self.operator,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        SupportTicket.objects.filter(pk=recent.pk).update(created=timezone.now())

        today = timezone.localtime().date()
        response = self.client.get(
            f"/api/ik/tickets/my_desk/?created_from={today}&created_to={today}&page_size=100"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        titles = {r["title"] for r in data["results"]}
        self.assertEqual(len(titles), 1)
        self.assertIn("Solo en rango", titles)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class TicketCategoryCRUDTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="staff@smarthydro.cl", password="pass", username="staffcat", is_staff=True
        )
        self.client_user = User.objects.create_user(
            email="clientcat@smarthydro.cl", password="pass", username="clientcat"
        )
        self.operator = User.objects.create_user(
            email="operatorcat@smarthydro.cl", password="pass", username="operatorcat"
        )
        self.cat_parent = TicketCategory.objects.get(category_type="SOFTWARE", name="Software")

    def _client_for(self, user):
        token = Token.objects.create(user=user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def test_client_cannot_create_category(self):
        client = self._client_for(self.client_user)
        response = client.post(
            "/api/ik/ticket-categories/",
            {"category_type": "SOFTWARE", "name": "Nueva"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_can_create_category(self):
        client = self._client_for(self.staff)
        response = client.post(
            "/api/ik/ticket-categories/",
            {
                "category_type": "SOFTWARE",
                "name": "Subcategoría API",
                "parent": self.cat_parent.id,
                "operators": [self.operator.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "Subcategoría API")
        self.assertIn(self.operator.id, data["operators"])

    def test_staff_can_update_category(self):
        category = TicketCategory.objects.create(
            category_type="SOFTWARE", name="Editable", parent=self.cat_parent
        )
        client = self._client_for(self.staff)
        response = client.patch(
            f"/api/ik/ticket-categories/{category.id}/",
            {"notify_operators_on_create": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        category.refresh_from_db()
        self.assertFalse(category.notify_operators_on_create)

    def test_category_parent_must_match_type(self):
        hardware_parent = TicketCategory.objects.get(category_type="HARDWARE", name="Hardware")
        client = self._client_for(self.staff)
        response = client.post(
            "/api/ik/ticket-categories/",
            {"category_type": "SOFTWARE", "name": "Mal padre", "parent": hardware_parent.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_default_list_includes_work_order_categories(self):
        client = self._client_for(self.staff)
        response = client.get("/api/ik/ticket-categories/", format="json")
        self.assertEqual(response.status_code, 200)
        categories = response.json()["categories"]
        self.assertTrue(categories)
        self.assertTrue(
            any(c["category_type"] == "WORK_ORDER" for c in categories),
            "El listado por defecto debe incluir las categorías de OT "
            "(el frontend las consume sin filtro).",
        )

    def test_work_order_categories_available_with_filter(self):
        client = self._client_for(self.staff)
        response = client.get(
            "/api/ik/ticket-categories/?category_type=WORK_ORDER", format="json"
        )
        self.assertEqual(response.status_code, 200)
        categories = response.json()["categories"]
        self.assertTrue(categories)
        for c in categories:
            self.assertEqual(c["category_type"], "WORK_ORDER")


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class SLAConfigCRUDTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="staffsla@smarthydro.cl", password="pass", username="staffsla", is_staff=True
        )
        self.client_user = User.objects.create_user(
            email="clientsla@smarthydro.cl", password="pass", username="clientsla"
        )
        self.cat = TicketCategory.objects.get(category_type="HARDWARE", name="Hardware")

    def _client_for(self, user):
        token = Token.objects.create(user=user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def test_client_cannot_create_sla(self):
        client = self._client_for(self.client_user)
        response = client.post(
            "/api/ik/sla-configs/",
            {"priority": "ALTA", "response_time_hours": 2, "resolution_time_hours": 8},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_can_create_sla(self):
        client = self._client_for(self.staff)
        response = client.post(
            "/api/ik/sla-configs/",
            {
                "category": self.cat.id,
                "priority": "ALTA",
                "response_time_hours": 2,
                "resolution_time_hours": 8,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["response_time_hours"], 2)

    def test_sla_duplicate_rejected(self):
        SLAConfig.objects.create(
            category=self.cat, priority="ALTA", response_time_hours=1, resolution_time_hours=4
        )
        client = self._client_for(self.staff)
        response = client.post(
            "/api/ik/sla-configs/",
            {
                "category": self.cat.id,
                "priority": "ALTA",
                "response_time_hours": 2,
                "resolution_time_hours": 8,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class BusinessHoursTests(TestCase):
    def test_business_hours_skips_night(self):
        from api.core.utils.business_hours import add_business_hours
        # Lunes 8:00 → +1h debe ser Lunes 10:00
        start = timezone.make_aware(timezone.datetime(2026, 7, 6, 8, 0))
        result = add_business_hours(start, 1)
        self.assertEqual(result.weekday(), 0)  # Lunes
        self.assertEqual(result.hour, 10)

    def test_business_hours_skips_weekend(self):
        from api.core.utils.business_hours import add_business_hours
        # Viernes 17:00 → +2h debe ser Lunes 10:00
        start = timezone.make_aware(timezone.datetime(2026, 7, 3, 17, 0))
        result = add_business_hours(start, 2)
        self.assertEqual(result.weekday(), 0)  # Lunes
        self.assertEqual(result.hour, 10)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotifySLAOverdueTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(
            email="slaop@smarthydro.cl", password="pass", username="slaop"
        )
        self.user = User.objects.create_user(
            email="slauser@smarthydro.cl", password="pass", username="slauser"
        )
        self.client_obj = Client.objects.create(name="Cliente SLA")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto SLA", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto SLA", project=self.project, owner_user=self.user
        )
        self.cat = TicketCategory.objects.get(category_type="HARDWARE", name="Hardware")
        self.cat.operators.add(self.operator)

    def test_command_notifies_overdue_resolution(self):
        ticket = SupportTicket.objects.create(
            title="Ticket vencido",
            description="...",
            status="ABIERTO",
            priority="ALTA",
            category=self.cat,
            origin="INTERNO",
            source="SISTEMA",
            sla_deadline_resolution=timezone.now() - timezone.timedelta(hours=1),
        )
        ticket.points.add(self.point)

        from django.core import mail
        mail.outbox = []
        call_command("notify_sla_overdue", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.operator.email, mail.outbox[0].to)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.sla_last_overdue_notification)

    def test_command_sends_webhook_when_configured(self):
        from unittest import mock
        ticket = SupportTicket.objects.create(
            title="Ticket webhook",
            description="...",
            status="ABIERTO",
            priority="ALTA",
            category=self.cat,
            origin="INTERNO",
            source="SISTEMA",
            sla_deadline_resolution=timezone.now() - timezone.timedelta(hours=1),
        )
        ticket.points.add(self.point)
        sla = SLAConfig.objects.create(
            client=self.client_obj,
            category=self.cat,
            priority="ALTA",
            response_time_hours=4,
            resolution_time_hours=24,
            webhook_url="https://hooks.example.com/sla",
        )
        ticket.sla_config = sla
        ticket.save(update_fields=["sla_config"])

        from django.core import mail
        mail.outbox = []
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = type(
                "R", (), {"raise_for_status": lambda self: None}
            )()
            call_command("notify_sla_overdue", stdout=StringIO())
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://hooks.example.com/sla")
        self.assertEqual(kwargs["json"]["event"], "sla_overdue")
        self.assertEqual(kwargs["json"]["ticket_id"], ticket.id)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.sla_last_overdue_notification)

    def test_command_respects_notify_email_flag(self):
        self.operator.notify_email = False
        self.operator.save(update_fields=["notify_email"])
        ticket = SupportTicket.objects.create(
            title="Ticket sin correo",
            description="...",
            status="ABIERTO",
            priority="ALTA",
            category=self.cat,
            origin="INTERNO",
            source="SISTEMA",
            sla_deadline_resolution=timezone.now() - timezone.timedelta(hours=1),
        )
        ticket.points.add(self.point)

        from django.core import mail
        mail.outbox = []
        call_command("notify_sla_overdue", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.sla_last_overdue_notification)


# Tests adicionales de regresión para bugs encontrados en auditoría SLA.


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TicketOperationsOriginTests(TestCase):
    """Tests del origen OPERACIONES para tickets internos."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="opstaff@smarthydro.cl", password="pass", username="opstaff", is_staff=True
        )
        self.client_user = User.objects.create_user(
            email="opclient@smarthydro.cl", password="pass", username="opclient"
        )
        self.cat = TicketCategory.objects.get(category_type="SOFTWARE", name="Software")
        SLAConfig.objects.create(
            category=self.cat,
            priority="MEDIA",
            response_time_hours=4,
            resolution_time_hours=24,
        )
        self.staff_token = Token.objects.create(user=self.staff)
        self.client_token = Token.objects.create(user=self.client_user)

    def _client_for(self, user):
        client = APIClient()
        token = self.staff_token if user == self.staff else self.client_token
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def test_staff_can_create_operations_ticket_without_points(self):
        client = self._client_for(self.staff)
        response = client.post(
            "/api/ik/tickets/",
            {
                "title": "Ticket operaciones",
                "description": "Sin punto",
                "origin": "OPERACIONES",
                "source": "APP_CLIENTE",
                "priority": "MEDIA",
                "category": self.cat.id,
                "points": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["origin"], "OPERACIONES")
        self.assertEqual(data["points"], [])
        self.assertIsNotNone(data["sla_deadline_response"])
        self.assertIsNotNone(data["sla_deadline_resolution"])

    def test_client_cannot_create_operations_ticket(self):
        client = self._client_for(self.client_user)
        response = client.post(
            "/api/ik/tickets/",
            {
                "title": "Intento operaciones",
                "description": "...",
                "origin": "OPERACIONES",
                "priority": "MEDIA",
                "category": self.cat.id,
                "points": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class TicketSLARecalculationTests(TestCase):
    """Tests de recálculo de SLA al editar tickets."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="slastaff@smarthydro.cl", password="pass", username="slastaff", is_staff=True
        )
        self.client_user = User.objects.create_user(
            email="slaclient@smarthydro.cl", password="pass", username="slaclient"
        )
        self.client_obj = Client.objects.create(name="Cliente SLARec")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto SLARec", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto SLARec", project=self.project, owner_user=self.client_user
        )
        self.cat_hardware = TicketCategory.objects.get(category_type="HARDWARE", name="Hardware")
        self.cat_software = TicketCategory.objects.get(category_type="SOFTWARE", name="Software")
        SLAConfig.objects.create(
            category=self.cat_hardware,
            priority="ALTA",
            response_time_hours=2,
            resolution_time_hours=8,
        )
        SLAConfig.objects.create(
            category=self.cat_software,
            priority="BAJA",
            response_time_hours=24,
            resolution_time_hours=120,
        )
        self.token = Token.objects.create(user=self.staff)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_sla_recalculates_when_priority_changes(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket SLA recalc",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            priority="BAJA",
            category=self.cat_software,
        )
        old_response = ticket.sla_deadline_response

        response = self.client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {"priority": "ALTA", "category": self.cat_hardware.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.priority, "ALTA")
        self.assertEqual(ticket.category, self.cat_hardware)
        self.assertIsNotNone(ticket.sla_deadline_response)
        self.assertNotEqual(ticket.sla_deadline_response, old_response)

    def test_sla_applies_when_origin_changes_from_interno(self):
        ticket = SupportTicket.objects.create(
            title="Ticket interno",
            description="...",
            origin="INTERNO",
            source="SISTEMA",
            priority="ALTA",
            category=self.cat_hardware,
        )
        ticket.points.add(self.point)
        self.assertIsNone(ticket.sla_deadline_response)

        response = self.client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {"origin": "CLIENTE"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.origin, "CLIENTE")
        self.assertIsNotNone(ticket.sla_deadline_response)

    def test_client_cannot_change_priority_or_category(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket cliente",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            priority="BAJA",
            category=self.cat_software,
        )
        client_token = Token.objects.create(user=self.client_user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {client_token.key}")

        response = client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {"priority": "ALTA", "category": self.cat_hardware.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.priority, "BAJA")
        self.assertEqual(ticket.category, self.cat_software)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class TicketNotificationAPITests(TestCase):
    """Endpoints de notificaciones in-app del subsistema de tickets."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="notif@smarthydro.cl", password="pass", username="notifuser"
        )
        self.client_obj = Client.objects.create(name="Cliente Notif")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Notif", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Notif", project=self.project, owner_user=self.user
        )
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _make_ticket_with_mention(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket notif",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        comment = TicketComment.objects.create(
            ticket=ticket, author=self.user, content="Hola @notifuser"
        )
        TicketNotification.objects.create(
            user=self.user,
            ticket=ticket,
            comment=comment,
            message="Te mencionaron en el ticket",
        )
        return ticket, comment

    def test_list_notifications(self):
        ticket, _ = self._make_ticket_with_mention()
        response = self.client.get("/api/ik/tickets/notifications/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["unread_count"], 1)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["ticket_title"], ticket.title)

    def test_mark_read_single(self):
        ticket, _ = self._make_ticket_with_mention()
        notif = TicketNotification.objects.get(user=self.user)
        response = self.client.post(
            "/api/ik/tickets/notifications/mark-read/",
            {"id": notif.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unread_count"], 0)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_mark_read_bulk(self):
        self._make_ticket_with_mention()
        self._make_ticket_with_mention()
        ids = list(TicketNotification.objects.filter(user=self.user).values_list("id", flat=True))
        response = self.client.post(
            "/api/ik/tickets/notifications/mark-read/",
            {"ids": ids},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unread_count"], 0)
        self.assertEqual(
            TicketNotification.objects.filter(user=self.user, is_read=True).count(), 2
        )

    def test_list_notifications_unread_only(self):
        self._make_ticket_with_mention()
        notif = TicketNotification.objects.get(user=self.user)
        notif.is_read = True
        notif.save(update_fields=["is_read"])
        response = self.client.get(
            "/api/ik/tickets/notifications/?unread_only=true"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["unread_count"], 0)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class TicketCommentStatusChangeTests(TestCase):
    """Tests de cambio de estado vía comentario."""
    def setUp(self):
        self.staff = User.objects.create_user(
            email="commentstaff@smarthydro.cl", password="pass", username="commentstaff", is_staff=True
        )
        self.client_user = User.objects.create_user(
            email="commentclient@smarthydro.cl", password="pass", username="commentclient"
        )
        self.client_obj = Client.objects.create(name="Cliente Comment")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Comment", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Comment", project=self.project, owner_user=self.client_user
        )
        self.cat = TicketCategory.objects.get(category_type="HARDWARE", name="Hardware")
        SLAConfig.objects.create(
            category=self.cat,
            priority="ALTA",
            response_time_hours=2,
            resolution_time_hours=8,
        )
        self.token = Token.objects.create(user=self.staff)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_internal_comment_does_not_mark_sla_responded(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket interno comment",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            category=self.cat,
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "Nota interna", "is_internal": True},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.sla_responded_at)

    def test_comment_status_change_resolved_sets_timestamps(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket resolver por comentario",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            category=self.cat,
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "Resuelto", "status_change": "RESUELTO"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "RESUELTO")
        self.assertIsNotNone(ticket.resolved_at)
        self.assertIsNotNone(ticket.sla_resolved_at)

    def test_comment_status_change_invalid_returns_400(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket estado invalido",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "Intento", "status_change": "ESTADO_FALSO"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class TicketStatusResolvedAtTests(TestCase):
    """Tests de sla_resolved_at al cambiar estado."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="statusstaff@smarthydro.cl", password="pass", username="statusstaff", is_staff=True
        )
        self.client_obj = Client.objects.create(name="Cliente Status")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Status", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Status", project=self.project, owner_user=self.staff
        )
        self.token = Token.objects.create(user=self.staff)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_status_change_to_resolved_sets_sla_resolved_at(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket resolver",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "RESUELTO"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.sla_resolved_at)
        self.assertIsNotNone(ticket.sla_responded_at)

    def test_status_change_preserves_existing_sla_responded_at(self):
        from datetime import timedelta
        responded = timezone.now() - timedelta(hours=3)
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket con respuesta previa",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            sla_responded_at=responded,
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "RESUELTO"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.sla_responded_at, responded)
        self.assertIsNotNone(ticket.sla_resolved_at)

    def test_status_change_to_open_status_sets_sla_responded_at(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket a analisis",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "EN_ANALISIS"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.sla_responded_at)

    def test_assign_sets_sla_responded_at(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket a asignar",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/assign/",
            {"assigned_to": self.staff.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.sla_responded_at)

    def test_patch_by_staff_sets_sla_responded_at(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket con fecha",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {"scheduled_date": "2026-08-20"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.sla_responded_at)

    def test_client_actions_do_not_set_sla_responded_at(self):
        client_user = User.objects.create_user(
            email="respclient@smarthydro.cl", password="pass", username="respclient"
        )
        client_token = Token.objects.create(user=client_user)
        client_api = APIClient()
        client_api.credentials(HTTP_AUTHORIZATION=f"Token {client_token.key}")
        client_point = CatchmentPoint.objects.create(
            title="Punto Cliente Resp", project=self.project, owner_user=client_user
        )
        ticket = _create_ticket_with_point(
            client_point,
            title="Ticket de cliente",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = client_api.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {"title": "Titulo editado por cliente"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.sla_responded_at)

    def test_status_change_from_cancelled_to_resolved_does_not_500(self):
        """Cambiar de CANCELADO a RESUELTO no debe fallar por timestamps inconsistentes."""
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket cancelado",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            status="CANCELADO",
        )
        # Simular inconsistencia: closed_at seteado estando CANCELADO
        ticket.closed_at = timezone.now()
        ticket.save(update_fields=["closed_at"])

        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "RESUELTO"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "RESUELTO")
        self.assertIsNone(ticket.closed_at)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class TicketSLAPauseTests(TestCase):
    """Tests de pausa/reanudación del reloj SLA en estados de espera."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="pausestaff@smarthydro.cl", password="pass", username="pausestaff", is_staff=True
        )
        self.client_obj = Client.objects.create(name="Cliente Pausa")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Pausa", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Pausa", project=self.project, owner_user=self.staff
        )
        self.cat = TicketCategory.objects.get(category_type="HARDWARE", name="Hardware")
        SLAConfig.objects.create(
            category=self.cat,
            priority="ALTA",
            response_time_hours=2,
            resolution_time_hours=8,
        )
        self.token = Token.objects.create(user=self.staff)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _ticket(self, **kwargs):
        defaults = dict(
            title="Ticket SLA pausa",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            status="ABIERTO",
            priority="ALTA",
            category=self.cat,
        )
        defaults.update(kwargs)
        return _create_ticket_with_point(self.point, **defaults)

    def test_status_change_to_espera_pauses_sla(self):
        from datetime import timedelta
        ticket = self._ticket(
            sla_deadline_response=timezone.now() + timedelta(hours=2),
            sla_deadline_resolution=timezone.now() + timedelta(hours=8),
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "ESPERA_CLIENTE"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "ESPERA_CLIENTE")
        self.assertIsNotNone(ticket.sla_paused_at)
        old_response = ticket.sla_deadline_response
        old_resolution = ticket.sla_deadline_resolution

        # La pausa no debe alterar los deadlines (el reloj queda congelado).
        ticket.refresh_from_db()
        self.assertEqual(ticket.sla_deadline_response, old_response)
        self.assertEqual(ticket.sla_deadline_resolution, old_resolution)

    def test_status_change_back_from_espera_extends_deadlines(self):
        from datetime import timedelta
        ticket = self._ticket(
            sla_deadline_response=timezone.now() + timedelta(hours=2),
            sla_deadline_resolution=timezone.now() + timedelta(hours=8),
        )
        self.client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "ESPERA_PROVEEDOR"},
            format="json",
        )
        ticket.refresh_from_db()
        paused_response = ticket.sla_deadline_response
        paused_resolution = ticket.sla_deadline_resolution

        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "EN_ANALISIS"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "EN_ANALISIS")
        self.assertIsNone(ticket.sla_paused_at)
        self.assertGreater(ticket.sla_deadline_response, paused_response)
        self.assertGreater(ticket.sla_deadline_resolution, paused_resolution)

    def test_comment_status_change_pauses_and_resumes(self):
        from datetime import timedelta
        ticket = self._ticket(
            sla_deadline_response=timezone.now() + timedelta(hours=2),
            sla_deadline_resolution=timezone.now() + timedelta(hours=8),
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "En espera de cliente", "status_change": "ESPERA_CLIENTE"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.sla_paused_at)
        paused_resolution = ticket.sla_deadline_resolution

        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "Respuesta del cliente", "status_change": "EN_ANALISIS"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.sla_paused_at)
        self.assertGreater(ticket.sla_deadline_resolution, paused_resolution)

    def test_patch_status_pauses_and_resumes(self):
        from datetime import timedelta
        ticket = self._ticket(
            sla_deadline_response=timezone.now() + timedelta(hours=2),
            sla_deadline_resolution=timezone.now() + timedelta(hours=8),
        )
        response = self.client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {"status": "ESPERA_CLIENTE"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.sla_paused_at)
        paused_resolution = ticket.sla_deadline_resolution

        response = self.client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {"status": "ABIERTO"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "ABIERTO")
        self.assertIsNone(ticket.sla_paused_at)
        self.assertGreater(ticket.sla_deadline_resolution, paused_resolution)

    def test_create_ticket_in_espera_pauses_sla(self):
        response = self.client.post(
            "/api/ik/tickets/",
            {
                "title": "Ticket creado en espera",
                "description": "...",
                "origin": "CLIENTE",
                "source": "APP_CLIENTE",
                "status": "ESPERA_CLIENTE",
                "priority": "ALTA",
                "category": self.cat.id,
                "points": [self.point.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "ESPERA_CLIENTE")
        self.assertIsNotNone(data["sla_paused_at"])
        self.assertIsNotNone(data["sla_deadline_resolution"])
        ticket = SupportTicket.objects.get(id=data["id"])
        self.assertIsNotNone(ticket.sla_paused_at)

    def test_notify_sla_overdue_skips_paused_tickets(self):
        from datetime import timedelta
        from django.core import mail
        self.operator = User.objects.create_user(
            email="pauseop@smarthydro.cl", password="pass", username="pauseop"
        )
        self.cat.operators.add(self.operator)
        ticket = self._ticket(
            status="ESPERA_CLIENTE",
            sla_deadline_resolution=timezone.now() - timedelta(hours=1),
            sla_deadline_response=timezone.now() - timedelta(hours=1),
            sla_paused_at=timezone.now() - timedelta(hours=2),
        )
        mail.outbox = []
        call_command("notify_sla_overdue", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)
        ticket.refresh_from_db()
        self.assertIsNone(ticket.sla_last_overdue_notification)

    def test_dashboard_excludes_paused_overdue(self):
        from datetime import timedelta
        overdue = timezone.now() - timedelta(hours=1)
        # Vencido en espera (pausado) → no cuenta como vencido
        self._ticket(
            status="ESPERA_CLIENTE",
            sla_deadline_resolution=overdue,
            sla_deadline_response=overdue,
            sla_paused_at=timezone.now() - timedelta(hours=2),
        )
        response = self.client.get("/api/ik/tickets/dashboard/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kpis"]["sla_resolution_overdue"], 0)
        self.assertEqual(data["kpis"]["sla_response_overdue"], 0)

        # Vencido sin pausa → sí cuenta
        self._ticket(
            status="ABIERTO",
            sla_deadline_resolution=overdue,
            sla_deadline_response=overdue,
        )
        response = self.client.get("/api/ik/tickets/dashboard/")
        data = response.json()
        self.assertEqual(data["kpis"]["sla_resolution_overdue"], 1)
        self.assertEqual(data["kpis"]["sla_response_overdue"], 1)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class TicketConvertToClientTests(TestCase):
    """Tests de conversión de tickets INTERNO -> CLIENTE."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="convertstaff@smarthydro.cl", password="pass", username="convertstaff", is_staff=True
        )
        self.client_user = User.objects.create_user(
            email="convertclient@smarthydro.cl", password="pass", username="convertclient"
        )
        self.client_obj = Client.objects.create(name="Cliente Convert")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Convert", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Convert", project=self.project, owner_user=self.client_user
        )
        self.cat = TicketCategory.objects.get(category_type="HARDWARE", name="Hardware")
        SLAConfig.objects.create(
            category=self.cat,
            priority="MEDIA",
            response_time_hours=4,
            resolution_time_hours=24,
        )
        self.token = Token.objects.create(user=self.staff)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_convert_internal_to_client_sets_sla(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Evento sistema",
            description="...",
            origin="INTERNO",
            source="SISTEMA",
            category=self.cat,
            priority="MEDIA",
        )
        self.assertIsNone(ticket.sla_deadline_response)

        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/convert-to-client/",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["origin"], "CLIENTE")

        ticket.refresh_from_db()
        self.assertEqual(ticket.origin, "CLIENTE")
        self.assertIsNotNone(ticket.sla_deadline_response)
        self.assertIsNotNone(ticket.sla_deadline_resolution)
        self.assertEqual(ticket.activity_logs.filter(field_name="origin").count(), 1)

    def test_convert_already_client_returns_ok(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket cliente",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/convert-to-client/",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("ya es de origen CLIENTE", response.json()["detail"])

    def test_convert_operations_rejected(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Ticket operaciones",
            description="...",
            origin="OPERACIONES",
            source="SISTEMA",
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/convert-to-client/",
        )
        self.assertEqual(response.status_code, 400)

    def test_convert_requires_staff(self):
        ticket = _create_ticket_with_point(
            self.point,
            title="Evento sistema",
            description="...",
            origin="INTERNO",
            source="SISTEMA",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=self.client_user).key}")
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/convert-to-client/",
        )
        self.assertEqual(response.status_code, 403)

    def test_convert_internal_to_client_without_point_with_client(self):
        """Convertir a CLIENTE es válido aunque el ticket no tenga punto con cliente."""
        no_client_project = ProjectCatchments.objects.create(name="Proyecto sin cliente")
        no_client_point = CatchmentPoint.objects.create(
            title="Punto sin cliente", project=no_client_project, owner_user=self.client_user
        )
        ticket = _create_ticket_with_point(
            no_client_point,
            title="Evento sin cliente",
            description="...",
            origin="INTERNO",
            source="SISTEMA",
            category=self.cat,
            priority="MEDIA",
        )
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/convert-to-client/",
        )
        self.assertEqual(response.status_code, 200)
        ticket.refresh_from_db()
        self.assertEqual(ticket.origin, "CLIENTE")


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class SLAConfigUpdateTests(TestCase):
    """Tests de edición parcial de SLA sin falsos duplicados."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="slapatch@smarthydro.cl", password="pass", username="slapatch", is_staff=True
        )
        self.cat = TicketCategory.objects.get(category_type="HARDWARE", name="Hardware")
        self.sla = SLAConfig.objects.create(
            category=self.cat,
            priority="ALTA",
            response_time_hours=2,
            resolution_time_hours=8,
        )
        # SLA global creada por migración 0068
        self.token = Token.objects.create(user=self.staff)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_patch_sla_time_does_not_trigger_duplicate_global(self):
        response = self.client.patch(
            f"/api/ik/sla-configs/{self.sla.id}/",
            {"response_time_hours": 4},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.sla.refresh_from_db()
        self.assertEqual(self.sla.response_time_hours, 4)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class CleanupStaleInternalTests(TestCase):
    """Tests del comando cleanup_stale_internal_tickets."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cleanup@smarthydro.cl", password="pass", username="cleanup"
        )

    def test_cleanup_does_not_set_closed_at_on_cancelled(self):
        from datetime import timedelta
        old_ticket = SupportTicket.objects.create(
            title="Ticket viejo",
            description="...",
            origin="INTERNO",
            source="SISTEMA",
            status="ABIERTO",
            is_active=True,
        )
        old_ticket.created = timezone.now() - timedelta(days=100)
        old_ticket.save(update_fields=["created"])

        call_command("cleanup_stale_internal_tickets", stdout=StringIO())
        old_ticket.refresh_from_db()
        self.assertEqual(old_ticket.status, "CANCELADO")
        self.assertFalse(old_ticket.is_active)
        self.assertIsNone(old_ticket.closed_at)

    def test_cleanup_rejects_negative_days(self):
        out = StringIO()
        call_command("cleanup_stale_internal_tickets", days=-1, stdout=out)
        self.assertIn("debe ser un número positivo", out.getvalue())


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotifySLAOverdueFixTests(TestCase):
    """Tests adicionales del comando notify_sla_overdue."""

    def setUp(self):
        self.operator = User.objects.create_user(
            email="slaop2@smarthydro.cl", password="pass", username="slaop2"
        )
        self.user = User.objects.create_user(
            email="slauser2@smarthydro.cl", password="pass", username="slauser2"
        )
        self.client_obj = Client.objects.create(name="Cliente SLA2")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto SLA2", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto SLA2", project=self.project, owner_user=self.user
        )
        self.cat = TicketCategory.objects.get(category_type="HARDWARE", name="Hardware")
        self.cat.operators.add(self.operator)

    def test_does_not_notify_already_resolved_ticket(self):
        ticket = SupportTicket.objects.create(
            title="Ticket ya resuelto",
            description="...",
            status="ABIERTO",
            priority="ALTA",
            category=self.cat,
            origin="CLIENTE",
            source="APP_CLIENTE",
            sla_deadline_resolution=timezone.now() - timezone.timedelta(hours=1),
            sla_resolved_at=timezone.now() - timezone.timedelta(minutes=30),
        )
        ticket.points.add(self.point)

        from django.core import mail
        mail.outbox = []
        call_command("notify_sla_overdue", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_dry_run_does_not_update_timestamp(self):
        ticket = SupportTicket.objects.create(
            title="Ticket dry run",
            description="...",
            status="ABIERTO",
            priority="ALTA",
            category=self.cat,
            origin="CLIENTE",
            source="APP_CLIENTE",
            sla_deadline_resolution=timezone.now() - timezone.timedelta(hours=1),
        )
        ticket.points.add(self.point)

        call_command("notify_sla_overdue", dry_run=True, stdout=StringIO())
        ticket.refresh_from_db()
        self.assertIsNone(ticket.sla_last_overdue_notification)


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
class TicketDashboardTests(TestCase):
    """Tests del dashboard unificado de soporte."""

    def setUp(self):
        self.staff = User.objects.create_user(
            email="dashstaff@smarthydro.cl", password="pass", username="dashstaff", is_staff=True
        )
        self.client_user = User.objects.create_user(
            email="dashclient@smarthydro.cl", password="pass", username="dashclient"
        )
        self.client_obj = Client.objects.create(name="Cliente Dashboard")
        self.project = ProjectCatchments.objects.create(
            name="Proyecto Dashboard", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Punto Dashboard", project=self.project, owner_user=self.client_user
        )
        self.cat_software = TicketCategory.objects.get(category_type="SOFTWARE", name="Software")
        self.cat_work_order = TicketCategory.objects.get(category_type="WORK_ORDER", name="Orden de Trabajo")
        self.token = Token.objects.create(user=self.staff)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_dashboard_returns_kpis_and_charts(self):
        _create_ticket_with_point(
            self.point,
            title="Ticket abierto",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            status="ABIERTO",
            priority="ALTA",
            category=self.cat_software,
        )
        _create_ticket_with_point(
            self.point,
            title="Ticket orden de trabajo",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            status="EN_ORDEN_TRABAJO",
            priority="MEDIA",
            category=self.cat_work_order,
            scheduled_date="2026-07-15",
        )

        response = self.client.get("/api/ik/tickets/dashboard/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("kpis", data)
        self.assertIn("charts", data)
        self.assertIn("tables", data)
        self.assertEqual(data["kpis"]["tickets"], 2)
        self.assertEqual(data["kpis"]["active_tickets"], 1)
        self.assertEqual(data["charts"]["by_status"]["ABIERTO"], 1)
        self.assertEqual(data["charts"]["by_status"]["EN_ORDEN_TRABAJO"], 1)
        self.assertEqual(data["charts"]["by_category_type"]["WORK_ORDER"], 1)
        self.assertEqual(data["kpis"]["work_orders_total"], 1)
        self.assertEqual(data["kpis"]["work_orders_with_visit"], 1)

    def test_dashboard_ignores_interno_tickets(self):
        # Los tickets INTERNO (alertas automáticas del sistema) no deben
        # aparecer en el dashboard de soporte: inundan los charts.
        _create_ticket_with_point(
            self.point,
            title="Alerta automatica sistema",
            description="...",
            origin="INTERNO",
            source="SISTEMA",
            status="ABIERTO",
        )
        _create_ticket_with_point(
            self.point,
            title="Alerta automatica regla",
            description="...",
            origin="INTERNO",
            source="ALERTA_AUTO",
            status="ABIERTO",
        )
        _create_ticket_with_point(
            self.point,
            title="Ticket soporte",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            status="ABIERTO",
        )

        response = self.client.get("/api/ik/tickets/dashboard/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kpis"]["tickets"], 1)
        self.assertNotIn("INTERNO", data["charts"]["by_origin"])
        self.assertEqual(data["charts"]["by_origin"]["CLIENTE"], 1)
        self.assertEqual(data["charts"]["by_status"]["ABIERTO"], 1)
        self.assertEqual(sum(data["charts"]["by_origin"].values()), 1)

    def test_dashboard_only_counts_cliente_origin(self):
        # El SLA de soporte considera solo tickets CLIENTE: OPERACIONES e
        # INTERNO no deben contar en KPIs ni charts.
        _create_ticket_with_point(
            self.point,
            title="OT operaciones",
            description="...",
            origin="OPERACIONES",
            source="APP_ADMIN",
            status="ABIERTO",
        )
        _create_ticket_with_point(
            self.point,
            title="Ticket cliente",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            status="ABIERTO",
        )

        response = self.client.get("/api/ik/tickets/dashboard/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kpis"]["tickets"], 1)
        self.assertNotIn("OPERACIONES", data["charts"]["by_origin"])
        self.assertEqual(data["charts"]["by_origin"]["CLIENTE"], 1)

    def test_dashboard_charts_count_multiple_tickets_per_status(self):
        # Regresión: con Meta.ordering='-created' + distinct(), `created` se
        # colaba al GROUP BY y cada estado/prioridad contaba 1 aunque hubiera
        # varios tickets. Verifica que los charts sumen el total del KPI.
        for i in range(3):
            t = _create_ticket_with_point(
                self.point,
                title=f"Ticket RESUELTO {i}",
                description="...",
                origin="CLIENTE",
                source="APP_CLIENTE",
                status="RESUELTO",
                priority="BAJA",
                category=self.cat_software,
            )
            t.created = timezone.now() - timezone.timedelta(days=i, hours=i)
            t.save(update_fields=["created"])

        response = self.client.get("/api/ik/tickets/dashboard/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kpis"]["tickets"], 3)
        self.assertEqual(data["charts"]["by_status"]["RESUELTO"], 3)
        self.assertEqual(data["charts"]["by_priority"]["BAJA"], 3)
        self.assertEqual(sum(data["charts"]["by_status"].values()), 3)
        self.assertEqual(sum(data["charts"]["by_priority"].values()), 3)

    def test_stats_compliance_by_status_sums_to_total(self):
        # Regresión: en /stats/, `compliance_qs` tiene .distinct() y con
        # Meta.ordering='-created' el ORDER BY se colaba al GROUP BY, contando
        # 1 por grupo. compliance.by_status debe sumar compliance.total.
        cat_compliance = TicketCategory.objects.get(
            category_type="COMPLIANCE", name="Cumplimiento DGA"
        )
        for i in range(2):
            t = _create_ticket_with_point(
                self.point,
                title=f"Compliance {i}",
                description="...",
                origin="CLIENTE",
                source="APP_CLIENTE",
                status="RESUELTO",
                priority="ALTA",
                category=cat_compliance,
            )
            t.created = timezone.now() - timezone.timedelta(days=i)
            t.save(update_fields=["created"])

        response = self.client.get("/api/ik/tickets/stats/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["compliance"]["total"], 2)
        self.assertEqual(data["compliance"]["by_status"]["RESUELTO"], 2)
        self.assertEqual(sum(data["compliance"]["by_status"].values()), data["compliance"]["total"])

    def test_ranking_by_resolved_assigned_created(self):
        resolver = User.objects.create_user(
            email="resolver@smarthydro.cl", password="pass", username="resolver",
            first_name="Soporte", last_name="Uno",
        )
        assigned = User.objects.create_user(
            email="asignado@smarthydro.cl", password="pass", username="asignado",
            first_name="Asignado", last_name="Dos",
        )
        creator = User.objects.create_user(
            email="creador@smarthydro.cl", password="pass", username="creador",
            first_name="Creador", last_name="Tres",
        )

        for i in range(2):
            t = _create_ticket_with_point(
                self.point,
                title=f"Resuelto {i}",
                description="...",
                origin="CLIENTE",
                source="APP_CLIENTE",
                status="RESUELTO",
                priority="MEDIA",
                category=self.cat_software,
                created_by=creator,
                assigned_to=assigned,
            )
            TicketActivityLog.objects.create(
                ticket=t, user=resolver, field_name="status",
                old_value="EN_ANALISIS", new_value="RESUELTO",
            )

        t2 = _create_ticket_with_point(
            self.point,
            title="Cerrado directo",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            status="CERRADO",
            priority="BAJA",
            category=self.cat_software,
            created_by=creator,
            assigned_to=assigned,
        )
        TicketActivityLog.objects.create(
            ticket=t2, user=resolver, field_name="status",
            old_value="EN_ORDEN_TRABAJO", new_value="CERRADO",
        )

        response = self.client.get("/api/ik/tickets/ranking/")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        by_resolved = {r["user_id"]: r["total"] for r in data["by_resolved"]}
        self.assertEqual(by_resolved[resolver.id], 3)
        self.assertEqual(sum(r["total"] for r in data["by_resolved"]), 3)
        entry = next(r for r in data["by_resolved"] if r["user_id"] == resolver.id)
        self.assertEqual(entry["name"], "Soporte Uno")

        by_assigned = {r["user_id"]: r["total"] for r in data["by_assigned"]}
        self.assertEqual(by_assigned[assigned.id], 3)

        by_created = {r["user_id"]: r["total"] for r in data["by_created"]}
        self.assertEqual(by_created[creator.id], 3)

    def test_ranking_ignores_interno_and_operaciones(self):
        resolver = User.objects.create_user(
            email="resolver2@smarthydro.cl", password="pass", username="resolver2",
            first_name="Soporte", last_name="Dos",
        )
        _create_ticket_with_point(
            self.point,
            title="Alerta sistema",
            description="...",
            origin="INTERNO",
            source="SISTEMA",
            status="RESUELTO",
            category=self.cat_software,
            created_by=resolver,
            assigned_to=resolver,
        )
        _create_ticket_with_point(
            self.point,
            title="OT operaciones",
            description="...",
            origin="OPERACIONES",
            source="APP_ADMIN",
            status="RESUELTO",
            category=self.cat_software,
            created_by=resolver,
            assigned_to=resolver,
        )

        response = self.client.get("/api/ik/tickets/ranking/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["by_resolved"], [])
        self.assertEqual(data["by_assigned"], [])
        self.assertEqual(data["by_created"], [])

    def test_ranking_sla_overdue_by_person(self):
        user_a = User.objects.create_user(
            email="sla_a@smarthydro.cl", password="pass", username="sla_a",
            first_name="Sla", last_name="A",
        )
        user_b = User.objects.create_user(
            email="sla_b@smarthydro.cl", password="pass", username="sla_b",
            first_name="Sla", last_name="B",
        )
        overdue_res = timezone.now() - timezone.timedelta(days=5)
        overdue_resp = timezone.now() - timezone.timedelta(days=3)

        for i in range(2):
            _create_ticket_with_point(
                self.point,
                title=f"SLA res vencido A {i}",
                description="...",
                origin="CLIENTE",
                source="APP_CLIENTE",
                status="EN_ANALISIS",
                priority="ALTA",
                category=self.cat_software,
                assigned_to=user_a,
                sla_deadline_resolution=overdue_res,
                sla_deadline_response=overdue_resp,
            )
        _create_ticket_with_point(
            self.point,
            title="SLA res vencido B",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            status="EN_ANALISIS",
            priority="ALTA",
            category=self.cat_software,
            assigned_to=user_b,
            sla_deadline_resolution=overdue_res,
        )
        # Vencido sin asignar: no debe sumar a nadie
        _create_ticket_with_point(
            self.point,
            title="SLA vencido sin asignar",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            status="EN_ANALISIS",
            priority="ALTA",
            category=self.cat_software,
            sla_deadline_resolution=overdue_res,
            sla_deadline_response=overdue_resp,
        )
        # Vencido pero ya resuelto: no cuenta
        _create_ticket_with_point(
            self.point,
            title="SLA vencido resuelto",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            status="RESUELTO",
            priority="ALTA",
            category=self.cat_software,
            assigned_to=user_a,
            sla_deadline_resolution=overdue_res,
            sla_resolved_at=timezone.now(),
        )

        response = self.client.get("/api/ik/tickets/ranking/")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        by_res = {r["user_id"]: r["total"] for r in data["by_sla_resolution_overdue"]}
        self.assertEqual(by_res[user_a.id], 2)
        self.assertEqual(by_res[user_b.id], 1)
        self.assertEqual(sum(r["total"] for r in data["by_sla_resolution_overdue"]), 3)

        by_resp = {r["user_id"]: r["total"] for r in data["by_sla_response_overdue"]}
        self.assertEqual(by_resp[user_a.id], 2)
        self.assertEqual(sum(r["total"] for r in data["by_sla_response_overdue"]), 2)

    def test_dashboard_filters_by_assigned_to(self):
        _create_ticket_with_point(
            self.point,
            title="Asignado a staff",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            assigned_to=self.staff,
        )
        _create_ticket_with_point(
            self.point,
            title="Sin asignar",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )

        response = self.client.get(f"/api/ik/tickets/dashboard/?assigned_to={self.staff.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kpis"]["tickets"], 1)

    def test_dashboard_sla_overdue_tables(self):
        from datetime import timedelta
        _create_ticket_with_point(
            self.point,
            title="SLA vencido",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            status="ABIERTO",
            priority="CRITICA",
            category=self.cat_software,
            sla_deadline_resolution=timezone.now() - timedelta(hours=2),
        )

        response = self.client.get("/api/ik/tickets/dashboard/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kpis"]["sla_resolution_overdue"], 1)
        self.assertEqual(len(data["tables"]["sla_resolution_overdue"]), 1)
        self.assertEqual(data["tables"]["sla_resolution_overdue"][0]["priority"], "CRITICA")

    def test_dashboard_excludes_terminal_statuses_from_sla_overdue(self):
        from datetime import timedelta
        past = timezone.now() - timedelta(days=5)
        _create_ticket_with_point(
            self.point,
            title="Resuelto con SLA vencido",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            status="RESUELTO",
            priority="CRITICA",
            category=self.cat_software,
            sla_deadline_resolution=past,
            sla_deadline_response=past,
            sla_responded_at=None,
            sla_resolved_at=None,
        )
        _create_ticket_with_point(
            self.point,
            title="Abierto con SLA vencido",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            status="ABIERTO",
            priority="CRITICA",
            category=self.cat_software,
            sla_deadline_resolution=past,
            sla_deadline_response=past,
            sla_responded_at=None,
            sla_resolved_at=None,
        )

        response = self.client.get("/api/ik/tickets/dashboard/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kpis"]["sla_resolution_overdue"], 1)
        self.assertEqual(data["kpis"]["sla_response_overdue"], 1)
        self.assertEqual(len(data["tables"]["sla_resolution_overdue"]), 1)
        self.assertEqual(len(data["tables"]["sla_response_overdue"]), 1)
        self.assertEqual(data["tables"]["sla_resolution_overdue"][0]["title"], "Abierto con SLA vencido")

    def test_dashboard_invalid_date_filter_returns_400(self):
        response = self.client.get("/api/ik/tickets/dashboard/?created_at__gte=mal")
        self.assertEqual(response.status_code, 400)


class TicketAssignmentEmailNotificationTests(TestCase):
    """Correos al asignar/reasignar tickets (asignado + operadores + creador, sin el actor)."""

    def setUp(self):
        self.assigner = User.objects.create_user(
            email="assigner@smarthydro.cl", password="pass", username="assigner", is_staff=True
        )
        self.assignee = User.objects.create_user(
            email="assignee@smarthydro.cl", password="pass", username="assignee", is_staff=True
        )
        self.creator = User.objects.create_user(
            email="creator@smarthydro.cl", password="pass", username="creator"
        )
        self.operator = User.objects.create_user(
            email="operator@smarthydro.cl", password="pass", username="operator", is_staff=True
        )
        self.client_obj = Client.objects.create(name="Cliente Asig")
        self.project = ProjectCatchments.objects.create(name="Proyecto Asig", client=self.client_obj)
        self.point = CatchmentPoint.objects.create(
            title="Punto Asig", project=self.project, owner_user=self.creator
        )
        self.cat = TicketCategory.objects.get(category_type="HARDWARE", name="Telemetría")
        self.cat.operators.add(self.operator)
        self.token = Token.objects.create(user=self.assigner)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _ticket(self, **kwargs):
        defaults = dict(
            title="Ticket asignación",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            category=self.cat,
            created_by=self.creator,
        )
        defaults.update(kwargs)
        return _create_ticket_with_point(self.point, **defaults)

    def test_assign_sends_email_to_assignee_creator_and_operators(self):
        from django.core import mail
        ticket = self._ticket()
        mail.outbox = []
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/assign/",
            {"assigned_to": self.assignee.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        recipients = set(mail.outbox[0].to)
        self.assertIn(self.assignee.email, recipients)
        self.assertIn(self.creator.email, recipients)
        self.assertIn(self.operator.email, recipients)
        self.assertNotIn(self.assigner.email, recipients)
        self.assertIn("asign", mail.outbox[0].subject.lower())

    def test_assign_no_email_when_notify_email_false(self):
        from django.core import mail
        self.assignee.notify_email = False
        self.assignee.save()
        ticket = self._ticket()
        mail.outbox = []
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/assign/",
            {"assigned_to": self.assignee.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        recipients = set(mail.outbox[0].to)
        self.assertNotIn(self.assignee.email, recipients)
        self.assertIn(self.creator.email, recipients)

    def test_reassign_to_same_user_no_email(self):
        from django.core import mail
        ticket = self._ticket(assigned_to=self.assignee)
        mail.outbox = []
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/assign/",
            {"assigned_to": self.assignee.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_patch_assigned_to_sends_email(self):
        from django.core import mail
        ticket = self._ticket()
        mail.outbox = []
        response = self.client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {"assigned_to": self.assignee.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.assignee.email, mail.outbox[0].to)


class TicketStatusEmailNotificationTests(TestCase):
    """Correos al cambiar el estado de un ticket (involucrados, sin el actor)."""

    def setUp(self):
        self.actor = User.objects.create_user(
            email="statactor@smarthydro.cl", password="pass", username="statactor", is_staff=True
        )
        self.assignee = User.objects.create_user(
            email="statassignee@smarthydro.cl", password="pass", username="statassignee", is_staff=True
        )
        self.creator = User.objects.create_user(
            email="statcreator@smarthydro.cl", password="pass", username="statcreator"
        )
        self.operator = User.objects.create_user(
            email="statoperator@smarthydro.cl", password="pass", username="statoperator", is_staff=True
        )
        self.client_obj = Client.objects.create(name="Cliente Estado")
        self.project = ProjectCatchments.objects.create(name="Proyecto Estado", client=self.client_obj)
        self.point = CatchmentPoint.objects.create(
            title="Punto Estado", project=self.project, owner_user=self.creator
        )
        self.cat = TicketCategory.objects.get(category_type="HARDWARE", name="Telemetría")
        self.cat.operators.add(self.operator)
        self.token = Token.objects.create(user=self.actor)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _ticket(self, **kwargs):
        defaults = dict(
            title="Ticket estado",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
            category=self.cat,
            created_by=self.creator,
            assigned_to=self.assignee,
        )
        defaults.update(kwargs)
        return _create_ticket_with_point(self.point, **defaults)

    def test_status_endpoint_sends_email_to_involved(self):
        from django.core import mail
        ticket = self._ticket()
        mail.outbox = []
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "EN_ANALISIS"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        recipients = set(mail.outbox[0].to)
        self.assertIn(self.assignee.email, recipients)
        self.assertIn(self.creator.email, recipients)
        self.assertIn(self.operator.email, recipients)
        self.assertNotIn(self.actor.email, recipients)
        self.assertIn("cambió", mail.outbox[0].subject)

    def test_status_change_via_comment_sends_email(self):
        from django.core import mail
        ticket = self._ticket()
        mail.outbox = []
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/comments/",
            {"content": "cambio estado", "status_change": "EN_ANALISIS"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("cambió", mail.outbox[0].subject)

    def test_status_change_via_patch_sends_email(self):
        from django.core import mail
        ticket = self._ticket()
        mail.outbox = []
        response = self.client.patch(
            f"/api/ik/tickets/{ticket.id}/",
            {"status": "RESUELTO"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        recipients = set(mail.outbox[0].to)
        self.assertIn(self.assignee.email, recipients)
        self.assertIn(self.creator.email, recipients)

    def test_same_status_no_email(self):
        from django.core import mail
        ticket = self._ticket(status="EN_ANALISIS")
        mail.outbox = []
        response = self.client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "EN_ANALISIS"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_status_notify_email_false_respected(self):
        from django.core import mail
        self.assignee.notify_email = False
        self.assignee.save()
        ticket = self._ticket()
        mail.outbox = []
        self.client.post(
            f"/api/ik/tickets/{ticket.id}/status/",
            {"status": "EN_ANALISIS"},
            format="json",
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(self.assignee.email, mail.outbox[0].to)
