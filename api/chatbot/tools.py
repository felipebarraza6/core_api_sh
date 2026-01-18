import pytz
from django.db.models import Q

from api.telemetry.models.telemetry import TelemetryRecord
from api.telemetry.models.catchment_points import CatchmentPoint

chile_tz = pytz.timezone("America/Santiago")


def search_points(query, context_client=None):
    """Busca puntos por nombre, cliente, proyecto o usuario.

    Prioriza el contexto del cliente si se proporciona.
    """
    from django.db.models import Q

    from api.telemetry.models.catchment_points import CatchmentPoint, Client

    clean_query = query.replace("puntos de ", "").replace("pozos de ", "").strip()

    # PASO 0: Si tenemos un contexto de cliente y una búsqueda corta (ej: "P4")
    # Intentar resolverlo directamente dentro de ese cliente
    if context_client and len(clean_query) <= 10:
        context_points = CatchmentPoint.objects.filter(
            project__client__name__icontains=context_client,
            title__icontains=clean_query,
        ).select_related("project", "project__client")

        if context_points.count() == 1:
            p = context_points.first()
            return [{"id": p.id, "title": p.title, "client": p.project.client.name}]
        elif context_points.exists():
            # Si hay varios, devolver solo los del cliente en contexto para desambiguar rápido
            return [
                {"id": p.id, "title": p.title, "client": p.project.client.name}
                for p in context_points[:10]
            ]

    # PASO 1: Buscar como cliente completo
    client_matches = Client.objects.filter(name__icontains=clean_query)
    if client_matches.exists():
        client = client_matches.first()
        points = CatchmentPoint.objects.filter(project__client=client).select_related(
            "project", "project__client", "owner_user"
        )
        if points.exists():
            return [
                {
                    "id": p.id,
                    "title": p.title,
                    "client": (
                        p.project.client.name
                        if p.project and p.project.client
                        else "N/A"
                    ),
                }
                for p in points[:15]
            ]

    # PASO 2: Buscar por términos (Lógica AND / Intersection)
    terms = [
        t
        for t in query.split()
        if len(t) >= 2
        and t.lower()
        not in (
            "de",
            "del",
            "la",
            "los",
            "las",
            "el",
            "que",
            "hay",
            "cuales",
            "cuantos",
            "puntos",
            "pozos",
        )
    ]

    if not terms:
        return []

    # Comenzamos con todos los puntos y vamos filtrando por cada término
    # Un punto debe hacer match con TODOS los términos (en cualquiera de sus campos)
    points_qs = CatchmentPoint.objects.all()

    for term in terms:
        term_q = (
            Q(title__icontains=term)
            | Q(project__name__icontains=term)
            | Q(project__code_internal__icontains=term)
            | Q(project__client__name__icontains=term)
            | Q(owner_user__username__icontains=term)
            | Q(owner_user__first_name__icontains=term)
            | Q(owner_user__last_name__icontains=term)
        )
        points_qs = points_qs.filter(term_q)

    points = points_qs.select_related(
        "project", "project__client", "owner_user"
    ).distinct()[:15]

    return [
        {
            "id": p.id,
            "title": p.title,
            "client": (
                p.project.client.name if p.project and p.project.client else "N/A"
            ),
        }
        for p in points
    ]


def get_client_summary(client_name, project_name=None):
    """Obtiene un resumen de puntos para un cliente, opcionalmente filtrado por proyecto."""
    from api.telemetry.models.catchment_points import CatchmentPoint, Client, ProjectCatchments

    clients = Client.objects.filter(name__icontains=client_name)
    if not clients.exists():
        return f"No encontré al cliente '{client_name}'."

    client = clients.first()

    # Si se especifica proyecto, filtrar por él
    if project_name:
        projects = ProjectCatchments.objects.filter(
            client=client, name__icontains=project_name
        )
        if not projects.exists():
            return f"No encontré el proyecto '{project_name}' para {client.name}."

        project = projects.first()
        points = CatchmentPoint.objects.filter(project=project)
        count = points.count()

        res = f"Proyecto *{project.name}* de {client.name} ({count} puntos):\n"
        for p in points[:15]:
            res += f"- {p.title}\n"

        if count > 15:
            res += f"... y {count - 15} más."

        return res

    # Sin proyecto específico: mostrar resumen por proyectos
    projects = ProjectCatchments.objects.filter(client=client)
    total_points = CatchmentPoint.objects.filter(project__client=client).count()

    res = f"El cliente *{client.name}* tiene {total_points} puntos en {projects.count()} proyectos:\n\n"

    for proj in projects:
        proj_points = CatchmentPoint.objects.filter(project=proj)
        count = proj_points.count()
        res += f"📁 *{proj.name}* ({count} puntos)\n"
        for p in proj_points[:5]:
            res += f"   • {p.title}\n"
        if count > 5:
            res += f"   ... y {count - 5} más\n"
        res += "\n"

    res = add_suggestions(res, context="CLIENT", client=client.name)
    return res


