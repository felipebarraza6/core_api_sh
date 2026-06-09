"""
Tests de regresión para el subsistema de Tickets de Soporte + SLA.
"""

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.core.models import (
    Client, ProjectCatchments, CatchmentPoint, SLAConfig,
    SupportTicket, TicketComment, TicketActivityLog,
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

    def test_create_support_ticket(self):
        ticket = SupportTicket.objects.create(
            point_catchment=self.point,
            title="No hay datos",
            description="El punto lleva 2 horas sin datos",
            created_by=self.user,
            status="ABIERTO",
            priority="ALTA",
            category="CONECTIVIDAD",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        self.assertEqual(ticket.status, "ABIERTO")
        self.assertEqual(ticket.origin, "CLIENTE")
        self.assertEqual(ticket.point_catchment, self.point)

    def test_sla_config_matching(self):
        sla = SLAConfig.objects.create(
            client=self.client_obj,
            category="CONECTIVIDAD",
            priority="ALTA",
            response_time_hours=2,
            resolution_time_hours=8,
        )
        ticket = SupportTicket.objects.create(
            point_catchment=self.point,
            title="Falla",
            description="...",
            priority="ALTA",
            category="CONECTIVIDAD",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        from api.api_ik.views_tickets import _find_sla_config
        matched = _find_sla_config(ticket)
        self.assertIsNotNone(matched)
        self.assertEqual(matched.response_time_hours, 2)

    def test_comment_internal_hidden(self):
        ticket = SupportTicket.objects.create(
            point_catchment=self.point,
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
        ticket = SupportTicket.objects.create(
            point_catchment=self.point,
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

    def test_alert_trigger_creates_ticket(self):
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
            notification_sent=True,
        )
        ticket = SupportTicket.objects.filter(alert_trigger=trigger).first()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.category, "CONECTIVIDAD")
        self.assertEqual(ticket.origin, "INTERNO")
        self.assertEqual(ticket.source, "ALERTA_AUTO")

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


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
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
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_create_ticket_via_api(self):
        response = self.client.post(
            "/api/ik/tickets/",
            {
                "point_catchment": self.point.id,
                "title": "Falla API",
                "description": "Desde test",
                "category": "TELEMETRIA",
                "priority": "MEDIA",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Falla API")
        self.assertEqual(data["status"], "ABIERTO")

    def test_list_tickets_via_api(self):
        SupportTicket.objects.create(
            point_catchment=self.point,
            title="Ticket 1",
            description="...",
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.get("/api/ik/tickets/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)

    def test_change_status_via_api(self):
        ticket = SupportTicket.objects.create(
            point_catchment=self.point,
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
        ticket = SupportTicket.objects.create(
            point_catchment=self.point,
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

    def test_ticket_stats_via_api(self):
        SupportTicket.objects.create(
            point_catchment=self.point,
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
        """point_id no numérico debe retornar 400, no 500."""
        response = self.client.post(
            "/api/ik/tickets/",
            {
                "point_catchment": "not-an-id",
                "title": "Falla",
                "description": "...",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("point_id", response.json().get("error", "").lower())

    def test_assign_ticket_invalid_user(self):
        """Asignar a usuario inexistente debe retornar 400, no 500."""
        ticket = SupportTicket.objects.create(
            point_catchment=self.point,
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

    def test_upload_attachment_invalid_extension(self):
        """Subir archivo con extensión inválida debe retornar 400."""
        ticket = SupportTicket.objects.create(
            point_catchment=self.point,
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
