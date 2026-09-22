from rest_framework import serializers
from .models import (
    AppCatalog, AuditLog, Command, EmployeeProfile, InstalledApp, Machine,
    Notification, SoftwareRequest, SupportTicket, TicketAttachment, TicketMessage,
    NetworkPolicy, MachineAppPolicy, UnauthorizedSoftware, DetectedSoftware, DeviceMetric, PowerEvent,
)


class AppCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppCatalog
        fields = ["slug", "name", "latest_version", "winget_id", "source_type", "installer_url", "installer_sha256", "installer_kind", "github_repo", "github_asset_name", "github_release_tag", "install_args", "update_args", "homepage_url", "icon_url", "publisher", "description", "category", "employee_visible", "license_required", "license_notes", "update_notes"]


class InstalledAppSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(source="app.slug")
    name = serializers.CharField(source="app.name")
    latest_version = serializers.CharField(source="app.latest_version")

    class Meta:
        model = InstalledApp
        fields = ["slug", "name", "version", "latest_version", "last_reported"]


class DeviceMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceMetric
        fields = ["cpu_percent", "memory_percent", "memory_used_gb", "memory_total_gb", "storage_percent", "storage_used_gb", "storage_total_gb", "storage_volumes", "uptime_seconds", "recorded_at"]


class PowerEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = PowerEvent
        fields = ["event_type", "occurred_at", "source_id"]


class UnauthorizedSoftwareSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnauthorizedSoftware
        fields = ["id", "display_name", "version", "publisher", "detected_at", "last_seen", "resolved", "resolution"]


class DetectedSoftwareSerializer(serializers.ModelSerializer):
    catalog_slug = serializers.CharField(source="catalog_app.slug", allow_null=True, read_only=True)
    catalog_name = serializers.CharField(source="catalog_app.name", allow_null=True, read_only=True)

    class Meta:
        model = DetectedSoftware
        fields = ["id", "display_name", "version", "publisher", "classification", "catalog_slug", "catalog_name", "first_seen", "last_seen"]


class NetworkPolicySerializer(serializers.ModelSerializer):
    machine_count = serializers.IntegerField(read_only=True, required=False)
    class Meta:
        model = NetworkPolicy
        fields = ["id", "name", "mode", "allowed_sites", "blocked_sites", "enforce_edge", "enforce_chrome", "strict_browsing", "enabled", "revision", "machine_count", "updated_at"]


class MachineAppPolicySerializer(serializers.ModelSerializer):
    app_slug = serializers.CharField(source="app.slug", read_only=True)
    app_name = serializers.CharField(source="app.name", read_only=True)
    class Meta:
        model = MachineAppPolicy
        fields = ["id", "app_slug", "app_name", "mode", "auto_update", "updated_at"]


class MachineSerializer(serializers.ModelSerializer):
    online = serializers.BooleanField(read_only=True)
    installed_apps = InstalledAppSerializer(many=True, read_only=True)
    latest_metric = serializers.SerializerMethodField()
    unauthorized_software = UnauthorizedSoftwareSerializer(many=True, read_only=True)
    detected_software = DetectedSoftwareSerializer(many=True, read_only=True)
    app_policies = MachineAppPolicySerializer(many=True, read_only=True)
    network_policy_name = serializers.CharField(source="network_policy.name", allow_null=True, read_only=True)
    assigned_employee_name = serializers.SerializerMethodField()
    recent_power_events = serializers.SerializerMethodField()

    class Meta:
        model = Machine
        fields = [
            "id", "name", "branch", "device_type", "ip_address", "os_version",
            "serial_number", "policy", "tags", "system_info", "asset_details", "last_seen",
            "enrolled_at", "enabled", "online", "installed_apps", "detected_software", "compliance_mode", "network_policy", "network_policy_name", "last_boot_at", "latest_metric", "metrics_updated_at", "agent_live_mode", "unauthorized_software", "app_policies", "assigned_employee_name", "recent_power_events",
        ]

    def get_assigned_employee_name(self, obj):
        profile = obj.assigned_employees.select_related("user").first()
        if not profile:
            return None
        return profile.user.get_full_name() or profile.user.username

    def get_latest_metric(self, obj):
        if obj.live_metrics:
            return {**obj.live_metrics, "recorded_at": obj.metrics_updated_at}
        metric = obj.metrics.order_by("-recorded_at").first()
        return DeviceMetricSerializer(metric).data if metric else None

    def get_recent_power_events(self, obj):
        return PowerEventSerializer(obj.power_events.order_by("-occurred_at")[:8], many=True).data