def get_project_measurements(client_name, project_name):
    """Obtiene mediciones de todos los puntos de un proyecto específico."""
    from api.telemetry.models.catchment_points import CatchmentPoint, Client, ProjectCatchments

    clients = Client.objects.filter(name__icontains=client_name)
    if not clients.exists():
        return f"No encontré al cliente '{client_name}'."

    client = clients.first()
    projects = ProjectCatchments.objects.filter(
        client=client, name__icontains=project_name
    )

    if not projects.exists():
        return f"No encontré el proyecto '{project_name}' para {client.name}."

    project = projects.first()
    points = CatchmentPoint.objects.filter(project=project)

    if not points.exists():
        return f"El proyecto '{project.name}' no tiene puntos registrados."

    res = f"📊 *Mediciones de {project.name}* ({client.name})\n\n"

    def safe_float(val):
        if val is None:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    for point in points[:10]:
        latest = (
            TelemetryRecord.objects.filter(point=point).order_by("-timestamp").first()
        )

        if latest:
            actual_date = latest.timestamp
            if latest.metadata.get("last_logger_timestamp"):
                try:
                    from datetime import datetime

                    actual_date = datetime.fromisoformat(
                        latest.metadata["last_logger_timestamp"]
                    )
                except:
                    pass

            fecha = (
                actual_date.astimezone(chile_tz).strftime("%d/%m %H:%M")
                if actual_date
                else "N/A"
            )
            days_disc = safe_float(latest.metadata.get("days_not_connection", 0))
            estado = "🔴" if days_disc > 0 else "🟢"

            valores = []
            data = latest.data
            flow_val = safe_float(data.get("flow", data.get("caudal", 0)))
            nivel_val = safe_float(data.get("nivel", 0))
            total_val = safe_float(data.get("total", 0))
            today_val = safe_float(data.get("total_today_diff", 0))

            if flow_val > 0:
                valores.append(f"Q:{round(flow_val, 2)}L/s")
            if nivel_val > 0:
                valores.append(f"N:{round(nivel_val, 2)}m")
            if total_val > 0:
                valores.append(f"T:{int(total_val)}m³")
            if today_val > 0:
                valores.append(f"Hoy:{int(today_val)}m³")

            valores_str = " | ".join(valores) if valores else "Sin datos"
            res += f"{estado} *{point.title}* ({fecha})\n   {valores_str}\n"
        else:
            res += f"⚪ *{point.title}*: Sin mediciones\n"

    if points.count() > 10:
        res += f"\n... y {points.count() - 10} puntos más."

    # El contexto se detecta en add_suggestions, pero pasamos el cliente si está disponible
    client_name_ctx = client.name if "client" in locals() else None
    res = add_suggestions(
        res,
        context="STATS" if "Últimas mediciones" in res else "PROJECT",
        client=client_name_ctx,
    )
    return res


def get_point_latest_data(point_id):
    """
    Obtiene la última medición detallada de un punto específico.
    """
    try:
        point = CatchmentPoint.objects.get(id=point_id)
        latest = (
            TelemetryRecord.objects.filter(point=point).order_by("-timestamp").first()
        )

        if not latest:
            return f"El punto '{point.title}' no tiene mediciones registradas."

        # Determinar qué variables envía el punto (V3 uses CoreVariable)
        variables_enviadas = []
        try:
            from api.telemetry.models.telemetry import CoreVariable

            vars_v3 = CoreVariable.objects.filter(point=point, is_active=True)
            for v in vars_v3:
                variables_enviadas.append(v.internal_code)
        except:
            pass

        # Formatear fechas
        fecha_sistema = latest.timestamp.astimezone(chile_tz).strftime("%d/%m/%Y %H:%M")
        fecha_sensor = "N/A"
        if latest.metadata.get("last_logger_timestamp"):
            try:
                from datetime import datetime

                ls = datetime.fromisoformat(latest.metadata["last_logger_timestamp"])
                fecha_sensor = ls.astimezone(chile_tz).strftime("%d/%m/%Y %H:%M")
            except:
                pass

        client_name = (
            point.project.client.name
            if point.project and point.project.client
            else "N/A"
        )

        res = f"📍 *Punto:* {point.title}\n"
        res += f"🏢 *Cliente:* {client_name}\n"
        res += f"🕒 *Sist:* {fecha_sistema} | 📟 *Sens:* {fecha_sensor}\n\n"

        # Valores
        data = latest.data
        flow = float(data.get("flow", data.get("caudal", 0)))
        nivel = float(data.get("nivel", 0))
        total = float(data.get("total", 0))
        today_diff = float(data.get("total_today_diff", 0))

        if flow > 0:
            # Detectar si es Caudal o Caudal Promedio
            es_promedio = "flow" in variables_enviadas  # V3 internal code
            q_label = "Caudal"
            res += f"🌊 *{q_label}:* {flow} L/s\n"

        if nivel > 0:
            res += f"📏 *Nivel:* {nivel} mt\n"

        if total > 0:
            res += f"🚜 *Totalizador:* {total} m³\n"

        if today_diff > 0:
            res += f"💧 *Consumo Hoy:* {today_diff} m³\n"

        res += "\n"
        days_disc = float(latest.metadata.get("days_not_connection", 0))
        if days_disc > 0:
            res += f"⚠️ *Estado:* Desconectado ({int(days_disc)} días)"
        else:
            res += "✅ *Estado:* Operativo / Conectado"

        res = add_suggestions(
            res, context="POINT", point=point.title, client=client_name
        )
        return res
    except CatchmentPoint.DoesNotExist:
        return "Punto no encontrado."
    except Exception as e:
        return f"Error al obtener datos: {str(e)}"


def get_client_measurements(client_name):
    """Obtiene la última medición de TODOS los puntos de un cliente."""
    from api.telemetry.models.catchment_points import CatchmentPoint, Client

    clients = Client.objects.filter(name__icontains=client_name)
    if not clients.exists():
        return f"No encontré al cliente '{client_name}'."

    client = clients.first()
    points = CatchmentPoint.objects.filter(project__client=client).select_related(
        "project", "project__client"
    )

    if not points.exists():
        return f"El cliente '{client.name}' no tiene puntos registrados."

    res = f"📊 *Últimas mediciones de {client.name}* ({points.count()} puntos):\n\n"

    def safe_float(val):
        """Convierte a float de forma segura."""
        if val is None:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    for point in points[:10]:  # Max 10 para no saturar
        latest = (
            TelemetryRecord.objects.filter(point=point).order_by("-timestamp").first()
        )

        if latest:
            actual_date = latest.timestamp
            if latest.metadata.get("last_logger_timestamp"):
                try:
                    from datetime import datetime

                    actual_date = datetime.fromisoformat(
                        latest.metadata["last_logger_timestamp"]
                    )
                except:
                    pass

            fecha = (
                actual_date.astimezone(chile_tz).strftime("%d/%m %H:%M")
                if actual_date
                else "N/A"
            )
            days_disc = safe_float(latest.metadata.get("days_not_connection", 0))
            estado = "🔴" if days_disc > 0 else "🟢"

            # Solo mostrar valores que existen (con conversión segura)
            valores = []
            data = latest.data
            flow_val = safe_float(data.get("flow", data.get("caudal", 0)))
            nivel_val = safe_float(data.get("nivel", 0))
            total_val = safe_float(data.get("total", 0))
            today_val = safe_float(data.get("total_today_diff", 0))

            if flow_val > 0:
                valores.append(f"Q:{round(flow_val, 2)}L/s")
            if nivel_val > 0:
                valores.append(f"N:{round(nivel_val, 2)}m")
            if total_val > 0:
                valores.append(f"T:{int(total_val)}m³")
            if today_val > 0:
                valores.append(f"Hoy:{int(today_val)}m³")

            valores_str = " | ".join(valores) if valores else "Sin datos"
            res += f"{estado} *{point.title}* ({fecha})\n   {valores_str}\n"
        else:
            res += f"⚪ *{point.title}*: Sin mediciones\n"

    if points.count() > 10:
        res += f"\n... y {points.count() - 10} puntos más."

    # El contexto se detecta en add_suggestions, pero pasamos el cliente si está disponible
    client_name_ctx = client.name if "client" in locals() else None
    res = add_suggestions(
        res,
        context="STATS" if "Últimas mediciones" in res else "PROJECT",
        client=client_name_ctx,
    )
    return res


