# Migration to add DGA and status fields to TelemetryRecordV3
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0029_alter_alertrule_created_alter_alertrule_modified_and_more'),
    ]

    operations = [
        # Add DGA fields to TelemetryRecordV3
        migrations.RunSQL(
            sql="""
            ALTER TABLE core_telemetryrecordv3
            ADD COLUMN IF NOT EXISTS send_dga BOOLEAN DEFAULT FALSE;

            ALTER TABLE core_telemetryrecordv3
            ADD COLUMN IF NOT EXISTS n_voucher VARCHAR(200);

            ALTER TABLE core_telemetryrecordv3
            ADD COLUMN IF NOT EXISTS return_dga TEXT;

            ALTER TABLE core_telemetryrecordv3
            ADD COLUMN IF NOT EXISTS is_error BOOLEAN DEFAULT FALSE;

            ALTER TABLE core_telemetryrecordv3
            ADD COLUMN IF NOT EXISTS is_partial BOOLEAN DEFAULT FALSE;

            -- Add indexes for performance
            CREATE INDEX IF NOT EXISTS idx_telemetryv3_send_dga
            ON core_telemetryrecordv3(send_dga);

            CREATE INDEX IF NOT EXISTS idx_telemetryv3_n_voucher
            ON core_telemetryrecordv3(n_voucher);

            CREATE INDEX IF NOT EXISTS idx_telemetryv3_is_error
            ON core_telemetryrecordv3(is_error);

            CREATE INDEX IF NOT EXISTS idx_telemetryv3_is_partial
            ON core_telemetryrecordv3(is_partial);
            """,
            reverse_sql="""
            ALTER TABLE core_telemetryrecordv3 DROP COLUMN IF EXISTS send_dga;
            ALTER TABLE core_telemetryrecordv3 DROP COLUMN IF EXISTS n_voucher;
            ALTER TABLE core_telemetryrecordv3 DROP COLUMN IF EXISTS return_dga;
            ALTER TABLE core_telemetryrecordv3 DROP COLUMN IF EXISTS is_error;
            ALTER TABLE core_telemetryrecordv3 DROP COLUMN IF EXISTS is_partial;

            DROP INDEX IF EXISTS idx_telemetryv3_send_dga;
            DROP INDEX IF EXISTS idx_telemetryv3_n_voucher;
            DROP INDEX IF EXISTS idx_telemetryv3_is_error;
            DROP INDEX IF EXISTS idx_telemetryv3_is_partial;
            """
        ),
    ]
