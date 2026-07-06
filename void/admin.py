"""Admin registration for void."""
from django.contrib import admin

from void.models import (
    Client,
    ComplianceAuthority,
    ComplianceSubmission,
    Contract,
    CounterResetLog,
    Device,
    DeviceEvent,
    DeviceHardware,
    DeviceVariableConfig,
    Invoice,
    MqttTopicConfig,
    Notification,
    Point,
    PointComplianceProfile,
    PointGroup,
    PointPermission,
    ProcessedReading,
    ProcessingRule,
    ProcessingSchema,
    ProcessingStep,
    Project,
    Provider,
    ProviderEndpoint,
    RawReading,
    SLAEvent,
    SLAPolicy,
    Subscription,
    VoidUserProfile,
)


@admin.register(VoidUserProfile)
class VoidUserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "is_active", "created")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "user__username", "phone")


class PointComplianceProfileInline(admin.TabularInline):
    model = PointComplianceProfile
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "code_internal", "is_active", "created")
    list_filter = ("is_active",)
    search_fields = ("name", "client__name", "code_internal")


@admin.register(Point)
class PointAdmin(admin.ModelAdmin):
    list_display = ("name", "code_internal", "client_fk", "project_fk", "frequency_minutes", "is_active", "migration_status")
    list_filter = ("is_active", "migration_status", "frequency_minutes")
    search_fields = ("name", "code_internal", "client", "project")
    readonly_fields = ("created", "modified")
    inlines = [PointComplianceProfileInline]


@admin.register(PointGroup)
class PointGroupAdmin(admin.ModelAdmin):
    filter_horizontal = ("points",)
    search_fields = ("name",)


@admin.register(PointPermission)
class PointPermissionAdmin(admin.ModelAdmin):
    list_display = ("user", "group", "permission")
    list_filter = ("permission",)


class DeviceVariableConfigInline(admin.TabularInline):
    model = DeviceVariableConfig
    extra = 0


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("point", "provider", "model", "serial_number", "external_id", "is_active")
    list_filter = ("is_active", "provider")
    search_fields = ("serial_number", "external_id", "model")
    inlines = [DeviceVariableConfigInline]


@admin.register(DeviceHardware)
class DeviceHardwareAdmin(admin.ModelAdmin):
    list_display = ("device", "component_type", "model", "serial", "status", "warranty_until")
    list_filter = ("component_type", "status")


@admin.register(DeviceVariableConfig)
class DeviceVariableConfigAdmin(admin.ModelAdmin):
    list_display = ("device", "source_variable", "processing_type", "output_field", "pulses_factor", "is_active")
    list_filter = ("processing_type", "is_active")
    search_fields = ("device__serial_number", "source_variable")
    raw_id_fields = ("custom_schema",)


@admin.register(RawReading)
class RawReadingAdmin(admin.ModelAdmin):
    list_display = ("device", "variable", "timestamp", "raw_value", "is_valid")
    list_filter = ("variable", "is_valid")
    search_fields = ("device__serial_number", "device__external_id")


@admin.register(ProcessedReading)
class ProcessedReadingAdmin(admin.ModelAdmin):
    list_display = ("device", "variable", "timestamp", "total", "flow", "nivel", "is_error")
    list_filter = ("variable", "is_error", "is_reset")


class ProcessingStepInline(admin.TabularInline):
    model = ProcessingStep
    extra = 1


class ProcessingRuleInline(admin.TabularInline):
    model = ProcessingRule
    extra = 1


@admin.register(ProcessingSchema)
class ProcessingSchemaAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "is_template", "is_active")
    list_filter = ("is_template", "is_active")
    inlines = [ProcessingStepInline]


@admin.register(ProcessingStep)
class ProcessingStepAdmin(admin.ModelAdmin):
    list_display = ("schema", "order", "step_type", "name", "is_active")
    list_filter = ("step_type", "is_active")
    inlines = [ProcessingRuleInline]


@admin.register(ProcessingRule)
class ProcessingRuleAdmin(admin.ModelAdmin):
    list_display = ("step", "order", "action", "is_active")
    list_filter = ("action", "is_active")