def get_point_status_summary():
    """Obtiene un resumen del estado general de todos los puntos."""
    from django.db.models import Count

    from api.telemetry.models.catchment_points import CatchmentPoint

    def safe_float(val):
        if val is None:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    total = CatchmentPoint.objects.filter(
        data_config_profiles__is_telemetry=True
    ).count()

    # Contar desconectados
    disconnected = 0
    connected = 0

    for point in CatchmentPoint.objects.filter(data_config_profiles__is_telemetry=True):
        latest = (
            TelemetryRecord.objects.filter(point=point).order_by("-timestamp").first()
        )
        days_val = (
            safe_float(latest.metadata.get("days_not_connection", 0)) if latest else 0
        )
        if days_val > 0:
            disconnected += 1
        else:
            connected += 1

    res = f"📊 *Estado General del Sistema*\n\n"
    res += f"✅ Puntos conectados: {connected}\n"
    res += f"🔴 Puntos desconectados: {disconnected}\n"
    res += f"📍 Total puntos activos: {total}\n"

    health = round((connected / total * 100), 1) if total > 0 else 0
    res += f"\n💚 Salud del sistema: {health}%"

    res = add_suggestions(res, context="GLOBAL")
    return res


def get_dga_compliance(client_name):
    """Obtiene el cumplimiento DGA de un cliente: códigos, vouchers y errores."""
    from datetime import datetime, timedelta

    from api.telemetry.models.catchment_points import CatchmentPoint, Client, DgaDataConfigCatchment

    clients = Client.objects.filter(name__icontains=client_name)
    if not clients.exists():
        return f"No encontré al cliente '{client_name}'."

    client = clients.first()
    points = CatchmentPoint.objects.filter(project__client=client).select_related(
        "project", "project__client"
    )

    if not points.exists():
        return f"El cliente '{client.name}' no tiene puntos registrados."

    def safe_float(val):
        if val is None:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    # Calcular inicio del día en hora Chile
    import pytz

    chile_tz = pytz.timezone("America/Santiago")
    now_chile = datetime.now(chile_tz)
    today_start = now_chile.replace(hour=0, minute=0, second=0, microsecond=0)

    points_with_dga = 0
    points_with_errors = 0
    points_with_vouchers = 0
    total_envios_hoy = 0

    res = f"📋 *Cumplimiento DGA - {client.name}*\n"
    res += f"📅 Fecha: {now_chile.strftime('%d/%m/%Y %H:%M')}\n\n"

    details = []

    for point in points:
        # Obtener configuración DGA
        dga_config = DgaDataConfigCatchment.objects.filter(
            point_catchment=point
        ).first()

        if not dga_config or not dga_config.send_dga:
            continue  # Saltar puntos sin DGA activo

        points_with_dga += 1

        # Contar envíos de hoy (registros con voucher)
        envios_hoy = (
            TelemetryRecord.objects.filter(
                point=point, timestamp__gte=today_start, n_voucher__isnull=False
            )
            .exclude(n_voucher="")
            .count()
        )

        total_envios_hoy += envios_hoy

        # Obtener última medición (con o sin DGA)
        latest = (
            TelemetryRecord.objects.filter(point=point).order_by("-timestamp").first()
        )

        if not latest:
            details.append(
                {
                    "icon": "⚪",
                    "title": point.title,
                    "code": dga_config.code_dga or "N/A",
                    "standard": dga_config.standard,
                    "status": "Sin mediciones",
                    "envios_hoy": 0,
                }
            )
            continue

        # Formatear fecha (Priorizar logger)
        actual_date = latest.timestamp
        if latest.metadata.get("last_logger_timestamp"):
            try:
                actual_date = datetime.fromisoformat(
                    latest.metadata["last_logger_timestamp"]
                )
            except:
                pass

        fecha = (
            actual_date.astimezone(chile_tz).strftime("%d/%m %H:%M")
            if actual_date
            else "N/A"
        )

        # Determinar estado basado en voucher y errores
        has_voucher = latest.n_voucher and latest.n_voucher.strip()
        has_error = latest.is_error or (
            latest.return_dga and "error" in latest.return_dga.lower()
        )

        if has_voucher:
            points_with_vouchers += 1
            estado_icon = "✅"
            estado_text = f"Voucher: {latest.n_voucher[:20]}"
        elif has_error:
            points_with_errors += 1
            estado_icon = "❌"
            error_msg = (
                latest.return_dga[:50] if latest.return_dga else "Error desconocido"
            )
            estado_text = f"Error: {error_msg}"
        else:
            estado_icon = "⏳"
            estado_text = "Pendiente de envío"

        # Valores de medición
        data = latest.data
        flow_val = safe_float(data.get("flow", data.get("caudal", 0)))
        total_val = safe_float(data.get("total", 0))

        details.append(
            {
                "icon": estado_icon,
                "title": point.title,
                "code": dga_config.code_dga or "N/A",
                "standard": dga_config.standard,
                "fecha": fecha,
                "flow": flow_val,
                "total": total_val,
                "status": estado_text,
                "envios_hoy": envios_hoy,
            }
        )

    # Resumen
    if points_with_dga == 0:
        return (
            f"El cliente '{client.name}' no tiene puntos con cumplimiento DGA activo."
        )

    res += f"📊 *Resumen:*\n"
    res += f"   {points_with_dga} puntos con DGA activo\n"
    res += f"   ✅ Con voucher: {points_with_vouchers}\n"
    res += f"   ❌ Con errores: {points_with_errors}\n"
    res += f"   ⏳ Pendientes: {points_with_dga - points_with_vouchers - points_with_errors}\n"
    res += f"   📤 Envíos hoy: {total_envios_hoy}\n\n"

    # Detalles por punto
    for d in details:
        res += f"{d['icon']} *{d['title']}*\n"
        res += f"   Código: {d['code']} | {d['standard']}\n"

        if "fecha" in d:
            res += (
                f"   {d['fecha']} | Q:{round(d['flow'], 2)}L/s T:{int(d['total'])}m³\n"
            )
            res += f"   {d['status']}\n"
        else:
            res += f"   {d['status']}\n"

        if d["envios_hoy"] > 0:
            res += f"   📤 Envíos hoy: {d['envios_hoy']}\n"

        res += "\n"

    res = add_suggestions(res, context="CLIENT", client=client.name)
    return res


