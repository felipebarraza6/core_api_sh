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
                "scheduled_date": "2026-07-15",
                "visit_report": "Se reemplazó el sensor. Quedó operativo.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "EN_ORDEN_TRABAJO")
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

    def test_my_desk_filter_by_parent_category_includes_subcategories(self):
        """Filtrar my_desk por categoria padre incluye tickets de subcategorias."""
        sub_cat = TicketCategory.objects.create(
            category_type="SOFTWARE",
            name="Sub Software",
            parent=self.cat_software,
        )
        sub_cat.operators.add(self.operator)
        _create_ticket_with_point(
            self.point,
            title="Ticket subcategoria escritorio",
            description="...",
            category=sub_cat,
            origin="CLIENTE",
            source="APP_CLIENTE",
        )
        response = self.client.get(f"/api/ik/tickets/my_desk/?category={self.cat_software.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        titles = {r["title"] for r in data["results"]}
        self.assertIn("Ticket subcategoria escritorio", titles)


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

    def test_dashboard_invalid_date_filter_returns_400(self):
        response = self.client.get("/api/ik/tickets/dashboard/?created_at__gte=mal")
        self.assertEqual(response.status_code, 400)
