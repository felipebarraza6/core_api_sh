# Nuevas funciones Fase 1 - Temporal
# Este archivo contiene las nuevas funciones que se agregarán a tools.py

from api.core.models.catchment_points import CatchmentPoint
from api.core.models.interaction_detail import InteractionDetail
from django.db.models import Q
import pytz

chile_tz = pytz.timezone("America/Santiago")

def get_point_config(point_name):
    """Obtiene la configuración completa de un punto."""
    from api.core.models import CatchmentPoint, ProfileDataConfigCatchment, DgaDataConfigCatchment, Variable
    
    points = CatchmentPoint.objects.filter(Q(title__icontains=point_name) | Q(id=point_name))
    
    if not points.exists():
        return f"No encontré el punto '{point_name}'."
    
    if points.count() > 1:
        res = f"Encontré {points.count()} puntos con ese nombre:\n"
        for p in points[:5]:
            client = p.project.client.name if p.project and p.project.client else "N/A"
            res += f"• {p.title} ({client})\n"
        return res + "\nEspecifica mejor el nombre."
    
    point = points.first()
    client_name = point.project.client.name if p.project and p.project.client else "N/A"
    project_name = point.project.name if point.project else "N/A"
    
    res = f"⚙️ *Configuración de {point.title}*\n\n"
    res += f"📁 Cliente: {client_name}\n"
    res += f"📂 Proyecto: {project_name}\n"
    res += f"👤 Propietario: {point.owner_user.get_full_name() or point.owner_user.username}\n\n"
    
    # Configuración de telemetría
    data_config = ProfileDataConfigCatchment.objects.filter(point_catchment=point).first()
    if data_config:
        res += f"📡 *Telemetría*\n"
        res += f"   Activa: {'✅ Sí' if data_config.is_telemetry else '❌ No'}\n"
        
        # Variables activas
        variables = Variable.objects.filter(point_catchment=point)
        if variables.exists():
            res += f"   Variables: "
            var_list = []
            for v in variables:
                var_list.append(v.get_type_variable_display() if hasattr(v, 'get_type_variable_display') else v.type_variable)
            res += ", ".join(var_list) + "\n"
        res += "\n"
    
    # Configuración DGA
    dga_config = DgaDataConfigCatchment.objects.filter(point_catchment=point).first()
    if dga_config and dga_config.send_dga:
        res += f"📋 *DGA*\n"
        res += f"   Código: {dga_config.code_dga or 'N/A'}\n"
        res += f"   Estándar: {dga_config.standard}\n"
        res += f"   Tipo: {dga_config.type_dga}\n\n"
    
    # Última medición
    latest = InteractionDetail.objects.filter(catchment_point=point).order_by('-date_time_medition').first()
    if latest:
        fecha = latest.date_time_medition.astimezone(chile_tz).strftime("%d/%m/%Y %H:%M") if latest.date_time_medition else "N/A"
        res += f"📊 *Última Medición*: {fecha}\n"
        
        def safe_float(val):
            try:
                return float(val) if val else 0.0
            except:
                return 0.0
        
        flow_val = safe_float(latest.flow)
        nivel_val = safe_float(latest.nivel)
        total_val = safe_float(latest.total)
        days_disc = safe_float(latest.days_not_conection)
        
        if flow_val > 0:
            res += f"   Caudal: {round(flow_val, 2)} L/s\n"
        if nivel_val > 0:
            res += f"   Nivel: {round(nivel_val, 2)} m\n"
        if total_val > 0:
            res += f"   Total: {int(total_val)} m³\n"
        
        estado = "🔴 Desconectado" if days_disc > 0 else "🟢 Conectado"
        res += f"   Estado: {estado}\n"
    
    return res