# ========== FASE 1: NUEVAS FUNCIONALIDADES ==========


def get_point_config(point_name, context_client=None):
    """Obtiene la configuración completa de un punto."""
    from api.telemetry.models.catchment_points import (
        CatchmentPoint,
        DgaDataConfigCatchment,
        ProfileDataConfigCatchment,
    )
    from api.core.models import CoreVariable

    # Usar search_points para desambiguar con contexto
    found_points = search_points(point_name, context_client)

    if not found_points:
        return f"No encontré el punto '{point_name}'."

    if len(found_points) > 1:
        res = f"Encontré {len(found_points)} puntos similares. ¿A cuál te refieres?\n"
        for p in found_points[:8]:
            res += f"• {p['title']} (Cliente: {p['client']})\n"
        return res

    point_id = found_points[0]["id"]
    point = CatchmentPoint.objects.get(id=point_id)
    client_name = (
        point.project.client.name if point.project and point.project.client else "N/A"
    )
    project_name = point.project.name if point.project else "N/A"

    res = f"⚙️ *Configuración Técnica de {point.title}*\n\n"
    res += f"📁 Cliente: {client_name}\n"
    res += f"📂 Proyecto: {project_name}\n"
    res += f"👤 Propietario: {point.owner_user.get_full_name() or point.owner_user.username}\n\n"

    # Configuración de telemetría y Escalas (ProfileDataConfigCatchment)
    data_config = ProfileDataConfigCatchment.objects.filter(
        point_catchment=point
    ).first()
    if data_config:
        res += f"📡 *Parámetros Télemetría (Escalas)*\n"
        res += f"   • Telemetría Activa: {'✅ SI' if data_config.is_telemetry else '❌ NO'}\n"
        if data_config.d1 > 0:
            res += f"   • Profundidad Pozo (d1): {data_config.d1} mt\n"
        if data_config.d2 > 0:
            res += f"   • Posicionamiento Bomba (d2): {data_config.d2} mt\n"
        if data_config.d3 > 0:
            res += f"   • Posicionamiento Nivel (d3): {data_config.d3} mt\n"
        if data_config.d4 > 0:
            res += f'   • Diámetro Ducto Salida (d4): {data_config.d4}"\n'
        if data_config.d5 > 0:
            res += f'   • Diámetro Flujómetro (d5): {data_config.d5}"\n'
        if data_config.d6:
            res += f"   • Lectura Inicial (d6): {data_config.d6} m³\n"
        if data_config.addition > 0:
            res += f"   • Adición (Reset/Glitch): {data_config.addition} m³\n"
        res += "\n"

        # Variables detalladas (CoreVariable model)
        from api.core.models import CoreVariable

        variables = CoreVariable.objects.filter(point=point, is_active=True)
        if variables.exists():
            res += f"📊 *Variables Configuradas*\n"
            for v in variables:
                res += f"   🔹 *{v.name}* ({v.internal_code})\n"
                res += f"      • Unit: {v.unit} | Factor: {v.scale_factor}\n"
            res += "\n"

    # Configuración DGA
    dga_config = DgaDataConfigCatchment.objects.filter(point_catchment=point).first()
    if dga_config and dga_config.send_dga:
        res += f"📋 *Configuración DGA (Fiscalización)*\n"
        res += f"   • Código Obra: `{dga_config.code_dga or 'N/A'}`\n"
        res += f"   • Estándar: {dga_config.get_standard_display() if hasattr(dga_config, 'get_standard_display') else dga_config.standard}\n"
        res += f"   • Tipo: {dga_config.get_type_dga_display() if hasattr(dga_config, 'get_type_dga_display') else dga_config.type_dga}\n"
        res += f"   • Caudal Otorgado: {dga_config.flow_granted_dga} L/s\n"
        if dga_config.total_granted_dga:
            res += f"   • Total Anual: {dga_config.total_granted_dga} m³\n"
        res += "\n"

    res = add_suggestions(res, context="POINT", point=point.title, client=client_name)
    return res


def get_client_alerts(client_name):
    """Obtiene las alertas activas de un cliente."""
    from api.telemetry.models.catchment_points import CatchmentPoint, Client

    clients = Client.objects.filter(name__icontains=client_name)
    if not clients.exists():
        return f"No encontré al cliente '{client_name}'."

    client = clients.first()
    points = CatchmentPoint.objects.filter(project__client=client)

    disconnected = []
    errors = []

    for point in points:
        latest = (
            TelemetryRecord.objects.filter(point=point).order_by("-timestamp").first()
        )

        if not latest:
            continue

        try:
            days_disc = float(latest.metadata.get("days_not_connection", 0))
        except:
            days_disc = 0

        if days_disc > 0:
            disconnected.append({"point": point.title, "days": int(days_disc)})

        if latest.is_error:
            errors.append(
                {
                    "point": point.title,
                    "error": (latest.return_dga[:50] if latest.return_dga else "Error"),
                }
            )

    total_alerts = len(disconnected) + len(errors)

    if total_alerts == 0:
        return f"✅ El cliente *{client.name}* no tiene alertas activas."

    res = f"🔔 *Alertas de {client.name}*\n\n"
    res += f"Total: {total_alerts}\n\n"

    if disconnected:
        res += f"🔴 *Desconectados ({len(disconnected)})*\n"
        for d in disconnected[:5]:
            res += f"   • {d['point']}: {d['days']} días\n"
        res += "\n"

    if errors:
        res += f"❌ *Con errores ({len(errors)})*\n"
        for e in errors[:5]:
            res += f"   • {e['point']}: {e['error']}\n"

    res = add_suggestions(res, context="CLIENT", client=client.name)
    return res