@admin.register(SLAPolicy)
class SLAPolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "metric", "operator", "threshold", "severity", "is_active")
    list_filter = ("metric", "severity", "is_active")


@admin.register(SLAEvent)
class SLAEventAdmin(admin.ModelAdmin):
    list_display = ("device", "policy", "started_at", "resolved_at", "status")
    list_filter = ("status", "policy__severity")


class ProviderEndpointInline(admin.TabularInline):
    model = ProviderEndpoint
    extra = 1


class MqttTopicConfigInline(admin.TabularInline):
    model = MqttTopicConfig
    extra = 1


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "protocol", "auth_type", "base_url", "is_active")
    list_filter = ("protocol", "auth_type", "is_active")
    search_fields = ("name", "base_url")
    inlines = [ProviderEndpointInline, MqttTopicConfigInline]


@admin.register(ProviderEndpoint)
class ProviderEndpointAdmin(admin.ModelAdmin):
    list_display = ("provider", "endpoint_type", "http_method", "path_template", "is_active")
    list_filter = ("endpoint_type", "http_method", "is_active")
    search_fields = ("provider__name", "path_template")


@admin.register(MqttTopicConfig)
class MqttTopicConfigAdmin(admin.ModelAdmin):
    list_display = ("provider", "topic_template", "qos", "is_active")
    list_filter = ("qos", "is_active")
    search_fields = ("provider__name", "topic_template")


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "tax_id", "status", "contact_email", "created")
    list_filter = ("status",)
    search_fields = ("name", "tax_id", "contact_email")


class SubscriptionInline(admin.TabularInline):
    model = Subscription
    extra = 1


class InvoiceInline(admin.TabularInline):
    model = Invoice
    extra = 0


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("name", "client", "billing_cycle", "amount", "status", "start_date", "end_date")
    list_filter = ("status", "billing_cycle")
    search_fields = ("name", "client__name")
    inlines = [SubscriptionInline, InvoiceInline]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("contract", "point", "status", "start_date", "end_date")
    list_filter = ("status",)
    search_fields = ("contract__name", "point__name")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("contract", "invoice_number", "period_start", "period_end", "due_date", "total_amount", "status")
    list_filter = ("status",)
    search_fields = ("contract__name", "invoice_number")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("category", "recipient_email", "channel", "status", "created")
    list_filter = ("category", "status", "channel")
    search_fields = ("recipient_email", "subject")


@admin.register(CounterResetLog)
class CounterResetLogAdmin(admin.ModelAdmin):
    list_display = ("device", "variable", "reset_type", "timestamp", "last_pulses", "current_pulses")
    list_filter = ("reset_type", "variable")
    search_fields = ("device__serial_number",)
    date_hierarchy = "timestamp"


@admin.register(DeviceEvent)
class DeviceEventAdmin(admin.ModelAdmin):
    list_display = ("device", "event_type", "severity", "timestamp", "is_dispatched")
    list_filter = ("event_type", "severity", "is_dispatched")
    search_fields = ("device__serial_number", "message")
    date_hierarchy = "timestamp"


@admin.register(ComplianceAuthority)
class ComplianceAuthorityAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "protocol", "auth_type", "is_active")
    list_filter = ("protocol", "auth_type", "is_active")
    search_fields = ("code", "name")


@admin.register(PointComplianceProfile)
class PointComplianceProfileAdmin(admin.ModelAdmin):
    list_display = ("point", "authority", "external_code", "type_key", "standard", "is_active")
    list_filter = ("authority", "is_active", "type_key", "standard")
    search_fields = ("point__name", "external_code", "authority__code")


@admin.register(ComplianceSubmission)
class ComplianceSubmissionAdmin(admin.ModelAdmin):
    list_display = ("profile", "status", "attempt_number", "sent_at", "voucher", "tracking_id")
    list_filter = ("status", "profile__authority", "created")
    search_fields = ("profile__point__name", "voucher", "tracking_id")
    date_hierarchy = "created"
    readonly_fields = ("created", "modified")
