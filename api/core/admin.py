from datetime import datetime
import pytz
from django.urls import reverse
# Django
from django.contrib import admin
# Models
from django.utils.safestring import mark_safe
from django.db.models import F, Max
from django.db.models.functions import TruncMonth
from api.core.models import (
    InteractionDetail, User, Client, ProjectCatchments, CatchmentPoint,
    ProfileDataConfigCatchment, ProfileIkoluCatchment, DgaDataConfigCatchment,
    SchemesCatchment, Variable, RegisterPersons, NotificationsCatchment,
    ResponseNotificationsCatchment, TypeFileCatchment, FileCatchment
)
from import_export.admin import ImportExportModelAdmin, ExportActionMixin


class UserAdm(ExportActionMixin, admin.ModelAdmin):
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
    )
    search_fields = ('email', )
    ordering = ('-created',)
    def save_model(self, request, obj, form, change):
        if obj.password == "pbkdf2" + "*":
            obj.password=obj.password
        else:
            obj.set_password(obj.password)
        super().save_model(request, obj, form, change)

admin.site.register(User, UserAdm)

@admin.register(InteractionDetail)
class InteractionDetailAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('catchment_point','is_error',
                    'date_time_medition', 'days_not_conection', 'pulses', 'total', 'total_diff', 'total_today_diff', 'nivel', 'water_table', 'flow', 'send_dga', 'n_voucher')
    date_hierarchy = 'date_time_medition'
    
    class HasVoucherFilter(admin.SimpleListFilter):
        title = 'Enviado a DGA'
        parameter_name = 'has_voucher'

        def lookups(self, request, model_admin):
            return (
                ('yes', 'SI'),
                ('no', 'NO'),
            )

        def queryset(self, request, queryset):
            if self.value() == 'yes':
                return queryset.exclude(n_voucher__isnull=True).exclude(n_voucher__exact='')
            if self.value() == 'no':
                return queryset.filter(n_voucher__isnull=True) | queryset.filter(n_voucher__exact='')

    list_filter = ('send_dga', 'date_time_medition','catchment_point',
                   'catchment_point__project__name', 'is_error', HasVoucherFilter)
       


@admin.register(Client)
class ClientAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('id', 'name', 'created')
    search_fields = ('name', )
    list_filter = ('created',)


@admin.register(ProjectCatchments)
class ProjectCatchmentsAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('id', 'client', 'name', 'code_internal', 'created')
    search_fields = ('name', 'client__name')
    list_filter = ('created',)


@admin.register(CatchmentPoint)
class CatchmentPointAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('id', 'title', 'last_interaction_detail','owner_user','frecuency')
    
    class HasDisconnectionFilter(admin.SimpleListFilter):
        title = 'Días de desconexión'
        parameter_name = 'disconnection_days'

        def lookups(self, request, model_admin):
            return (
                ('disconnected', 'Puntos sin conexión'),
            )

        def queryset(self, request, queryset):
            if self.value() == 'disconnected':
                # Get the latest interaction for each catchment point
                latest_interactions = InteractionDetail.objects.filter(
                    catchment_point__in=queryset
                ).values('catchment_point').annotate(
                    latest_date=Max('date_time_medition')
                )
                
                # Filter points where the latest interaction has days_not_conection > 0
                disconnected_points = []
                for interaction in latest_interactions:
                    latest = InteractionDetail.objects.filter(
                        catchment_point_id=interaction['catchment_point'],
                        date_time_medition=interaction['latest_date'],
                        days_not_conection__gt=0,
                        days_not_conection__isnull=False
                    ).exists()
                    if latest:
                        disconnected_points.append(interaction['catchment_point'])
                
                return queryset.filter(id__in=disconnected_points)
            return queryset


    search_fields = ('title', 'project__name')
    list_filter = (HasDisconnectionFilter, "frecuency",'is_novus', 'is_thethings', 'is_tdata', 'project__name')
    

    def last_interaction_detail(self, obj):
        last_interaction = InteractionDetail.objects.filter(
            catchment_point=obj).order_by('date_time_medition').last()
        chile = pytz.timezone("America/Santiago")
        date_time_medition_cl = None
        date_time_medition_logger = None
        if last_interaction:
            date_time_medition_cl = last_interaction.date_time_medition.astimezone(chile)
            date_time_medition_logger = last_interaction.date_time_last_logger
        if last_interaction:
            return mark_safe("<ul>{}</ul>".format("".join(["<li>logger:{}</li><li>medicion:{}</li><li>total: {}</li><li>caudal :{}</li><li>nivel: {}</li><li>desconexion: {}</li>".format(date_time_medition_logger,date_time_medition_cl, last_interaction.total, last_interaction.flow, last_interaction.nivel, last_interaction.days_not_conection)])))
        return None
    
    last_interaction_detail.short_description = 'Última medición'