class EmployeeMachineSerializer(serializers.ModelSerializer):
    online = serializers.BooleanField(read_only=True)
    installed_apps = InstalledAppSerializer(many=True, read_only=True)
    latest_metric = serializers.SerializerMethodField()
    recent_power_events = serializers.SerializerMethodField()
    network_policy_name = serializers.CharField(source="network_policy.name", allow_null=True, read_only=True)

    class Meta:
        model = Machine
        fields = [
            "id", "name", "branch", "device_type", "ip_address", "os_version",
            "serial_number", "tags", "system_info", "asset_details", "last_seen", "online", "installed_apps", "compliance_mode", "network_policy_name", "last_boot_at", "latest_metric", "metrics_updated_at", "agent_live_mode", "recent_power_events",
        ]

    def get_latest_metric(self, obj):
        if obj.live_metrics:
            return {**obj.live_metrics, "recorded_at": obj.metrics_updated_at}
        metric = obj.metrics.order_by("-recorded_at").first()
        return DeviceMetricSerializer(metric).data if metric else None

    def get_recent_power_events(self, obj):
        return PowerEventSerializer(obj.power_events.order_by("-occurred_at")[:8], many=True).data


class EmployeeProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    full_name = serializers.SerializerMethodField()
    email = serializers.CharField(source="user.email", read_only=True)
    assigned_machine_id = serializers.UUIDField(source="assigned_machine.id", allow_null=True, read_only=True)
    assigned_machine_name = serializers.CharField(source="assigned_machine.name", allow_null=True, read_only=True)

    password_status = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeProfile
        fields = [
            "username", "first_name", "last_name", "full_name", "email", "employee_code", "job_title", "department", "branch", "phone",
            "assigned_machine_id", "assigned_machine_name", "onboarding_state", "temporary_password_issued_at",
            "email_verified_at", "password_changed_at", "password_status", "asset_details",
        ]

    def get_password_status(self, obj):
        if obj.password_changed_at:
            return "Permanent password set"
        if obj.temporary_password_issued_at:
            return "Temporary password issued"
        return "Not initialized"

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


class CommandSerializer(serializers.ModelSerializer):
    machine_name = serializers.CharField(source="machine.name", read_only=True)
    app_slug = serializers.CharField(source="app.slug", read_only=True)
    app_name = serializers.CharField(source="app.name", read_only=True)

    class Meta:
        model = Command
        fields = [
            "id", "machine", "machine_name", "app_slug", "app_name", "action",
            "status", "requested_at", "started_at", "completed_at", "result_message", "attempts",
        ]


class AuditLogSerializer(serializers.ModelSerializer):
    actor = serializers.CharField(source="actor.username", allow_null=True)
    machine_name = serializers.CharField(source="machine.name", allow_null=True)

    class Meta:
        model = AuditLog
        fields = ["id", "kind", "event", "message", "actor", "machine_name", "metadata", "created_at"]


class SoftwareRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    employee_username = serializers.CharField(source="employee.username", read_only=True)
    machine_name = serializers.CharField(source="machine.name", read_only=True)
    app_slug = serializers.CharField(source="app.slug", read_only=True)
    app_name = serializers.CharField(source="app.name", read_only=True)
    current_version = serializers.SerializerMethodField()
    latest_version = serializers.CharField(source="app.latest_version", read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()
    command_status = serializers.CharField(source="linked_command.status", allow_null=True, read_only=True)

    class Meta:
        model = SoftwareRequest
        fields = [
            "id", "employee_name", "employee_username", "machine_name", "app_slug", "app_name", "action",
            "current_version", "latest_version", "reason", "status", "admin_note", "requested_at",
            "reviewed_at", "completed_at", "reviewed_by_name", "command_status",
        ]

    def get_employee_name(self, obj):
        return obj.employee.get_full_name() or obj.employee.username

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by:
            return None
        return obj.reviewed_by.get_full_name() or obj.reviewed_by.username

    def get_current_version(self, obj):
        install = InstalledApp.objects.filter(machine=obj.machine, app=obj.app).only("version").first()
        return install.version if install else None


class TicketAttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = TicketAttachment
        fields = ["id", "original_name", "content_type", "size", "download_url"]

    def get_download_url(self, obj):
        return f"/api/tickets/attachments/{obj.id}/"


class TicketMessageSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_is_staff = serializers.SerializerMethodField()
    attachment = serializers.SerializerMethodField()

    class Meta:
        model = TicketMessage
        fields = ["id", "author_name", "author_is_staff", "body", "created_at", "attachment"]

    def get_author_name(self, obj):
        if not obj.author:
            return "System"
        return obj.author.get_full_name() or obj.author.username

    def get_author_is_staff(self, obj):
        return bool(obj.author and obj.author.is_staff)

    def get_attachment(self, obj):
        try:
            attachment = obj.attachment
        except TicketAttachment.DoesNotExist:
            return None
        return TicketAttachmentSerializer(attachment).data


class SupportTicketSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    employee_username = serializers.CharField(source="employee.username", read_only=True)
    machine_name = serializers.CharField(source="machine.name", allow_null=True, read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    messages = TicketMessageSerializer(many=True, read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            "id", "employee_name", "employee_username", "machine_name", "category", "priority",
            "subject", "description", "status", "assigned_to_name", "created_at", "updated_at",
            "resolved_at", "messages",
        ]

    def get_employee_name(self, obj):
        return obj.employee.get_full_name() or obj.employee.username

    def get_assigned_to_name(self, obj):
        if not obj.assigned_to:
            return None
        return obj.assigned_to.get_full_name() or obj.assigned_to.username


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "message", "link", "is_read", "created_at"]
