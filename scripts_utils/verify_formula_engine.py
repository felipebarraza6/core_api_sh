
import sys
sys.path.append('/app')
import os
import django
from datetime import timedelta
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models.users import User
from api.telemetry.models import CatchmentPoint, CoreVariable, TelemetryFormula, ProcessingRule, FormulaAssignment, RuleAssignment
from api.telemetry.processing.formula_engine import FormulaEngine

def test_formula_engine():
    print("--- Starting Formula Engine Verification ---")
    
    # 1. Create Mock Data
    user, _ = User.objects.get_or_create(email='test@example.com', defaults={'username': 'testuser'})
    
    point, _ = CatchmentPoint.objects.get_or_create(
        id=9999, 
        defaults={'title': 'Test Point', 'owner_user': user}
    )
    
    variable, _ = CoreVariable.objects.get_or_create(
        point=point,
        internal_code='test_var',
        defaults={'name': 'Test Variable'}
    )
    
    # 2. Create Formulas
    formula_jan, _ = TelemetryFormula.objects.get_or_create(
        code='jan_formula',
        defaults={'name': 'January Formula', 'expression': '{value} * 1'}
    )
    
    formula_feb, _ = TelemetryFormula.objects.get_or_create(
        code='feb_formula',
        defaults={'name': 'February Formula', 'expression': '{value} * 2'}
    )
    
    # 3. Create Rules
    rule_clamp, _ = ProcessingRule.objects.get_or_create(
        code='max_clamp',
        defaults={
            'name': 'Max Value Clamp', 
            'rule_type': 'MAX_VALUE',
            'default_parameters': {'limit': 100}
        }
    )
    
    # 4. Create Assignments (Time Slicing)
    now = timezone.now()
    jan_start = now.replace(month=1, day=1, hour=0, minute=0, second=0)
    feb_start = now.replace(month=2, day=1, hour=0, minute=0, second=0)
    mar_start = now.replace(month=3, day=1, hour=0, minute=0, second=0)
    
    # Assign Jan Formula for Jan
    FormulaAssignment.objects.update_or_create(
        variable=variable,
        valid_from=jan_start,
        defaults={'valid_to': feb_start, 'formula': formula_jan, 'priority': 10}
    )
    
    # Assign Feb Formula for Feb
    FormulaAssignment.objects.update_or_create(
        variable=variable,
        valid_from=feb_start,
        defaults={'valid_to': mar_start, 'formula': formula_feb, 'priority': 10}
    )
    
    # Assign Rule globally (always active)
    RuleAssignment.objects.update_or_create(
        variable=variable,
        rule=rule_clamp,
        defaults={'valid_from': jan_start}
    )
    
    # 5. Execute Tests
    engine = FormulaEngine(point_id=point.id)
    
    # Test Jan (Expect * 1)
    jan_date = jan_start + timedelta(days=5)
    result_jan = engine.process_variable(
        variable=variable,
        raw_value=50,
        current_values={},
        current_timestamp=jan_date
    )
    print(f"Jan Test (50 * 1): Got {result_jan} - {'✅ OK' if result_jan == 50 else '❌ FAIL'}")
    
    # Test Feb (Expect * 2)
    feb_date = feb_start + timedelta(days=5)
    result_feb = engine.process_variable(
        variable=variable,
        raw_value=50,
        current_values={},
        current_timestamp=feb_date
    )
    print(f"Feb Test (50 * 2): Got {result_feb} - {'✅ OK' if result_feb == 100 else '❌ FAIL'}")
    
    # Test Rule Clamp (Value 60 * 2 = 120, should be clamped to 100)
    result_clamp = engine.process_variable(
        variable=variable,
        raw_value=60,
        current_values={},
        current_timestamp=feb_date
    )
    print(f"Clamp Test (60 * 2 = 120 -> 100): Got {result_clamp} - {'✅ OK' if result_clamp == 100 else '❌ FAIL'}")

    # 6. Test Recursion Chain
    # Var A = 10 (fixed)
    # Var B = {fixed_var} * 2
    
    formula_fixed, _ = TelemetryFormula.objects.get_or_create(
        code='fixed_10', defaults={'name': 'Fixed 10', 'expression': '10'}
    )
    var_fixed, _ = CoreVariable.objects.get_or_create(
        point=point, internal_code='fixed_var', defaults={'name': 'Fixed Var'}
    )
    FormulaAssignment.objects.update_or_create(
        variable=var_fixed, valid_from=jan_start, defaults={'formula': formula_fixed}
    )
    
    var_rec, _ = CoreVariable.objects.get_or_create(
        point=point, internal_code='recursive_var', defaults={'name': 'Recursive Var'}
    )
    formula_rec, _ = TelemetryFormula.objects.get_or_create(
        code='rec_formula', defaults={'name': 'Recursive', 'expression': '{fixed_var} * 2'}
    )
    FormulaAssignment.objects.update_or_create(
        variable=var_rec, valid_from=jan_start, defaults={'formula': formula_rec}
    )
    
    print("Testing Recursion...")
    # Refresh engine context to load new variables
    engine = FormulaEngine(point_id=point.id)
    
    result_rec = engine.process_variable(
        variable=var_rec, raw_value=0, current_values={}, current_timestamp=jan_date
    )
    print(f"Recursion (10 * 2): Got {result_rec} - {'✅ OK' if result_rec == 20 else '❌ FAIL'}")

    # 7. Test Cycle Detection
    # Var C = {var_d}
    # Var D = {var_c}
    
    var_c, _ = CoreVariable.objects.get_or_create(point=point, internal_code='var_c', defaults={'name': 'C'})
    var_d, _ = CoreVariable.objects.get_or_create(point=point, internal_code='var_d', defaults={'name': 'D'})
    
    form_c, _ = TelemetryFormula.objects.get_or_create(code='f_c', defaults={'expression': '{var_d}'})
    form_d, _ = TelemetryFormula.objects.get_or_create(code='f_d', defaults={'expression': '{var_c}'})
    
    FormulaAssignment.objects.update_or_create(variable=var_c, valid_from=jan_start, defaults={'formula': form_c})
    FormulaAssignment.objects.update_or_create(variable=var_d, valid_from=jan_start, defaults={'formula': form_d})
    
    # Reload engine to pick up new vars
    engine = FormulaEngine(point_id=point.id)
    
    print("Testing Cycle Detection...")
    result_cycle = engine.process_variable(
        variable=var_c, raw_value=0, current_values={}, current_timestamp=jan_date
    )
    print(f"Cycle Test: Got {result_cycle} - {'✅ OK' if result_cycle == 0 else '❌ FAIL'}")

    print("--- Verification Complete ---")


# Execute Tests
test_formula_engine()

