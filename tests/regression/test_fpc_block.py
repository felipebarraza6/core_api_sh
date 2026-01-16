
from django.test import TestCase
from django.utils import timezone
from api.core.models import (
    InteractionDetail,
    CatchmentPoint,
    Client,
    ProjectCatchments
)
from api.cronjobs.dga.cron_dga import run

class FPCTissueBlockTest(TestCase):
    def setUp(self):
        # Create User for owner
        from api.core.models import User
        self.user = User.objects.create(username="testuser", email="test@example.com")

        # Create dummy point to take ID 1 (because cron_dga excludes catchment_point=1)
        # We need projects and clients for integrity if strict, but let's try minimum
        dummy_client = Client.objects.create(name="Dummy")
        dummy_project = ProjectCatchments.objects.create(name="Dummy Proj", client=dummy_client)
        CatchmentPoint.objects.create(title="Dummy Point 1", project=dummy_project, owner_user=self.user)

        # Create FPC Tissue structure
        self.blocked_client = Client.objects.create(name="FPC Tissue S.A.")
        self.blocked_project = ProjectCatchments.objects.create(
            name="Planta Tissue", 
            client=self.blocked_client 
        )
        self.blocked_point = CatchmentPoint.objects.create(
            title="Pozo Bloqueado",
            project=self.blocked_project,
            owner_user=self.user
        )

        # Create Normal Client
        self.normal_client = Client.objects.create(name="Cliente Normal")
        self.normal_project = ProjectCatchments.objects.create(
            name="Proyecto Normal", 
            client=self.normal_client 
        )
        self.normal_point = CatchmentPoint.objects.create(
            title="Pozo Normal",
            project=self.normal_project,
            owner_user=self.user
        )

    def test_fpc_tissue_is_blocked(self):
        """Test that FPC Tissue records are blocked and marked with error."""
        # Ensure our point is NOT ID 1
        self.assertNotEqual(self.blocked_point.id, 1, "Blocked point should not be ID 1")

        # Create record for blocked client
        blocked_record = InteractionDetail.objects.create(
            catchment_point=self.blocked_point,
            send_dga=True,
            total="100",
            date_time_medition=timezone.now()
        )
        
        # Create record for normal client
        normal_record = InteractionDetail.objects.create(
            catchment_point=self.normal_point,
            send_dga=True,
            total="200",
            date_time_medition=timezone.now()
        )

        # Run the cron job logic
        try:
            run()
        except Exception as e:
            pass # Ignore other errors
        
        # Reload records
        blocked_record.refresh_from_db()
        normal_record.refresh_from_db()

        # Check Blocked Record
        self.assertFalse(blocked_record.send_dga, "Should mark send_dga=False")
        self.assertTrue(blocked_record.is_error, "Should mark is_error=True")
        self.assertIn("FPC Tissue", str(blocked_record.return_dga))
        
        # Check Normal Record
        # Logic: If it passed the block, it might have failed later (e.g. no DGA config), which is expected.
        # But it should NOT have "Cliente Bloqueado" error.
        if normal_record.return_dga:
            self.assertNotIn("FPC Tissue", normal_record.return_dga)

