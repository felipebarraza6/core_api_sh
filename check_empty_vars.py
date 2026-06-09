import django
django.setup()

from api.core.models import Variable, SchemesCatchment, CatchmentPoint

empty_vars = Variable.objects.filter(str_variable__in=['', None])
print(f"Variables con str_variable vacio/nulo: {empty_vars.count()}")
for v in empty_vars[:20]:
    schemes = SchemesCatchment.objects.filter(variables=v)
    points = CatchmentPoint.objects.filter(schemes__in=schemes).distinct()
    point_names = [p.title for p in points[:5]]
    print(f"  id={v.id} type={v.type_variable} str='{v.str_variable}' sensor='{v.sensor}' puntos={point_names}")
