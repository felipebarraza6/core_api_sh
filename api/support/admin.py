from django.contrib import admin
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html

from .models import SupportTicket, TicketComment, TicketSLA


class TicketCommentInline(admin.StackedInline):
    model = TicketComment
    fields = ['author', 'comment', 'is_internal', 'created']
    readonly_fields = ['created']
    extra = 0
    can_delete = False


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    """Admin avanzado para gestión de tickets de soporte"""

    list_display = [
        'ticket_number', 'title', 'status_badge', 'priority_badge',
        'category', 'created_by', 'assigned_to', 'opened_at', 'days_open'
    ]

    list_filter = [
        'status', 'priority', 'category', 'assigned_to',
        ('opened_at', admin.DateFieldListFilter),
        ('due_date', admin.DateFieldListFilter),
    ]

    search_fields = ['ticket_number', 'title', 'description', 'created_by__email']

    readonly_fields = [
        'ticket_number', 'opened_at', 'resolved_at', 'closed_at',
        'resolution_time_hours', 'days_open'
    ]

    fieldsets = (
        ('Información Básica', {
            'fields': ('ticket_number', 'title', 'description')
        }),
        ('Estado y Prioridad', {
            'fields': ('status', 'priority', 'category')
        }),
        ('Asignación', {
            'fields': ('created_by', 'assigned_to')
        }),
        ('Fechas', {
            'fields': ('opened_at', 'due_date', 'resolved_at', 'closed_at', 'resolution_time_hours')
        }),
        ('Recursos Afectados', {
            'fields': ('affected_devices', 'affected_points')
        }),
        ('Información Adicional', {
            'fields': ('tags', 'attachments', 'custom_fields'),
            'classes': ('collapse',)
        }),
        ('Métricas', {
            'fields': ('days_open', 'customer_satisfaction'),
            'classes': ('collapse',)
        }),
    )

    inlines = [TicketCommentInline]

    actions = [
        'assign_to_me', 'mark_in_progress', 'mark_resolved', 'close_ticket',
        'set_high_priority', 'set_critical_priority', 'add_followup_required'
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'affected_devices', 'affected_points', 'comments'
        )

    def status_badge(self, obj):
        colors = {
            'OPEN': 'blue',
            'IN_PROGRESS': 'orange',
            'WAITING_CUSTOMER': 'yellow',
            'WAITING_SUPPLIER': 'purple',
            'RESOLVED': 'green',
            'CLOSED': 'gray'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.8em;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Estado'

    def priority_badge(self, obj):
        colors = {
            'LOW': 'green',
            'NORMAL': 'blue',
            'HIGH': 'orange',
            'CRITICAL': 'red',
            'EMERGENCY': 'darkred'
        }
        color = colors.get(obj.priority, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.8em;">{}</span>',
            color, obj.get_priority_display()
        )
    priority_badge.short_description = 'Prioridad'

    def days_open(self, obj):
        return obj.days_open
    days_open.short_description = 'Días Abierto'

    # Actions
    def assign_to_me(self, request, queryset):
        updated = 0
        for ticket in queryset.filter(assigned_to__isnull=True):
            ticket.assign_to(request.user)
            updated += 1
        self.message_user(request, f"{updated} tickets asignados a ti")

    def mark_in_progress(self, request, queryset):
        updated = queryset.filter(status='OPEN').update(
            status='IN_PROGRESS',
            assigned_to=request.user
        )
        self.message_user(request, f"{updated} tickets marcados en progreso")

    def mark_resolved(self, request, queryset):
        updated = 0
        for ticket in queryset.filter(status__in=['OPEN', 'IN_PROGRESS']):
            ticket.resolve(request.user, "Resuelto desde admin")
            updated += 1
        self.message_user(request, f"{updated} tickets resueltos")

    def close_ticket(self, request, queryset):
        updated = queryset.filter(status='RESOLVED').update(
            status='CLOSED',
            closed_at=timezone.now()
        )
        self.message_user(request, f"{updated} tickets cerrados")

    def set_high_priority(self, request, queryset):
        updated = queryset.update(priority='HIGH')
        self.message_user(request, f"{updated} tickets marcados como alta prioridad")

    def set_critical_priority(self, request, queryset):
        updated = queryset.update(priority='CRITICAL')
        self.message_user(request, f"{updated} tickets marcados como críticos")

    def add_followup_required(self, request, queryset):
        # Agregar tag de seguimiento requerido
        for ticket in queryset:
            tags = ticket.tags or []
            if 'followup_required' not in tags:
                tags.append('followup_required')
                ticket.tags = tags
                ticket.save()
        self.message_user(request, f"Tag 'followup_required' agregado a {queryset.count()} tickets")


@admin.register(TicketSLA)
class TicketSLAAdmin(admin.ModelAdmin):
    """Admin para gestión de SLAs de tickets"""

    list_display = [
        'name', 'category', 'priority', 'response_time_hours',
        'resolution_time_hours', 'is_active'
    ]

    list_filter = ['category', 'priority', 'is_active']
    search_fields = ['name', 'category', 'priority']

    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'category', 'priority')
        }),
        ('Tiempos', {
            'fields': ('response_time_hours', 'resolution_time_hours')
        }),
        ('Penalizaciones', {
            'fields': ('penalty_per_hour',)
        }),
        ('Configuración', {
            'fields': ('is_active', 'business_hours_only')
        }),
    )