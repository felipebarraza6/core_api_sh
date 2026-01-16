
import os
import django
from unittest.mock import MagicMock

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
django.setup()

from api.core.views.interaction_detail import InteractionXLS
from api.core.models import CatchmentPoint, Variable, ProjectCatchments, Client, User, SchemesCatchment

def setup_mock_data():
    # Ensure a user exists
    user, _ = User.objects.get_or_create(username="test_user", defaults={"email": "test@example.com"})
    
    # Ensure client & project
    client, _ = Client.objects.get_or_create(name="Test Client")
    project, _ = ProjectCatchments.objects.get_or_create(name="Test Project", client=client)

    # 1. Point with ONLY NIVEL
    point_nivel, _ = CatchmentPoint.objects.get_or_create(
        title="Test Point Nivel",
        project=project,
        owner_user=user,
        defaults={"lat": "0", "lon": "0"}
    )
    scheme_nivel, _ = SchemesCatchment.objects.get_or_create(name="Scheme Nivel")
    scheme_nivel.points_catchment.add(point_nivel)
    Variable.objects.get_or_create(scheme_catchment=scheme_nivel, type_variable="NIVEL", str_variable="nivel_var", label="Nivel")
    # Ensure no others
    Variable.objects.filter(scheme_catchment=scheme_nivel).exclude(type_variable="NIVEL").delete()

    # 2. Point with ALL
    point_all, _ = CatchmentPoint.objects.get_or_create(
        title="Test Point All",
        project=project,
        owner_user=user,
        defaults={"lat": "0", "lon": "0"}
    )
    scheme_all, _ = SchemesCatchment.objects.get_or_create(name="Scheme All")
    scheme_all.points_catchment.add(point_all)
    Variable.objects.get_or_create(scheme_catchment=scheme_all, type_variable="NIVEL", str_variable="n", label="N")
    Variable.objects.get_or_create(scheme_catchment=scheme_all, type_variable="CAUDAL", str_variable="c", label="C")
    Variable.objects.get_or_create(scheme_catchment=scheme_all, type_variable="TOTALIZADO", str_variable="t", label="T")

    return point_nivel, point_all

def test_view_context(point):
    view = InteractionXLS()
    view.request = MagicMock()
    view.request.query_params = {'catchment_point': str(point.id)}
    
    context = view.get_renderer_context()
    
    print(f"\n--- Testing Point: {point.title} (ID: {point.id}) ---")
    print("Titles (Context):", context.get('header', {}).get('titles'))
    print("Titles (View Instance):", view.column_header['titles'])
    print("Ignore List:", view.xlsx_ignore_headers)

if __name__ == "__main__":
    try:
        p_nivel, p_all = setup_mock_data()
        test_view_context(p_nivel)
        test_view_context(p_all)
    except Exception as e:
        print(f"Error: {e}")