def get_point_history(point_name, days=7, context_client=None):
    """Obtiene el historial de mediciones de un punto."""
    from datetime import datetime, timedelta

    import pytz

    from api.telemetry.models.catchment_points import CatchmentPoint

    found_points = search_points(point_name, context_client)

    if not found_points:
        return f"No encontré el punto '{point_name}'."

    if len(found_points) > 1:
        res = f"Encontré {len(found_points)} puntos. Especifica:\n"
        for p in found_points[:5]:
            res += f"• {p['title']} ({p['client']})\n"
        return res

    point_id = found_points[0]["id"]
    point = CatchmentPoint.objects.get(id=point_id)

    chile_tz = pytz.timezone("America/Santiago")
    now = datetime.now(chile_tz)
    start_date = now - timedelta(days=days)

    records = TelemetryRecord.objects.filter(
        point=point, timestamp__gte=start_date
    ).order_by("-timestamp")[:20]

    if not records.exists():
        return f"No hay mediciones de *{point.title}* en los últimos {days} días."

    res = f"📊 *Historial de Extracciones: {point.title}*\n"
    res += f"Período: Últimos {days} días\n\n"

    for record in records[:10]:
        actual_date = record.timestamp
        if record.metadata.get("last_logger_timestamp"):
            try:
                actual_date = datetime.fromisoformat(
                    record.metadata["last_logger_timestamp"]
                )
            except:
                pass

        fecha = actual_date.astimezone(chile_tz).strftime("%d/%m %H:%M")
        data = record.data
        flow_val = float(data.get("flow", data.get("caudal", 0)))
        total_val = float(data.get("total", 0))
        res += f"• {fecha}: Q: {round(flow_val, 2)} L/s | T: {int(total_val)} m³\n"

    res += f"\n💡 *Q*: Caudal instantáneo | *T*: Totalizado acumulado"
    res = add_suggestions(
        res, context="POINT", point=point.title, client=context_client
    )
    return res


def get_client_errors(client_name, days=7):
    """Obtiene los errores recientes de un cliente."""
    from datetime import datetime, timedelta

    from api.telemetry.models.catchment_points import CatchmentPoint, Client

    clients = Client.objects.filter(name__icontains=client_name)
    if not clients.exists():
        return f"No encontré al cliente '{client_name}'."

    client = clients.first()
    points = CatchmentPoint.objects.filter(project__client=client)

    start_date = datetime.now() - timedelta(days=days)
    error_records = TelemetryRecord.objects.filter(
        point__in=points, timestamp__gte=start_date, is_error=True
    ).order_by("-timestamp")[:15]

    if not error_records.exists():
        return f"✅ No se registran fallos técnicos recientes para *{client.name}*."

    res = f"❌ *Fallas Técnicas / DGA: {client.name}*\n"
    res += f"Reporte de los últimos {days} días\n\n"
    for r in error_records:
        fecha = r.timestamp.strftime("%d/%m %H:%M")
        res += f"• *{r.point.title}* ({fecha}):\n  └─ {r.return_dga[:80]}\n\n"

    res = add_suggestions(res, context="STATS", client=client.name)
    return res


def get_global_status():
    """Obtiene un boletín operativo detallado de TODA la flota de SmartHydro (Modo Estado)."""
    from datetime import datetime

    import pytz
    from django.db.models import Count, Q

    from api.telemetry.models.catchment_points import CatchmentPoint, Client, NotificationsCatchment

    chile_tz = pytz.timezone("America/Santiago")

    # 1. Resumen de Flota
    total_points = CatchmentPoint.objects.filter(
        data_config_profiles__is_telemetry=True
    ).count()
    total_clients = Client.objects.count()

    disconnected_list = []
    with_errors = 0

    points_active = CatchmentPoint.objects.filter(
        data_config_profiles__is_telemetry=True
    ).select_related("project__client")

    for p in points_active:
        latest = TelemetryRecord.objects.filter(point=p).order_by("-timestamp").first()
        if latest:
            try:
                days = float(latest.metadata.get("days_not_connection", 0))
                if days > 0:
                    # USAR date_time_last_logger
                    actual_date = latest.timestamp
                    if latest.metadata.get("last_logger_timestamp"):
                        try:
                            actual_date = datetime.fromisoformat(
                                latest.metadata["last_logger_timestamp"]
                            )
                        except:
                            pass

                    # Si es muy viejo, agregar el año
                    fmt = "%d/%m/%y %H:%M" if days > 30 else "%d/%m %H:%M"
                    fecha_str = actual_date.astimezone(chile_tz).strftime(fmt)

                    # Obtener variables configuradas y su estado (simplificado)
                    vars_status = []
                    data = latest.data
                    if data.get("total") and float(data["total"]) > 0:
                        vars_status.append("✅T")
                    if data.get("nivel") and float(data["nivel"]) > 0:
                        vars_status.append("✅N")
                    if data.get("flow") and float(data["flow"]) > 0:
                        vars_status.append("✅Q")

                    disconnected_list.append(
                        {
                            "title": p.title,
                            "client": (
                                p.project.client.name
                                if p.project and p.project.client
                                else "N/A"
                            ),
                            "days": int(days),
                            "last_seen": fecha_str,
                            "vars": " ".join(vars_status) if vars_status else "",
                        }
                    )
            except:
                pass
            if latest.is_error:
                with_errors += 1

    # Ordenar desconectados por más días primero
    disconnected_list = sorted(disconnected_list, key=lambda x: x["days"], reverse=True)
    connected_count = total_points - len(disconnected_list)
    health = round((connected_count / total_points * 100), 1) if total_points > 0 else 0

    # Construcción del Boletín
    res = f"🌐 *Boletín Operativo SmartHydro*\n"
    res += f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
    res += f"🏢 Clientes: {total_clients} | 📍 Flota: {total_points} puntos\n"
    res += f"✅ Online: {connected_count} | 🔴 Offline: {len(disconnected_list)} | 💚 {health}%\n\n"

    # 2. SECCIÓN ESTADO: Desconectados críticos
    if disconnected_list:
        res += f"🚨 *Puntos Offline ({len(disconnected_list)})*\n"
        res += f"(T=Total, N=Nivel, Q=Caudal | ✅Ok ❌Falla)\n\n"
        for d in disconnected_list[:50]:
            vars_str = f" [{d['vars']}]" if d.get("vars") else ""
            res += f"• *{d['title']}* ({d['client']}){vars_str}\n"
            res += f"  └─ {d['days']}d sin señal (Ult: {d['last_seen']})\n"

        if len(disconnected_list) > 50:
            res += f"  ... y {len(disconnected_list) - 50} más.\n"
        res += "\n"

    # 3. SECCIÓN NOTIFICACIONES (Agrupadas)
    notifs = (
        NotificationsCatchment.objects.filter(is_active=True)
        .select_related("point_catchment__project__client")
        .order_by("-id")[:20]
    )
    if notifs.exists():
        res += f"🔔 *Últimas Alertas del Sistema*\n"
        grouped_notifs = {}
        for n in notifs:
            clean_title = n.title.strip()
            key = (n.point_catchment.id, clean_title)
            if key not in grouped_notifs:
                grouped_notifs[key] = {
                    "title": clean_title,
                    "point": n.point_catchment.title,
                    "count": 1,
                    "type": n.type_notification,
                }
            else:
                grouped_notifs[key]["count"] += 1

        for key, n in list(grouped_notifs.items())[:8]:
            icon = "🚨" if n["type"] == "CRITICAL" else "⚠️"
            count_str = f" ({n['count']} veces)" if n["count"] > 1 else ""
            res += f"{icon} {n['title']}{count_str} - {n['point']}\n"
        res += "\n"

    if health < 90:
        res += "⚠️ *Alerta:* La salud general está bajo el umbral del 90%.\n"

    res = add_suggestions(res, context="GLOBAL")
    return res


