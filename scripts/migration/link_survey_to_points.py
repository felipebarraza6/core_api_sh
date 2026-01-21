"""
Script de migración: Vincular TechnicalSurvey con CatchmentPoint

Este script:
1. Busca todos los CatchmentPoint existentes
2. Para cada uno, busca el TechnicalSurvey del mismo proyecto
3. Los vincula bidireccionalmente

Ejecutar con:
    docker-compose -f docker/docker-compose.dev.yml exec django_app python manage.py shell < scripts/migration/link_survey_to_points.py
"""

from django.db import transaction
from api.telemetry.models import CatchmentPoint
from api.crm.models import TechnicalSurvey

def migrate_survey_point_relations():
    """Vincula puntos existentes con sus levantamientos técnicos."""
    
    points = CatchmentPoint.objects.select_related('project').all()
    linked_count = 0
    created_survey_count = 0
    skipped_count = 0
    
    print(f"🔍 Encontrados {points.count()} puntos de captación")
    
    with transaction.atomic():
        for point in points:
            # Saltar si ya tiene un survey vinculado
            if point.technical_survey_id:
                skipped_count += 1
                continue
            
            project = point.project
            if not project:
                print(f"  ⚠️  Punto '{point.title}' sin proyecto asignado, saltando...")
                skipped_count += 1
                continue
            
            # Buscar survey existente del proyecto
            survey = TechnicalSurvey.objects.filter(project=project).first()
            
            if survey:
                # Vincular punto existente con survey existente
                point.technical_survey = survey
                point.save(update_fields=['technical_survey'])
                linked_count += 1
                print(f"  ✅ Vinculado: '{point.title}' → Survey '{survey.name or survey.id}'")
            else:
                # Crear survey básico para el proyecto
                survey = TechnicalSurvey.objects.create(
                    project=project,
                    name=f"Levantamiento - {point.title}",
                    requires_telemetry=True,
                    requires_dga=False,
                )
                point.technical_survey = survey
                point.save(update_fields=['technical_survey'])
                created_survey_count += 1
                linked_count += 1
                print(f"  🆕 Creado survey y vinculado: '{point.title}' → Survey '{survey.name}'")
    
    print("\n" + "="*50)
    print("📊 RESUMEN DE MIGRACIÓN")
    print("="*50)
    print(f"  • Puntos procesados: {points.count()}")
    print(f"  • Puntos vinculados: {linked_count}")
    print(f"  • Surveys creados:   {created_survey_count}")
    print(f"  • Puntos saltados:   {skipped_count}")
    print("="*50)

if __name__ == "__main__":
    migrate_survey_point_relations()
else:
    # Ejecutado desde shell
    migrate_survey_point_relations()
