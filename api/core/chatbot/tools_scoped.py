"""
Scoped Tools for User-Bound Chatbot Queries
=============================================

Versión de las tools del chatbot que filtran resultados por los puntos
que el usuario tiene permitidos ver (owner_user o users_viewers).

Staff / superusers delegan directamente a las funciones originales.
"""

import logging
from typing import Optional, Set

from api.core.chatbot import tools as original_tools
from api.core.chatbot.user_scope import (
    get_allowed_point_ids,
    get_allowed_clients,
    is_client_allowed,
    is_point_allowed,
)

logger = logging.getLogger(__name__)

# Mensaje genérico cuando no se encuentra nada dentro del alcance del usuario
NOT_FOUND_MSG = "No encontré información relacionada con tu consulta en tus puntos asociados."
ACCESS_DENIED_MSG = "No tienes acceso a esa información."


class ScopedTools:
    """
    Wrapper de tools que restringe consultas a los puntos permitidos del usuario.
    Expone métodos con las mismas firmas que las funciones originales.
    """

    def __init__(self, user):
        self.user = user
        self.is_staff = user.is_staff or user.is_superuser
        self.allowed_ids: Set[int] = get_allowed_point_ids(user)
        self.allowed_clients: list = get_allowed_clients(user)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _filter_points_qs(self, queryset):
        if self.is_staff or not self.allowed_ids:
            return queryset
        return queryset.filter(id__in=self.allowed_ids)

    def _check_client(self, client_name: str) -> bool:
        if self.is_staff:
            return True
        return is_client_allowed(client_name, self.user)

    def _check_point_id(self, point_id: int) -> bool:
        if self.is_staff or not self.allowed_ids:
            return True
        return point_id in self.allowed_ids

    def _search_allowed_point(self, query: str, context_client=None):
        """Busca un punto dentro del alcance permitido del usuario."""
        from api.core.models import CatchmentPoint
        clean = query.strip()

        # 1. Buscar por ID exacto si es numérico
        if clean.isdigit():
            pid = int(clean)
            if self._check_point_id(pid):
                pt = CatchmentPoint.objects.filter(id=pid).select_related(
                    "project", "project__client"
                ).first()
                if pt:
                    return [{"id": pt.id, "title": pt.title,
                             "client": pt.project.client.name if pt.project and pt.project.client else "N/A"}]
            return []

        # 2. Buscar por título exacto (case insensitive) dentro de puntos permitidos
        qs = CatchmentPoint.objects.all()
        if not self.is_staff and self.allowed_ids:
            qs = qs.filter(id__in=self.allowed_ids)

        if context_client:
            qs = qs.filter(project__client__name__icontains=context_client)

        exact = qs.filter(title__iexact=clean).select_related("project", "project__client")
        if exact.count() == 1:
            p = exact.first()
            return [{"id": p.id, "title": p.title,
                     "client": p.project.client.name if p.project and p.project.client else "N/A"}]

        # 3. Buscar por contención
        partial = qs.filter(title__icontains=clean).select_related("project", "project__client")[:10]
        return [{"id": p.id, "title": p.title,
                 "client": p.project.client.name if p.project and p.project.client else "N/A"}
                for p in partial]

    # ------------------------------------------------------------------
    # Tools públicas (mismas firmas que originales)
    # ------------------------------------------------------------------
    def search_points(self, query, context_client=None):
        if self.is_staff:
            return original_tools.search_points(query, context_client)
        return self._search_allowed_point(query, context_client)

    def get_client_summary(self, client_name, project_name=None):
        if not self._check_client(client_name):
            return NOT_FOUND_MSG
        return original_tools.get_client_summary(client_name, project_name)

    def get_project_measurements(self, client_name, project_name):
        if not self._check_client(client_name):
            return NOT_FOUND_MSG
        # Filtrar puntos del proyecto por IDs permitidos
        if not self.is_staff and self.allowed_ids:
            from api.core.models import CatchmentPoint, Client, ProjectCatchments
            clients = Client.objects.filter(name__icontains=client_name)
            if not clients.exists():
                return f"No encontré al cliente '{client_name}'."
            client = clients.first()
            projects = ProjectCatchments.objects.filter(client=client, name__icontains=project_name)
            if not projects.exists():
                return f"No encontré el proyecto '{project_name}' para {client.name}."
            project = projects.first()
            points = CatchmentPoint.objects.filter(project=project, id__in=self.allowed_ids)
            if not points.exists():
                return NOT_FOUND_MSG
            # Reconstruir mensaje manualmente para solo puntos permitidos
            return self._format_project_measurements(project, client, points)
        return original_tools.get_project_measurements(client_name, project_name)

    def _format_project_measurements(self, project, client, points_qs):
        """Reconstrucción local de get_project_measurements filtrada."""
        from api.core.models.interaction_detail import InteractionDetail
        res = f"📊 *Mediciones de {project.name}* ({client.name})\n\n"
        for point in points_qs[:10]:
            latest = InteractionDetail.objects.filter(catchment_point=point).order_by('-date_time_medition').first()
            if latest:
                fecha = (latest.date_time_last_logger or latest.date_time_medition)
                if fecha:
                    fecha = fecha.astimezone(original_tools.chile_tz).strftime("%d/%m %H:%M")
                else:
                    fecha = "N/A"
                vals = []
                if latest.flow:
                    vals.append(f"Q:{latest.flow}L/s")
                if latest.nivel:
                    vals.append(f"N:{latest.nivel}m")
                if latest.total:
                    vals.append(f"T:{latest.total}m³")
                vals_str = " | ".join(vals) if vals else "Sin datos"
                res += f"*{point.title}* ({fecha})\n   {vals_str}\n"
            else:
                res += f"⚪ *{point.title}*: Sin mediciones\n"
        if points_qs.count() > 10:
            res += f"\n... y {points_qs.count() - 10} puntos más."
        return res

    def get_point_latest_data(self, point_id):
        if not self._check_point_id(point_id):
            return ACCESS_DENIED_MSG
        return original_tools.get_point_latest_data(point_id)

    def get_client_measurements(self, client_name):
        if not self._check_client(client_name):
            return NOT_FOUND_MSG
        if not self.is_staff and self.allowed_ids:
            from api.core.models import CatchmentPoint, Client
            clients = Client.objects.filter(name__icontains=client_name)
            if not clients.exists():
                return f"No encontré al cliente '{client_name}'."
            client = clients.first()
            points = CatchmentPoint.objects.filter(
                project__client=client, id__in=self.allowed_ids
            ).select_related('project', 'project__client')
            if not points.exists():
                return NOT_FOUND_MSG
            return self._format_client_measurements(client, points)
        return original_tools.get_client_measurements(client_name)

    def _format_client_measurements(self, client, points_qs):
        from api.core.models.interaction_detail import InteractionDetail
        import pytz
        chile = pytz.timezone("America/Santiago")
        res = f"📊 *Últimas mediciones de {client.name}* ({points_qs.count()} puntos):\n\n"
        for point in points_qs[:10]:
            latest = InteractionDetail.objects.filter(catchment_point=point).order_by('-date_time_medition').first()
            if latest:
                actual = latest.date_time_last_logger or latest.date_time_medition
                fecha = actual.astimezone(chile).strftime("%d/%m %H:%M") if actual else "N/A"
                dias = latest.days_not_conection or 0
                estado = "🔴" if dias > 0 else "🟢"
                vals = []
                if latest.flow:
                    vals.append(f"Q:{latest.flow}L/s")
                if latest.nivel:
                    vals.append(f"N:{latest.nivel}m")
                if latest.total:
                    vals.append(f"T:{latest.total}m³")
                if latest.total_today_diff:
                    vals.append(f"Hoy:{latest.total_today_diff}m³")
                vals_str = " | ".join(vals) if vals else "Sin datos"
                res += f"{estado} *{point.title}* ({fecha})\n   {vals_str}\n"
            else:
                res += f"⚪ *{point.title}*: Sin mediciones\n"
        if points_qs.count() > 10:
            res += f"\n... y {points_qs.count() - 10} puntos más."
        return res

    def get_point_status_summary(self):
        if self.is_staff:
            return original_tools.get_point_status_summary()
        # Reimplementar contando solo puntos permitidos
        from api.core.models import CatchmentPoint, InteractionDetail
        points = CatchmentPoint.objects.filter(
            data_config_profiles__is_telemetry=True, id__in=self.allowed_ids
        )
        total = points.count()
        disconnected = 0
        connected = 0
        for point in points:
            latest = InteractionDetail.objects.filter(catchment_point=point).order_by('-date_time_medition').first()
            dias = float(latest.days_not_conection) if latest and latest.days_not_conection else 0
            if dias > 0:
                disconnected += 1
            else:
                connected += 1
        res = f"📊 *Estado de tus puntos*\n\n"
        res += f"✅ Conectados: {connected}\n"
        res += f"🔴 Desconectados: {disconnected}\n"
        res += f"📍 Total: {total}\n"
        health = round((connected / total * 100), 1) if total > 0 else 0
        res += f"\n💚 Salud: {health}%"
        return res

    def get_dga_compliance(self, client_name):
        if not self._check_client(client_name):
            return NOT_FOUND_MSG
        if not self.is_staff and self.allowed_ids:
            from api.core.models import CatchmentPoint, Client, DgaDataConfigCatchment, InteractionDetail
            clients = Client.objects.filter(name__icontains=client_name)
            if not clients.exists():
                return f"No encontré al cliente '{client_name}'."
            client = clients.first()
            points = CatchmentPoint.objects.filter(project__client=client, id__in=self.allowed_ids)
            configs = DgaDataConfigCatchment.objects.filter(point_catchment__in=points, send_dga=True)
            if not configs.exists():
                return NOT_FOUND_MSG
            res = f"📋 *Cumplimiento DGA — {client.name}* (tus puntos)\n\n"
            for cfg in configs.select_related('point_catchment'):
                pt = cfg.point_catchment
                last = InteractionDetail.objects.filter(
                    catchment_point=pt, n_voucher__isnull=False
                ).order_by('-date_time_medition').first()
                voucher = str(last.n_voucher)[:20] if last and last.n_voucher else "Sin voucher"
                fecha = last.date_time_medition.astimezone(original_tools.chile_tz).strftime("%d/%m %H:%M") if last else "N/A"
                res += f"• *{pt.title}* ({cfg.code_dga or 'Sin código'})\n"
                res += f"  Último envío: {fecha} | Voucher: {voucher}\n\n"
            return res
        return original_tools.get_dga_compliance(client_name)

    def get_point_config(self, point_name, context_client=None):
        # Buscar punto permitido
        found = self.search_points(point_name, context_client)
        if not found:
            return NOT_FOUND_MSG
        # Si hay múltiples, tomar el primero (comportamiento original)
        return original_tools.get_point_config(found[0]["title"], context_client=found[0].get("client"))

    def get_client_alerts(self, client_name):
        if not self._check_client(client_name):
            return NOT_FOUND_MSG
        if not self.is_staff and self.allowed_ids:
            from api.core.models import CatchmentPoint, Client, NotificationsCatchment
            clients = Client.objects.filter(name__icontains=client_name)
            if not clients.exists():
                return f"No encontré al cliente '{client_name}'."
            client = clients.first()
            points = CatchmentPoint.objects.filter(project__client=client, id__in=self.allowed_ids)
            alerts = NotificationsCatchment.objects.filter(
                point_catchment__in=points, is_active=True
            ).select_related('point_catchment').order_by('-created')[:20]
            if not alerts.exists():
                return "No tienes alertas activas en tus puntos."
            res = f"🚨 *Alertas activas — {client.name}*\n\n"
            for a in alerts:
                res += f"• *{a.title}* ({a.point_catchment.title})\n"
                if a.message:
                    res += f"  {a.message[:80]}\n"
            return res
        return original_tools.get_client_alerts(client_name)

    def get_point_history(self, point_name, days=7, context_client=None):
        found = self.search_points(point_name, context_client)
        if not found:
            return NOT_FOUND_MSG
        return original_tools.get_point_history(found[0]["title"], days, context_client=found[0].get("client"))

    def get_client_errors(self, client_name, days=7):
        if not self._check_client(client_name):
            return NOT_FOUND_MSG
        if not self.is_staff and self.allowed_ids:
            from api.core.models import CatchmentPoint, Client, NotificationsCatchment
            clients = Client.objects.filter(name__icontains=client_name)
            if not clients.exists():
                return f"No encontré al cliente '{client_name}'."
            client = clients.first()
            points = CatchmentPoint.objects.filter(project__client=client, id__in=self.allowed_ids)
            errors = NotificationsCatchment.objects.filter(
                point_catchment__in=points,
                type_notification='ERROR',
                created__gte=__import__('django.utils.timezone').utils.timezone.now() - __import__('datetime').timedelta(days=days)
            ).select_related('point_catchment').order_by('-created')[:20]
            if not errors.exists():
                return "No se encontraron errores recientes en tus puntos."
            res = f"⚠️ *Errores recientes — {client.name}*\n\n"
            for e in errors:
                res += f"• {e.title} ({e.point_catchment.title})\n"
            return res
        return original_tools.get_client_errors(client_name, days)

    def get_global_status(self):
        # Para usuarios normales, es equivalente a get_point_status_summary
        return self.get_point_status_summary()

    def get_recent_notifications(self, limit=10):
        if self.is_staff:
            return original_tools.get_recent_notifications(limit)
        from api.core.models import NotificationsCatchment
        notifications = NotificationsCatchment.objects.filter(
            point_catchment__id__in=self.allowed_ids
        ).select_related('point_catchment').order_by('-created')[:limit]
        if not notifications.exists():
            return "No tienes notificaciones recientes."
        res = "🔔 *Notificaciones recientes*\n\n"
        for n in notifications:
            res += f"• *{n.title}* ({n.point_catchment.title if n.point_catchment else 'Sistema'})\n"
            if n.message:
                res += f"  {n.message[:80]}\n"
        return res

    def compare_points(self, point1_query, point2_query, context_client=None):
        p1 = self.search_points(point1_query, context_client)
        p2 = self.search_points(point2_query, context_client)
        if not p1 or not p2:
            return NOT_FOUND_MSG
        return original_tools.compare_points(p1[0]["title"], p2[0]["title"], context_client=context_client)

    def get_client_stats(self, client_query, days=7):
        if not self._check_client(client_query):
            return NOT_FOUND_MSG
        if not self.is_staff and self.allowed_ids:
            from api.core.models import Client, CatchmentPoint, InteractionDetail
            from django.db.models import Avg, Max, Min, Sum
            import pytz
            chile = pytz.timezone("America/Santiago")
            clients = Client.objects.filter(name__icontains=client_query)
            if not clients.exists():
                return f"No encontré al cliente '{client_query}'."
            client = clients.first()
            points = CatchmentPoint.objects.filter(project__client=client, id__in=self.allowed_ids)
            ids = [p.id for p in points]
            if not ids:
                return NOT_FOUND_MSG
            latest_records = InteractionDetail.objects.filter(
                catchment_point__id__in=ids
            ).order_by('catchment_point', '-date_time_medition').distinct('catchment_point')
            total_flow = sum(float(r.flow or 0) for r in latest_records)
            total_consume = sum(float(r.total_today_diff or 0) for r in latest_records)
            avg_flow = total_flow / len(latest_records) if latest_records else 0
            res = f"📈 *Estadísticas — {client.name}* (tus puntos)\n\n"
            res += f"• Caudal total: {total_flow:.2f} L/s\n"
            res += f"• Consumo hoy: {total_consume:.0f} m³\n"
            res += f"• Caudal promedio: {avg_flow:.2f} L/s\n"
            return res
        return original_tools.get_client_stats(client_query, days)

    def get_client_ranking(self, client_query, metric='CONSUME', days=1):
        if not self._check_client(client_query):
            return NOT_FOUND_MSG
        if not self.is_staff and self.allowed_ids:
            from api.core.models import Client, CatchmentPoint, InteractionDetail
            clients = Client.objects.filter(name__icontains=client_query)
            if not clients.exists():
                return f"No encontré al cliente '{client_query}'."
            client = clients.first()
            points = CatchmentPoint.objects.filter(project__client=client, id__in=self.allowed_ids)
            ids = [p.id for p in points]
            if not ids:
                return NOT_FOUND_MSG
            records = InteractionDetail.objects.filter(
                catchment_point__id__in=ids
            ).order_by('catchment_point', '-date_time_medition').distinct('catchment_point')
            data = []
            for r in records:
                val = float(r.total_today_diff or 0) if metric == 'CONSUME' else float(r.flow or 0)
                data.append({"point": r.catchment_point.title, "value": val})
            data.sort(key=lambda x: x["value"], reverse=True)
            label = "Consumo" if metric == 'CONSUME' else "Caudal"
            unit = "m³" if metric == 'CONSUME' else "L/s"
            res = f"🏆 *Ranking {label} — {client.name}*\n\n"
            for i, d in enumerate(data[:10], 1):
                res += f"{i}. {d['point']}: {d['value']:.2f} {unit}\n"
            return res
        return original_tools.get_client_ranking(client_query, metric, days)

    def get_stuck_points(self, client_query):
        if not self._check_client(client_query):
            return NOT_FOUND_MSG
        if not self.is_staff and self.allowed_ids:
            from api.core.models import Client, CatchmentPoint, InteractionDetail
            from django.utils import timezone
            clients = Client.objects.filter(name__icontains=client_query)
            if not clients.exists():
                return f"No encontré al cliente '{client_query}'."
            client = clients.first()
            points = CatchmentPoint.objects.filter(project__client=client, id__in=self.allowed_ids)
            stuck = []
            last_24h = timezone.now() - __import__('datetime').timedelta(hours=24)
            for point in points:
                records = InteractionDetail.objects.filter(
                    catchment_point=point, date_time_medition__gte=last_24h
                ).values_list('total_diff', flat=True)
                if len(records) >= 12 and all(d == 0 or d is None for d in records):
                    stuck.append(point.title)
            if not stuck:
                return "No se detectaron puntos sin variación en tus puntos las últimas 24h. ✅"
            res = f"📉 *Puntos sin variación — {client.name}*\n\n"
            for s in stuck[:15]:
                res += f"• {s}\n"
            return res
        return original_tools.get_stuck_points(client_query)

    def get_timeseries_analysis(self, point_name, window_days=7, context_client=None):
        found = self.search_points(point_name, context_client)
        if not found:
            return NOT_FOUND_MSG
        return original_tools.get_timeseries_analysis(found[0]["title"], window_days, context_client=found[0].get("client"))

    def get_telemetry_audit(self, days=30, show_all=True):
        if self.is_staff:
            return original_tools.get_telemetry_audit(days, show_all)
        # Para usuarios normales, audit solo sobre sus puntos
        from api.core.models import CatchmentPoint, InteractionDetail
        from django.utils import timezone
        points = CatchmentPoint.objects.filter(id__in=self.allowed_ids, data_config_profiles__is_telemetry=True)
        since = timezone.now() - __import__('datetime').timedelta(days=days)
        res = f"🔍 *Auditoría de tus puntos* (últimos {days} días)\n\n"
        issues = []
        for point in points:
            latest = InteractionDetail.objects.filter(catchment_point=point).order_by('-date_time_medition').first()
            if latest and latest.days_not_conection and latest.days_not_conection > 0:
                issues.append(f"• {point.title}: desconectado ({latest.days_not_conection} días)")
            recs = InteractionDetail.objects.filter(catchment_point=point, date_time_medition__gte=since).values_list('total_diff', flat=True)
            if len(recs) >= 12 and all(d == 0 or d is None for d in recs):
                issues.append(f"• {point.title}: sin variación >24h")
        if not issues:
            res += "✅ No se detectaron anomalías en tus puntos."
        else:
            res += "\n".join(issues[:20])
        return res

    def get_help_menu(self):
        # Help es global, no filtra datos sensibles
        return original_tools.get_help_menu()

    def add_suggestions(self, res, context="GLOBAL", client=None, point=None):
        return original_tools.add_suggestions(res, context, client, point)
