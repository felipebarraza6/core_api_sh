"""
Management command to apply critical database optimizations
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Apply critical database optimizations for telemetry performance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without executing',
        )
        parser.add_argument(
            '--indexes-only',
            action='store_true',
            help='Only create missing indexes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        indexes_only = options['indexes_only']

        self.stdout.write(
            self.style.WARNING('🚀 Starting database optimization...')
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('🔍 DRY RUN - No changes will be made')
            )

        try:
            with connection.cursor() as cursor:
                # Check current indexes
                self.stdout.write('📊 Checking existing indexes...')
                cursor.execute("""
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename = 'core_interactiondetail'
                    ORDER BY indexname;
                """)

                existing_indexes = {row[0]: row[1] for row in cursor.fetchall()}

                # Critical indexes to create
                critical_indexes = {
                    'idx_interaction_error_date_desc': """
                        CREATE INDEX CONCURRENTLY idx_interaction_error_date_desc
                        ON core_interactiondetail (is_error, date_time_medition DESC)
                        WHERE is_error = true;
                    """,
                    'idx_interaction_dga_date_desc': """
                        CREATE INDEX CONCURRENTLY idx_interaction_dga_date_desc
                        ON core_interactiondetail (send_dga, date_time_medition DESC)
                        WHERE send_dga = true;
                    """,
                    'idx_catchment_frecuency': """
                        CREATE INDEX CONCURRENTLY idx_catchment_frecuency
                        ON core_catchmentpoint (frecuency)
                        WHERE frecuency IN ('1', '5');
                    """,
                    'idx_interaction_point_error_date': """
                        CREATE INDEX CONCURRENTLY idx_interaction_point_error_date
                        ON core_interactiondetail (catchment_point_id, is_error, date_time_medition);
                    """,
                    'idx_profile_telemetry_active': """
                        CREATE INDEX CONCURRENTLY idx_profile_telemetry_active
                        ON core_profiledataconfigcatchment (point_catchment, is_telemetry)
                        WHERE is_telemetry = true;
                    """,
                    'idx_dga_config_active': """
                        CREATE INDEX CONCURRENTLY idx_dga_config_active
                        ON core_dgadataconfigcatchment (point_catchment, send_dga)
                        WHERE send_dga = true;
                    """
                }

                # Create missing indexes
                created_count = 0
                for index_name, create_sql in critical_indexes.items():
                    if index_name not in existing_indexes:
                        if dry_run:
                            self.stdout.write(
                                self.style.SUCCESS(f'📝 Would create index: {index_name}')
                            )
                        else:
                            try:
                                cursor.execute(create_sql)
                                created_count += 1
                                self.stdout.write(
                                    self.style.SUCCESS(f'✅ Created index: {index_name}')
                                )
                            except Exception as e:
                                self.stdout.write(
                                    self.style.ERROR(f'❌ Failed to create {index_name}: {e}')
                                )
                    else:
                        self.stdout.write(
                            self.style.WARNING(f'⚠️  Index already exists: {index_name}')
                        )

                if not indexes_only and not dry_run:
                    # Database configuration optimizations
                    self.stdout.write('\n⚙️  Applying database optimizations...')

                    optimizations = [
                        "ALTER SYSTEM SET shared_buffers = '512MB';",
                        "ALTER SYSTEM SET effective_cache_size = '1GB';",
                        "ALTER SYSTEM SET work_mem = '32MB';",
                        "ALTER SYSTEM SET maintenance_work_mem = '128MB';",
                        "ALTER SYSTEM SET random_page_cost = 1.1;",
                        "ALTER SYSTEM SET effective_io_concurrency = 200;",
                        "SELECT pg_reload_conf();"
                    ]

                    for opt in optimizations:
                        try:
                            cursor.execute(opt)
                            self.stdout.write(
                                self.style.SUCCESS(f'✅ Applied: {opt.split()[2] if len(opt.split()) > 2 else "config"}')
                            )
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(f'⚠️  Skipped: {e}')
                            )

                # Analyze tables for query optimization
                if not dry_run:
                    self.stdout.write('\n📈 Analyzing tables...')
                    cursor.execute("ANALYZE core_interactiondetail;")
                    cursor.execute("ANALYZE core_catchmentpoint;")
                    self.stdout.write(
                        self.style.SUCCESS('✅ Table analysis completed')
                    )

                # Final report
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n🎉 Database optimization completed!'
                        f'\n   📊 Indexes created: {created_count if not dry_run else "dry-run"}'
                        f'\n   💡 Remember to reload PostgreSQL service for system settings'
                    )
                )

        except Exception as e:
            raise CommandError(f'❌ Database optimization failed: {e}')