def get_recent_notifications(limit=10):
    """Obtiene y agrupa las últimas notificaciones importantes generadas por el sistema."""
    from collections import Counter

    from api.telemetry.models.catchment_points import NotificationsCatchment

    notifs = (
        NotificationsCatchment.objects.filter(is_active=True)
        .select_related("point_catchment", "point_catchment__project__client")
        .order_by("-id")[: limit * 2]
    )  # Pedir más para agrupar

    if not notifs.exists():
        return "✅ No hay notificaciones o alertas recientes activas en el sistema."

    res = f"🔔 *Últimas Notificaciones del Sistema*\n\n"

    # Agrupar por (Punto, Título)
    grouped = {}
    for n in notifs:
        key = (n.point_catchment.id, n.title)
        if key not in grouped:
            grouped[key] = {
                "title": n.title,
                "point": n.point_catchment.title,
                "client": (
                    n.point_catchment.project.client.name
                    if n.point_catchment.project
                    else "N/A"
                ),
                "type": n.type_notification,
                "count": 1,
                "message": n.message,
            }
        else:
            grouped[key]["count"] += 1

    # Mostrar limit resultados agrupados
    count_limit = 0
    for key in grouped:
        if count_limit >= limit:
            break
        n = grouped[key]
        tipo_icon = "🚨" if n["type"] == "CRITICAL" else "⚠️"

        reinicio_str = f" ({n['count']} veces)" if n["count"] > 1 else ""
        res += f"{tipo_icon} *{n['title']}*{reinicio_str}\n"
        res += f"   📍 {n['point']} ({n['client']})\n"
        if n["count"] == 1:
            res += f"   📝 {n['message'][:100]}\n\n"
        else:
            res += "\n"
        count_limit += 1

    res = add_suggestions(res, context="GLOBAL")
    return res


# ========== FASE 2: ANÁLISIS Y COMPARACIÓN ==========


def compare_points(point1_query, point2_query, context_client=None):
    """Compara dos puntos de captación en sus últimas mediciones."""
    from api.telemetry.models.catchment_points import CatchmentPoint

    p1_results = search_points(point1_query, context_client)
    p2_results = search_points(point2_query, context_client)

    if not p1_results or not p2_results:
        return f"No pude encontrar uno o ambos puntos para comparar ('{point1_query}' y '{point2_query}')."

    if len(p1_results) > 1 or len(p2_results) > 1:
        res = "Encontré múltiples coincidencias. Sé más específico:\n"
        if len(p1_results) > 1:
            res += (
                f"Búsqueda 1 ({point1_query}): "
                + ", ".join([p["title"] for p in p1_results[:3]])
                + "\n"
            )
        if len(p2_results) > 1:
            res += f"Búsqueda 2 ({point2_query}): " + ", ".join(
                [p["title"] for p in p2_results[:3]]
            )
        return res

    point1 = CatchmentPoint.objects.get(id=p1_results[0]["id"])
    point2 = CatchmentPoint.objects.get(id=p2_results[0]["id"])

    latest1 = (
        TelemetryRecord.objects.filter(point=point1).order_by("-timestamp").first()
    )
    latest2 = (
        TelemetryRecord.objects.filter(point=point2).order_by("-timestamp").first()
    )

    if not latest1 or not latest2:
        return "Uno de los puntos no tiene mediciones recientes para comparar."

    def safe_f(val):
        return float(val) if val else 0.0

    res = f"📊 *Comparativa: {point1.title} vs {point2.title}*\n"
    res += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    # Caudal
    d1, d2 = latest1.data, latest2.data
    q1, q2 = safe_f(d1.get("flow", d1.get("caudal", 0))), safe_f(
        d2.get("flow", d2.get("caudal", 0))
    )
    diff_q = q1 - q2
    icon_q = "🔼" if diff_q > 0 else "🔽" if diff_q < 0 else "⏺️"
    res += f"💧 *Caudal (Q):*\n"
    res += f"   • {point1.title}: {round(q1,2)} L/s\n"
    res += f"   • {point2.title}: {round(q2,2)} L/s\n"
    res += f"   {icon_q} Diff: {round(abs(diff_q),2)} L/s\n\n"

    # Nivel
    n1, n2 = safe_f(d1.get("nivel", 0)), safe_f(d2.get("nivel", 0))
    diff_n = n1 - n2
    res += f"📏 *Nivel (mt):*\n"
    res += f"   • {point1.title}: {round(n1,2)} mt\n"
    res += f"   • {point2.title}: {round(n2,2)} mt\n"
    res += f"   ↔️ Diff: {round(abs(diff_n),2)} mt\n\n"

    # Totalizado (24h)
    from datetime import datetime, timedelta

    yesterday = datetime.now() - timedelta(days=1)

    def get_cons(p):
        rec = TelemetryRecord.objects.filter(
            point=p, timestamp__gte=yesterday
        ).order_by("timestamp")
        if rec.count() >= 2:
            return safe_f(rec.last().data.get("total")) - safe_f(
                rec.first().data.get("total")
            )
        return 0.0

    c1, c2 = get_cons(point1), get_cons(point2)
    res += f"📈 *Consumo últimas 24h:*\n"
    res += f"   • {point1.title}: {int(c1)} m³\n"
    res += f"   • {point2.title}: {int(c2)} m³\n"

    res = add_suggestions(
        res, context="POINT", point=point1.title, client=context_client
    )
    return res


