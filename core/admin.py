from django.contrib import admin
from .models import (
    AppCatalog, AuditLog, Command, EmployeeProfile, InstalledApp, Machine,
    Notification, SoftwareRequest, SupportTicket, TicketAttachment, TicketMessage,
    NetworkPolicy, MachineAppPolicy, UnauthorizedSoftware, DetectedSoftware, DeviceMetric, PowerEvent, DevicePairingCode, AgentTask,
)


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "device_type", "policy", "enabled", "last_seen")
    search_fields = ("name", "branch", "ip_address", "serial_number")
    list_filter = ("policy", "enabled", "device_type", "branch")
    readonly_fields = ("id", "enrolled_at", "last_seen", "agent_key_hash", "agent_key_rotated_at")


@admin.register(AppCatalog)
class AppCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "latest_version", "winget_id", "enabled")
    search_fields = ("name", "slug", "winget_id")
    list_filter = ("enabled",)


@admin.register(InstalledApp)
class InstalledAppAdmin(admin.ModelAdmin):
    list_display = ("machine", "app", "version", "last_reported")
    search_fields = ("machine__name", "app__name", "version")


@admin.register(Command)
class CommandAdmin(admin.ModelAdmin):
    list_display = ("id", "machine", "app", "action", "status", "requested_by", "requested_at")
    list_filter = ("action", "status")
    search_fields = ("machine__name", "app__name", "result_message")
    readonly_fields = ("id", "requested_at", "started_at", "completed_at")


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "employee_code", "department", "branch", "assigned_machine")
    search_fields = ("user__username", "user__first_name", "user__last_name", "employee_code", "department", "branch")
    list_filter = ("branch", "department")


@admin.register(SoftwareRequest)
class SoftwareRequestAdmin(admin.ModelAdmin):
    list_display = ("requested_at", "employee", "app", "machine", "status", "reviewed_by")
    search_fields = ("employee__username", "employee__first_name", "app__name", "machine__name", "reason")
    list_filter = ("status", "app", "machine__branch")
    readonly_fields = ("id", "requested_at", "reviewed_at", "completed_at")


class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 0
    readonly_fields = ("author", "body", "created_at")
    can_delete = False


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("created_at", "subject", "employee", "category", "priority", "status", "assigned_to")
    search_fields = ("subject", "description", "employee__username", "employee__first_name", "machine__name")
    list_filter = ("status", "priority", "category", "machine__branch")
    readonly_fields = ("id", "created_at", "updated_at", "resolved_at")
    inlines = [TicketMessageInline]


@admin.register(TicketAttachment)
class TicketAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "original_name", "size", "uploaded_at")
    readonly_fields = ("id", "message", "file", "original_name", "content_type", "size", "uploaded_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "kind", "title", "is_read")
    search_fields = ("user__username", "title", "message")
    list_filter = ("kind", "is_read")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event", "kind", "actor", "machine", "ip_address")
    list_filter = ("kind", "event")
    search_fields = ("message", "machine__name", "actor__username")
    readonly_fields = ("created_at",)


@admin.register(NetworkPolicy)
class NetworkPolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "mode", "revision", "enabled", "updated_at")
    list_filter = ("mode", "enabled")


@admin.register(MachineAppPolicy)
class MachineAppPolicyAdmin(admin.ModelAdmin):
    list_display = ("machine", "app", "mode", "auto_update", "updated_at")
    list_filter = ("mode", "auto_update")
    search_fields = ("machine__name", "app__name")


@admin.register(UnauthorizedSoftware)
class UnauthorizedSoftwareAdmin(admin.ModelAdmin):
    list_display = ("machine", "display_name", "version", "publisher", "resolved", "last_seen")
    list_filter = ("resolved", "machine__branch")
    search_fields = ("machine__name", "display_name", "publisher")


@admin.register(DetectedSoftware)
class DetectedSoftwareAdmin(admin.ModelAdmin):
    list_display = ("machine", "display_name", "version", "publisher", "classification", "last_seen")
    list_filter = ("classification", "machine__branch")
    search_fields = ("machine__name", "display_name", "publisher", "version")


@admin.register(DeviceMetric)
class DeviceMetricAdmin(admin.ModelAdmin):
    list_display = ("machine", "cpu_percent", "memory_percent", "storage_percent", "recorded_at")
    list_filter = ("machine__branch",)


@admin.register(PowerEvent)
class PowerEventAdmin(admin.ModelAdmin):
    list_display = ("machine", "event_type", "occurred_at", "source_id")
    list_filter = ("event_type", "machine__branch")


@admin.register(AgentTask)
class AgentTaskAdmin(admin.ModelAdmin):
    list_display = ("machine", "kind", "status", "requested_by", "requested_at")
    list_filter = ("kind", "status")


@admin.register(DevicePairingCode)
class DevicePairingCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "expires_at", "used_at", "created_at")
    readonly_fields = ("code_hash", "created_at", "used_at")
