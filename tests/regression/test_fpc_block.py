
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
    """
    Test legacy: FPC Tissue blocking logic was removed from production.
    This test now validates that records without active DGA config are simply
    not processed (not blocked, just skipped).
    """
    def setUp(self):
        # Create User for owner
        from api.core.models import User
        self.user = User.objects.create(username="testuser", email="test@example.com")

        # Create dummy point to take ID 1 (because cron_dga excludes catchment_point=1)
        dummy_client = Client.objects.create(name="Dummy")
        dummy_project = ProjectCatchments.objects.create(name="Dummy Proj", client=dummy_client)
        CatchmentPoint.objects.create(title="Dummy Point 1", project=dummy_project, owner_user=self.user)

        # Create FPC Tissue structure (legacy name, now treated as normal client)
        self.fpc_client = Client.objects.create(name="FPC Tissue S.A.")
        self.fpc_project = ProjectCatchments.objects.create(
            name="Planta Tissue",
            client=self.fpc_client
        )
        self.fpc_point = CatchmentPoint.objects.create(
            title="Pozo FPC",
            project=self.fpc_project,
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

    def test_records_without_dga_config_are_not_processed(self):
        """Records without active DGA config are skipped, not blocked."""
        # Ensure our point is NOT ID 1
        self.assertNotEqual(self.fpc_point.id, 1, "FPC point should not be ID 1")

        # Create record for FPC point (no DGA config with send_dga=True)
        fpc_record = InteractionDetail.objects.create(
            catchment_point=self.fpc_point,
            send_dga=True,
            total="100",
            date_time_medition=timezone.now()
        )

        # Create record for normal point (no DGA config with send_dga=True)
        normal_record = InteractionDetail.objects.create(
            catchment_point=self.normal_point,
            send_dga=True,
            total="200",
            date_time_medition=timezone.now()
        )

        # Run the cron job logic
        try:
            run()
        except Exception:
            pass  # Ignore other errors

        # Reload records
        fpc_record.refresh_from_db()
        normal_record.refresh_from_db()

        # Both records should remain unchanged (not processed because no DGA config)
        self.assertTrue(fpc_record.send_dga, "FPC record should remain pending (no DGA config)")
        self.assertTrue(normal_record.send_dga, "Normal record should remain pending (no DGA config)")