def get_client_stats(client_query, days=7):
    """Genera estadísticas agregadas para un cliente en un período."""
    from datetime import datetime, timedelta

    from django.db.models import Avg, Max, Sum

    from api.telemetry.models.catchment_points import CatchmentPoint, Client

    clients = Client.objects.filter(name__icontains=client_query)
    if not clients.exists():
        return f"No encontré al cliente '{client_query}'."
    client = clients.first()

    points = CatchmentPoint.objects.filter(
        project__client=client, data_config_profiles__is_telemetry=True
    )
    start_date = datetime.now() - timedelta(days=days)

    stats = TelemetryRecord.objects.filter(
        point__in=points, timestamp__gte=start_date
    ).aggregate(
        avg_flow=Avg("data__flow"),
        max_flow=Max("data__flow"),
        total_m3=Sum("data__total_diff"),
    )

    if not stats["total_m3"]:
        return f"No hay datos suficientes para generar estadísticas de {client.name}."

    res = f"📈 *Estadísticas: {client.name}*\n"
    res += f"Período: Últimos {days} días\n"
    res += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    res += f"💧 *Caudal (Q):*\n"
    res += f"   • Promedio: {round(float(stats['avg_flow'] or 0), 2)} L/s\n"
    res += f"   • Máximo: {round(float(stats['max_flow'] or 0), 2)} L/s\n\n"

    res += f"🚜 *Consumo Total:* {int(stats['total_m3'] or 0)} m³\n"
    res += f"   • Promedio Diario: {int((stats['total_m3'] or 0) / days)} m³/día\n"

    res = add_suggestions(res, context="STATS", client=client.name)
    return res


