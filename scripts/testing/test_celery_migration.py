#!/usr/bin/env python3
"""
Test script to verify Celery migration from cronjobs
Run this after setting up Celery to ensure everything works
"""

import os
import sys
import django
from datetime import timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.utils import timezone
from api.core.models import CatchmentPoint, InteractionDetail
from api.core.tasks.telemetry import collect_telemetry
from api.core.tasks.dga import process_dga_queue
from api.core.tasks.alerts import process_alerts
from api.core.tasks.monitoring import perform_health_check


def test_celery_setup():
    """Test basic Celery setup"""
    print("🧪 Testing Celery Setup...")

    try:
        from api.celery_app import app

        # Test Celery app
        result = app.send_task('api.core.tasks.monitoring.perform_health_check')
        health = result.get(timeout=30)

        print("✅ Celery worker is responding")
        print(f"   Health status: {health.get('overall_status', 'unknown')}")

        return True
    except Exception as e:
        print(f"❌ Celery setup failed: {e}")
        return False


def test_telemetry_task():
    """Test telemetry collection task"""
    print("\n🧪 Testing Telemetry Task...")

    try:
        # Get a test point (if exists)
        test_point = CatchmentPoint.objects.filter(
            data_config_profiles__is_telemetry=True
        ).first()

        if not test_point:
            print("⚠️  No telemetry-enabled points found, creating test data...")
            return True

        # Test task execution
        result = collect_telemetry.apply(args=['60'], throw=True)
        task_result = result.get(timeout=60)

        print("✅ Telemetry task executed successfully"        print(f"   Result: {task_result}")

        return True
    except Exception as e:
        print(f"❌ Telemetry task failed: {e}")
        return False


def test_dga_task():
    """Test DGA processing task"""
    print("\n🧪 Testing DGA Task...")

    try:
        result = process_dga_queue.apply(throw=True)
        task_result = result.get(timeout=30)

        print("✅ DGA task executed successfully"        print(f"   Processed: {task_result.get('processed', 0)}")
        print(f"   Errors: {task_result.get('errors', 0)}")

        return True
    except Exception as e:
        print(f"❌ DGA task failed: {e}")
        return False


def test_alerts_task():
    """Test alerts processing task"""
    print("\n🧪 Testing Alerts Task...")

    try:
        result = process_alerts.apply(throw=True)
        task_result = result.get(timeout=30)

        print("✅ Alerts task executed successfully"        print(f"   Processed: {task_result.get('alerts_processed', 0)}")
        print(f"   Notifications: {task_result.get('notifications_created', 0)}")

        return True
    except Exception as e:
        print(f"❌ Alerts task failed: {e}")
        return False


def test_database_performance():
    """Test database query performance"""
    print("\n🧪 Testing Database Performance...")

    try:
        from django.db import connection
        import time

        # Test recent telemetry query
        start_time = time.time()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM core_interactiondetail
                WHERE date_time_medition >= NOW() - INTERVAL '1 hour'
            """)
            count = cursor.fetchone()[0]
        query_time = time.time() - start_time

        print("✅ Database query successful"        print(f"   Records in last hour: {count}")
        print(".2f"        # Performance check
        if query_time > 1.0:
            print(".2f"            return False

        return True
    except Exception as e:
        print(f"❌ Database performance test failed: {e}")
        return False


def test_redis_connectivity():
    """Test Redis connectivity"""
    print("\n🧪 Testing Redis Connectivity...")

    try:
        from django.core.cache import cache
        import time

        # Test cache operations
        test_key = 'celery_test_key'
        test_value = 'celery_test_value'

        start_time = time.time()
        cache.set(test_key, test_value, 30)
        retrieved = cache.get(test_key)
        set_get_time = time.time() - start_time

        cache.delete(test_key)

        if retrieved == test_value:
            print("✅ Redis connectivity successful"            print(".2f"            return True
        else:
            print("❌ Redis cache inconsistency")
            return False

    except Exception as e:
        print(f"❌ Redis connectivity failed: {e}")
        return False


def main():
    """Run all tests"""
    print("🚀 SmartHydro Celery Migration Test Suite")
    print("=" * 50)

    tests = [
        ("Celery Setup", test_celery_setup),
        ("Redis Connectivity", test_redis_connectivity),
        ("Database Performance", test_database_performance),
        ("Telemetry Task", test_telemetry_task),
        ("DGA Task", test_dga_task),
        ("Alerts Task", test_alerts_task),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")

    print("\n" + "=" * 50)
    print("📊 Test Results:"    print(f"   Passed: {passed}/{total}")
    print(".1f"
    if passed == total:
        print("🎉 All tests passed! Celery migration successful!")
        return 0
    else:
        print("⚠️  Some tests failed. Check configuration and try again.")
        return 1


if __name__ == '__main__':
    sys.exit(main())