@admin.register(ProfileDataConfigCatchment)
class ProfileDataConfigCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('id', 'point_catchment',
                    'token_service', 'd3', 'is_telemetry')
    list_filter = ('is_telemetry', 'point_catchment__project__name',)


@admin.register(ProfileIkoluCatchment)
class ProfileIkoluCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('id', 'point_catchment', 'm1',
                    'm2', 'm3', 'm4', 'm5', 'm6', 'm7')
    list_filter = ('entry_by_form',)


@admin.register(DgaDataConfigCatchment)
class DgaDataConfigCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('id', 'point_catchment',
                    'standard', 'code_dga', 'flow_granted_dga', 'total_granted_dga',
                    'date_start_compliance', 'date_created_code', 'send_dga',
                    )
    list_filter = ('standard', 'point_catchment__project__name',)


@admin.register(SchemesCatchment)
class SchemesCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('id', 'name', 'get_points_catchment', 'get_variables')

    def get_points_catchment(self, obj):
        points = obj.points_catchment.all()
        return mark_safe("<ul>{}</ul>".format("".join(["<li>{}</li>".format(point) for point in points])))
    get_points_catchment.short_description = 'Puntos de captación'

    def get_variables(self, obj):
        variables = obj.variables.all()
        return mark_safe("<ul>{}</ul>".format("".join(["<li>{}: {}</li>".format(variable.type_variable, variable.str_variable) for variable in variables])))
    get_variables.short_description = 'Variables'


@admin.register(Variable)
class VariableAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('id', 'scheme_catchment',
                    'str_variable', 'label', 'service', 'type_variable')
    list_filter = ('scheme_catchment__name', 'service', 'type_variable')


@admin.register(NotificationsCatchment)
class NotificationsCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('id', 'point_catchment', 'title', 'message',
                    'type_notification', 'created')
    list_filter = ('created', 'point_catchment__title',
                   'point_catchment__project__name', 'type_notification')


@admin.register(ResponseNotificationsCatchment)
class ResponseNotificationsCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('id', 'notification',
                    'user', 'response', 'created')
    list_filter = ('created', 'notification__title',
                   'notification__point_catchment__title',)


@admin.register(TypeFileCatchment)
class TypeFileCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('id', 'name', 'internal', 'created')
    list_filter = ('created',)


@admin.register(FileCatchment)
class FileCatchmentAdmin(ImportExportModelAdmin, ExportActionMixin, admin.ModelAdmin):
    list_display = ('id', 'name', 'point_catchment',
                    'type_file', 'file', 'created')
    list_filter = ('created', 'point_catchment__title',
                   'type_file__name', 'point_catchment__project__name')


admin.site.register(RegisterPersons)

# Acción personalizada agregada al InteractionDetailAdmin
def agregar_registros_cola_dga(modeladmin, request, queryset):
    """Agregar registros seleccionados a la cola de envío DGA"""
    updated = queryset.filter(send_dga=False).update(send_dga=True)
    if updated > 0:
        modeladmin.message_user(request, f'{updated} registros agregados a la cola DGA.')
    else:
        modeladmin.message_user(request, 'Ningún registro válido para agregar.', level='warning')

agregar_registros_cola_dga.short_description = 'Agregar a cola DGA'

# Agregar la acción al admin

# Función para remover registros de la cola DGA  
def remover_registros_cola_dga(modeladmin, request, queryset):
    """Remover registros seleccionados de la cola de envío DGA"""
    updated = queryset.filter(send_dga=True).update(send_dga=False)
    if updated > 0:
        modeladmin.message_user(request, f'{updated} registros removidos de la cola DGA.')
    else:
        modeladmin.message_user(request, 'Ningún registro válido para remover.', level='warning')

remover_registros_cola_dga.short_description = 'Remover de cola DGA'

# Asignar ambas acciones al admin
InteractionDetailAdmin.actions = [agregar_registros_cola_dga, remover_registros_cola_dga]