def get_client_ranking(client_query, metric="CONSUME", days=1):
    """Genera un ranking de puntos por consumo o caudal."""
    from datetime import datetime, timedelta

    from django.db.models import Max, Sum

    from api.telemetry.models.catchment_points import CatchmentPoint, Client

    clients = Client.objects.filter(name__icontains=client_query)
    if not clients.exists():
        return f"No encontré al cliente '{client_query}'."
    client = clients.first()

    start_date = datetime.now() - timedelta(days=days)
    points = CatchmentPoint.objects.filter(
        project__client=client, data_config_profiles__is_telemetry=True
    )

    ranking = []
    for p in points:
        data = TelemetryRecord.objects.filter(
            point=p, timestamp__gte=start_date
        ).aggregate(
            val=Sum("data__total_diff") if metric == "CONSUME" else Max("data__flow")
        )
        if data["val"]:
            ranking.append({"title": p.title, "val": float(data["val"])})

    ranking = sorted(ranking, key=lambda x: x["val"], reverse=True)

    unit = "m³" if metric == "CONSUME" else "L/s"
    label = "Consumo" if metric == "CONSUME" else "Caudal Máx"

    res = f"🏆 *Ranking SmartHydro: {client.name}*\n"
    res += f"Criterio: {label} ({days}d)\n"
    res += f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for i, item in enumerate(ranking[:5], 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
        res += f"{medal} {item['title']}: {int(item['val']) if unit=='m³' else round(item['val'],2)} {unit}\n"

    res = add_suggestions(res, context="STATS", client=client.name)
    return res


def get_stuck_points(client_query):
    """Detecta puntos que no han tenido variación en su totalizado en las últimas 24h."""
    from datetime import datetime, timedelta

    from api.telemetry.models.catchment_points import CatchmentPoint, Client

    clients = Client.objects.filter(name__icontains=client_query)
    if not clients.exists():
        return f"No encontré al cliente '{client_query}'."
    client = clients.first()

    points = CatchmentPoint.objects.filter(
        project__client=client, data_config_profiles__is_telemetry=True
    )
    yesterday = datetime.now() - timedelta(days=1)

    stuck = []
    for p in points:
        records = TelemetryRecord.objects.filter(
            point=p, timestamp__gte=yesterday
        ).order_by("timestamp")
        if records.count() >= 5:
            first = float(records.first().data.get("total") or 0)
            last = float(records.last().data.get("total") or 0)
            # Si el totalizado es igual después de 24h pero mayor que 0
            if first > 0 and first == last:
                stuck.append(p.title)

    if not stuck:
        return f"✅ Todos los puntos de *{client.name}* presentan variación de datos."

    res = f"⚠️ *Alerta: Puntos sin Variación (24h)*\n"
    res += f"Cliente: {client.name}\n\n"
    res += "Los siguientes puntos no han sumado m³ en las últimas 24h:\n"
    for s in stuck:
        res += f"   • {s}\n"
    res += "\n💡 *Sugerencia:* Revisa si el sensor de pulsos está desconectado o bloqueado."

    res = add_suggestions(res, context="STATS", client=client.name)
    return res


def add_suggestions(res, context="GLOBAL", client=None, point=None):
    """Añade una sección de sugerencias al final de la respuesta para guiar al usuario."""
    res += "\n💡 *Sugerencias:* "

    if context == "GLOBAL":
        res += "Ver [NOTIFICACIONES] | Estado de un [CLIENTE]"
    elif context == "CLIENT":
        res += f"Ver [MEDICIONES] de {client} | [STATS] semanales | [ALERTAS] activas"
    elif context == "PROJECT":
        res += f"Ver [MEDICIONES] de todo el cliente | [STATS] de {client}"
    elif context == "POINT":
        res += f"Ver [HISTORIAL] de {point} | [CONFIG] técnica | [DGA] normativa"
    elif context == "STATS":
        res += f"Ver [RANKING] de {client} | Buscar [ANOMALIAS]"

    return res


def get_help_menu():
    """
    Retorna un menú de ayuda mejorado con comandos y ejemplos.
    ✅ FASE 2: Sistema de comandos guiados por tipo de usuario.
    """
    res = "🤖 *Asistente SmartHydro - Centro de Comandos*\n"
    res += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    # Sección de comandos rápidos
    res += "⚡ *COMANDOS RÁPIDOS*\n"
    res += "┌────────────────────────────────\n"
    res += "│ `/estado` → Boletín de desconexiones\n"
    res += "│ `/alertas` → Últimas notificaciones\n"
    res += "│ `/metricas` → Rendimiento del bot\n"
    res += "│ `/limpiar` → Reiniciar contexto\n"
    res += "└────────────────────────────────\n\n"

    # Para usuarios internos (Soporte SmartHydro)
    res += "👨‍💻 *PARA SOPORTE INTERNO*\n"
    res += "```\n"
    res += '• "estado" o "drama" → Ver todos los puntos caídos\n'
    res += '• "alertas" → Notificaciones recientes del sistema\n'
    res += '• "DGA Iansa" → Cumplimiento y vouchers de un cliente\n'
    res += '• "anomalías Essbio" → Puntos sin variación\n'
    res += '• "ranking Iansa" → Top consumo de un cliente\n'
    res += '• "compara P1 con P4" → Comparar dos puntos\n'
    res += "```\n\n"

    # Para clientes externos
    res += "👤 *PARA CLIENTES*\n"
    res += "```\n"
    res += '• "Iansa Chillán P4" → Ver mediciones de un punto\n'
    res += '• "mediciones Chillán" → Todos los puntos del proyecto\n'
    res += '• "historial P4" → Últimos 7 días de datos\n'
    res += '• "config P4" → Ver escalas y configuración\n'
    res += '• "cómo viene P4" → Análisis de tendencia\n'
    res += '• "DGA P4" → Estado de cumplimiento del punto\n'
    res += "```\n\n"

    # Flujo conversacional
    res += "💬 *FLUJO CONVERSACIONAL*\n"
    res += "Puedo recordar tu contexto:\n"
    res += "1️⃣ Escribe: `Iansa` (selecciona cliente)\n"
    res += "2️⃣ Luego: `mediciones` (usa contexto de Iansa)\n"
    res += "3️⃣ Luego: `P4` (ver punto específico)\n"
    res += "4️⃣ Luego: `historial` (historial de ese punto)\n\n"

    res += '💡 Escribe **"estado"** para comenzar con el boletín global.'

    return res


def get_timeseries_analysis(point_name, window_days=7, context_client=None):
    """Analiza tendencias de series de tiempo para un punto específico."""
    from datetime import timedelta

    from django.db.models import Avg, Max, Min, Sum
    from django.utils import timezone

    point = search_points(point_name, context_client=context_client)
    if not point:
        return f"No encontré el punto '{point_name}' para el análisis de tendencias."

    point_id = point[0]["id"]
    point_obj = CatchmentPoint.objects.get(id=point_id)

    now = timezone.now()
    start_date = now - timedelta(days=window_days)
    prev_start_date = start_date - timedelta(days=window_days)

    # 1. Obtener datos actuales
    current_data = TelemetryRecord.objects.filter(
        point_id=point_id, timestamp__range=(start_date, now)
    ).order_by("timestamp")

    # 2. Obtener datos anteriores para comparar
    prev_data = TelemetryRecord.objects.filter(
        point_id=point_id, timestamp__range=(prev_start_date, start_date)
    ).aggregate(
        total_prev=Sum("data__total_diff"),
        avg_flow_prev=Avg("data__flow"),
        avg_nivel_prev=Avg("data__nivel"),
    )

    if not current_data.exists():
        return f"No hay datos suficientes en los últimos {window_days} días para un análisis de tendencias."

    stats = current_data.aggregate(
        total_curr=Sum("data__total_diff"),
        avg_flow_curr=Avg("data__flow"),
        avg_nivel_curr=Avg("data__nivel"),
        max_flow=Max("data__flow"),
        min_nivel=Min("data__nivel"),
    )

    res = f"📈 *Análisis de Tendencias: {point_obj.title}*\n"
    res += f"⏱️ Período: Últimos {window_days} días vs periodo anterior\n"
    res += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    # Análisis de Consumo (m³)
    curr_t = float(stats["total_curr"] or 0)
    prev_t = float(prev_data["total_prev"] or 0)
    if prev_t > 0:
        diff_p = ((curr_t - prev_t) / prev_t) * 100
        icon = "🔺" if diff_p > 5 else ("🔹" if diff_p < -5 else "📉")
        res += f"💧 *Consumo*: {int(curr_t)} m³ ({icon} {round(diff_p, 1)}%)\n"
    else:
        res += f"💧 *Consumo*: {int(curr_t)} m³\n"

    # Análisis de Caudal (L/s)
    curr_q = float(stats["avg_flow_curr"] or 0)
    prev_q = float(prev_data["avg_flow_prev"] or 0)
    if prev_q > 0:
        diff_q = ((curr_q - prev_q) / prev_q) * 100
        trend = "al alza" if diff_q > 2 else ("a la baja" if diff_q < -2 else "estable")
        res += f"🌊 *Caudal Prom*: {round(curr_q, 2)} L/s ({trend})\n"

    # Análisis de Nivel (mt)
    curr_n = float(stats["avg_nivel_curr"] or 0)
    prev_n = float(prev_data["avg_nivel_prev"] or 0)
    if prev_n > 0:
        diff_n = curr_n - prev_n
        if abs(diff_n) > 0.1:
            status = (
                "⚠️ Bajando" if diff_n > 0.2 else "✅ Subiendo"
            )  # En nivel, más metros es más profundo/peor
            res += f"📏 *Nivel Prom*: {round(curr_n, 2)} mt ({status} {round(diff_n, 2)}m)\n"
        else:
            res += f"📏 *Nivel Prom*: {round(curr_n, 2)} mt (Estable)\n"

    res += "\n💡 *Inferencia*: "
    if curr_t > prev_t * 1.2:
        res += "Se detecta un incremento fuerte en la demanda de agua. Revisa si es estacional o una posible fuga."
    elif curr_n > prev_n + 0.5:
        res += "El nivel freático está bajando significativamente. Precaución con la bomba."
    else:
        res += "Comportamiento dentro de los parámetros normales."

    return add_suggestions(
        res,
        context="POINT",
        point=f"{point_obj.title} ({point_obj.project.client.name})",
    )
