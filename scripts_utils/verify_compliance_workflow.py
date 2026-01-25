
import sys
sys.path.append('/app')
import os
import django
from django.utils import timezone
from datetime import timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models.users import User
from api.telemetry.models import CatchmentPoint, TelemetryRecord
from api.compliance.models import (
    ComplianceProvider, PointComplianceConfig, CompliancePeriod, ComplianceRule, ComplianceVoucher
)
from api.core.tasks.compliance_unified import send_compliance_data

def test_compliance():
    print("--- Starting Compliance Workflow Verification ---")
    
    # 1. Setup Data
    user, _ = User.objects.get_or_create(email='test_comp@example.com', defaults={'username': 'testcomp'})
    point, _ = CatchmentPoint.objects.get_or_create(id=9997, defaults={'title': 'Compliance Point', 'owner_user': user, 'point_code': 'TEST-CP'})
    
    provider, _ = ComplianceProvider.objects.get_or_create(
        name='test_prov', 
        defaults={
            'display_name': 'Test Provider',
            'base_url': 'http://mock.test',
            'data_endpoint_template': '/api/v1/data'
        }
    )
    
    config, _ = PointComplianceConfig.objects.get_or_create(
        point=point,
        provider=provider,
        defaults={'is_active': True, 'send_compliance': True}
    )
    
    # 2. Setup Blocking Rule
    rule, _ = ComplianceRule.objects.get_or_create(
        code='block_low_flow',
        defaults={
            'name': 'Block Low Flow',
            'logic': {"field": "flow", "operator": "<", "value": 1.0, "action": "IGNORE"}
        }
    )
    
    period, _ = CompliancePeriod.objects.get_or_create(
        point=point,
        name='Test Period',
        defaults={
            'valid_from': timezone.now() - timedelta(days=1),
            'valid_to': timezone.now() + timedelta(days=1),
            'is_active': True
        }
    )
    period.rules.add(rule)
    
    # 3. Test Blocked Record
    print("Test 1: Blocking compliance submission...")
    rec_blocked = TelemetryRecord.objects.create(
        point=point,
        timestamp=timezone.now(),
        data={'flow': 0.5} # < 1.0, should prompt IGNORE
    )
    
    # Call Task (Synchronously)
    send_compliance_data(rec_blocked.id, config.id)
    
    # Verify Voucher
    voucher = ComplianceVoucher.objects.filter(telemetry_record=rec_blocked).first()
    if voucher and voucher.voucher_status == 'IGNORED':
        print(f"✅ Voucher status is IGNORED (Reason: {voucher.error_message})")
    else:
        print(f"❌ FAIL: Voucher status is {voucher.voucher_status if voucher else 'None'}")
        
    # 4. Test Allowed Record
    print("Test 2: Allowing compliance submission...")
    rec_allowed = TelemetryRecord.objects.create(
        point=point,
        timestamp=timezone.now() + timedelta(seconds=1),
        data={'flow': 5.0} # > 1.0, allowed
    )
    
    try:
        send_compliance_data(rec_allowed.id, config.id)
    except Exception as e:
        print(f"Caught expected exception (Mock service connection): {type(e).__name__}")
        
    # Verify Voucher is ERROR (because http mock fails, but passed logic)
    voucher_ok = ComplianceVoucher.objects.filter(telemetry_record=rec_allowed).first()
    if voucher_ok and voucher_ok.voucher_status == 'ERROR':
        print(f"✅ Voucher status is ERROR (Passed logic, failed connection)")
    elif voucher_ok and voucher_ok.voucher_status == 'SENT':
         print(f"⚠️  Voucher status is SENT (Unexpected success against mock)")
    else:
        print(f"❌ FAIL: Voucher status is {voucher_ok.voucher_status if voucher_ok else 'None'}")

    print("--- Verification Complete ---")

if __name__ == "__main__":
    test_compliance()
