import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Machine(models.Model):
    POLICY_MANUAL = "manual"
    POLICY_AUTOMATIC = "automatic"
    POLICY_LOCKED = "locked"
    POLICY_CHOICES = [
        (POLICY_MANUAL, "Manual"),
        (POLICY_AUTOMATIC, "Automatic"),
        (POLICY_LOCKED, "Locked"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    branch = models.CharField(max_length=120, blank=True)
    device_type = models.CharField(max_length=40, default="Desktop")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    os_version = models.CharField(max_length=180, blank=True)
    serial_number = models.CharField(max_length=120, blank=True)
    policy = models.CharField(max_length=16, choices=POLICY_CHOICES, default=POLICY_MANUAL)
    tags = models.JSONField(default=list, blank=True)
    system_info = models.JSONField(default=dict, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    agent_key_hash = models.CharField(max_length=255, blank=True)
    agent_key_rotated_at = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=True)
    COMPLIANCE_AUDIT = "audit"
    COMPLIANCE_ENFORCE = "enforce"
    COMPLIANCE_CHOICES = [(COMPLIANCE_AUDIT, "Audit only"), (COMPLIANCE_ENFORCE, "Enforce approved software")]
    compliance_mode = models.CharField(max_length=16, choices=COMPLIANCE_CHOICES, default=COMPLIANCE_AUDIT)
    network_policy = models.ForeignKey("NetworkPolicy", on_delete=models.SET_NULL, null=True, blank=True, related_name="machines")
    last_boot_at = models.DateTimeField(null=True, blank=True)
    software_exceptions = models.JSONField(default=list, blank=True)
    live_metrics = models.JSONField(default=dict, blank=True)
    metrics_updated_at = models.DateTimeField(null=True, blank=True)
    agent_live_mode = models.BooleanField(default=False)
    asset_details = models.JSONField(default=dict, blank=True)
    # Dedicated endpoint acknowledgement for fast website-policy control.
    browser_policy_ack_id = models.PositiveIntegerField(null=True, blank=True)
    browser_policy_ack_revision = models.PositiveIntegerField(default=0)
    browser_policy_ack_enabled = models.BooleanField(default=False)
    browser_policy_ack_verified = models.BooleanField(default=False)
    browser_policy_ack_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    @property
    def online(self):
        if not self.last_seen:
            return False
        return (timezone.now() - self.last_seen).total_seconds() <= 180

    def __str__(self):
        return self.name


class AppCatalog(models.Model):
    SOURCE_WINGET = "winget"
    SOURCE_DIRECT = "direct"
    SOURCE_GITHUB = "github"
    SOURCE_CHOICES = [
        (SOURCE_WINGET, "Winget"),
        (SOURCE_DIRECT, "Direct HTTPS installer"),
        (SOURCE_GITHUB, "GitHub Release asset"),
    ]
    INSTALLER_EXE = "exe"
    INSTALLER_MSI = "msi"
    INSTALLER_CHOICES = [(INSTALLER_EXE, "EXE"), (INSTALLER_MSI, "MSI")]

    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=100)
    latest_version = models.CharField(max_length=64, blank=True)
    winget_id = models.CharField(max_length=120, blank=True)
    source_type = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_WINGET)
    installer_url = models.URLField(max_length=1200, blank=True)
    installer_sha256 = models.CharField(max_length=64, blank=True)
    installer_kind = models.CharField(max_length=8, choices=INSTALLER_CHOICES, default=INSTALLER_EXE)
    github_repo = models.CharField(max_length=180, blank=True)
    github_asset_name = models.CharField(max_length=220, blank=True)
    github_release_tag = models.CharField(max_length=120, blank=True)
    install_args = models.JSONField(default=list, blank=True)
    update_args = models.JSONField(default=list, blank=True)
    homepage_url = models.URLField(max_length=600, blank=True)
    icon_url = models.URLField(max_length=600, blank=True)
    detection_names = models.JSONField(default=list, blank=True)
    enabled = models.BooleanField(default=True)
    publisher = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True, max_length=1200)
    category = models.CharField(max_length=80, blank=True)
    employee_visible = models.BooleanField(default=True)
    license_required = models.BooleanField(default=False)
    license_notes = models.CharField(max_length=400, blank=True)
    update_notes = models.CharField(max_length=600, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class InstalledApp(models.Model):
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="installed_apps")
    app = models.ForeignKey(AppCatalog, on_delete=models.CASCADE, related_name="installations")
    version = models.CharField(max_length=64, blank=True)
    detected_name = models.CharField(max_length=180, blank=True)
    last_reported = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("machine", "app")]
        ordering = ["app__name"]


class Command(models.Model):
    ACTION_INSTALL = "install"
    ACTION_UPDATE = "update"
    ACTION_UNINSTALL = "uninstall"
    ACTION_CHOICES = [
        (ACTION_INSTALL, "Install"),
        (ACTION_UPDATE, "Update"),
        (ACTION_UNINSTALL, "Uninstall"),
    ]
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="commands")
    app = models.ForeignKey(AppCatalog, on_delete=models.PROTECT, related_name="commands")
    action = models.CharField(max_length=16, choices=ACTION_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    result_message = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_dispatch_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [models.Index(fields=["machine", "status", "requested_at"], name="core_comman_machine_57cdf6_idx")]


class AuditLog(models.Model):
    KIND_INFO = "info"
    KIND_SUCCESS = "success"
    KIND_WARNING = "warning"
    KIND_ERROR = "error"
    KIND_CHOICES = [
        (KIND_INFO, "Info"),
        (KIND_SUCCESS, "Success"),
        (KIND_WARNING, "Warning"),
        (KIND_ERROR, "Error"),
    ]

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True, blank=True)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=KIND_INFO)
    event = models.CharField(max_length=80)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"], name="core_auditl_created_5226bc_idx")]


def ticket_attachment_path(instance, filename):
    suffix = ""
    if "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1].lower()[:8]
    return f"ticket_attachments/{instance.id}{suffix}"


class EmployeeProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employee_profile")
    employee_code = models.CharField(max_length=40, unique=True, null=True, blank=True)
    job_title = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    branch = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    assigned_machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_employees")
    ONBOARD_PAIR_DEVICE = "pair_device"
    ONBOARD_VERIFY_EMAIL = "verify_email"
    ONBOARD_ACTIVE = "active"
    ONBOARD_CHOICES = [
        (ONBOARD_PAIR_DEVICE, "Connect company PC"),
        (ONBOARD_VERIFY_EMAIL, "Verify email and set password"),
        (ONBOARD_ACTIVE, "Active"),
    ]
    onboarding_state = models.CharField(max_length=20, choices=ONBOARD_CHOICES, default=ONBOARD_PAIR_DEVICE)
    temporary_password_issued_at = models.DateTimeField(null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    asset_details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__first_name", "user__username"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username




class PasswordResetOTP(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="varunops_password_otps")
    code_hash = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "used_at", "expires_at"], name="core_otp_user_state_idx")]


class SoftwareRequest(models.Model):
    STATUS_SUBMITTED = "submitted"
    STATUS_QUEUED = "queued"
    STATUS_COMPLETED = "completed"
    STATUS_REJECTED = "rejected"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_QUEUED, "Approved / Queued"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    ACTION_INSTALL = "install"
    ACTION_UPDATE = "update"
    ACTION_UNINSTALL = "uninstall"
    ACTION_CHOICES = [(ACTION_INSTALL, "Install"), (ACTION_UPDATE, "Update"), (ACTION_UNINSTALL, "Uninstall")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="software_requests")
    action = models.CharField(max_length=16, choices=ACTION_CHOICES, default=ACTION_INSTALL)
    machine = models.ForeignKey(Machine, on_delete=models.PROTECT, related_name="software_requests")
    app = models.ForeignKey(AppCatalog, on_delete=models.PROTECT, related_name="software_requests")
    reason = models.TextField(blank=True, max_length=1200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    admin_note = models.TextField(blank=True, max_length=1200)
    linked_command = models.OneToOneField(Command, on_delete=models.SET_NULL, null=True, blank=True, related_name="software_request")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_software_requests")
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        indexes = [models.Index(fields=["employee", "status", "requested_at"], name="core_swreq_emp_status_idx")]

    def __str__(self):
        return f"{self.employee} · {self.app} · {self.status}"


class SupportTicket(models.Model):
    CATEGORY_HARDWARE = "hardware"
    CATEGORY_NETWORK = "network"
    CATEGORY_PRINTER = "printer"
    CATEGORY_SOFTWARE = "software"
    CATEGORY_ACCESS = "access"
    CATEGORY_OTHER = "other"
    CATEGORY_CHOICES = [
        (CATEGORY_HARDWARE, "Hardware"),
        (CATEGORY_NETWORK, "Network"),
        (CATEGORY_PRINTER, "Printer"),
        (CATEGORY_SOFTWARE, "Software"),
        (CATEGORY_ACCESS, "Account / Access"),
        (CATEGORY_OTHER, "Other"),
    ]
    PRIORITY_LOW = "low"
    PRIORITY_MEDIUM = "medium"
    PRIORITY_HIGH = "high"
    PRIORITY_CRITICAL = "critical"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_MEDIUM, "Medium"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_CRITICAL, "Critical"),
    ]
    STATUS_SUBMITTED = "submitted"
    STATUS_ASSIGNED = "assigned"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_ASSIGNED, "Assigned"),
        (STATUS_IN_PROGRESS, "In progress"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_CLOSED, "Closed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="support_tickets")
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True, blank=True, related_name="support_tickets")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    subject = models.CharField(max_length=180)
    description = models.TextField(max_length=5000)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_support_tickets")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["employee", "status", "created_at"], name="core_ticket_emp_status_idx")]

    def __str__(self):
        return f"{self.subject} ({self.status})"


class TicketMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="ticket_messages")
    body = models.TextField(blank=True, max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class TicketAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.OneToOneField(TicketMessage, on_delete=models.CASCADE, related_name="attachment")
    file = models.FileField(upload_to=ticket_attachment_path, blank=True)
    blob = models.BinaryField(null=True, blank=True, editable=False)
    original_name = models.CharField(max_length=180)
    content_type = models.CharField(max_length=80, blank=True)
    size = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    KIND_INFO = "info"
    KIND_SUCCESS = "success"
    KIND_WARNING = "warning"
    KIND_CHOICES = [
        (KIND_INFO, "Info"),
        (KIND_SUCCESS, "Success"),
        (KIND_WARNING, "Warning"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="varunops_notifications")
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=KIND_INFO)
    title = models.CharField(max_length=140)
    message = models.CharField(max_length=500)
    link = models.CharField(max_length=240, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read", "created_at"], name="core_notice_user_read_idx")]


class NetworkPolicy(models.Model):
    MODE_BLOCKLIST = "blocklist"
    MODE_ALLOWLIST = "allowlist"
    MODE_CHOICES = [(MODE_BLOCKLIST, "Block selected sites"), (MODE_ALLOWLIST, "Allow only selected sites")]
    name = models.CharField(max_length=120, unique=True)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default=MODE_BLOCKLIST)
    allowed_sites = models.JSONField(default=list, blank=True)
    blocked_sites = models.JSONField(default=list, blank=True)
    enforce_edge = models.BooleanField(default=True)
    enforce_chrome = models.BooleanField(default=True)
    strict_browsing = models.BooleanField(default=False, help_text="Block common unmanaged browsers from outbound web access; Edge/Chrome remain governed by URL policy.")
    enabled = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class MachineAppPolicy(models.Model):
    MODE_REQUIRED = "required"
    MODE_OPTIONAL = "optional"
    MODE_BLOCKED = "blocked"
    MODE_CHOICES = [(MODE_REQUIRED, "Required"), (MODE_OPTIONAL, "Optional"), (MODE_BLOCKED, "Blocked")]
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="app_policies")
    app = models.ForeignKey(AppCatalog, on_delete=models.CASCADE, related_name="machine_policies")
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default=MODE_OPTIONAL)
    auto_update = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("machine", "app")]


class UnauthorizedSoftware(models.Model):
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="unauthorized_software")
    display_name = models.CharField(max_length=180)
    version = models.CharField(max_length=64, blank=True)
    publisher = models.CharField(max_length=140, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    resolved = models.BooleanField(default=False)
    resolution = models.CharField(max_length=160, blank=True)

    class Meta:
        unique_together = [("machine", "display_name")]
        ordering = ["-last_seen"]


class DetectedSoftware(models.Model):
    CLASS_CATALOG = "catalog"
    CLASS_EXCEPTION = "exception"
    CLASS_SYSTEM = "system"
    CLASS_UNAUTHORIZED = "unauthorized"
    CLASS_CHOICES = [
        (CLASS_CATALOG, "Company approved"),
        (CLASS_EXCEPTION, "Per-PC exception"),
        (CLASS_SYSTEM, "Windows / Microsoft baseline"),
        (CLASS_UNAUTHORIZED, "Unauthorized"),
    ]
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="detected_software")
    display_name = models.CharField(max_length=180)
    version = models.CharField(max_length=64, blank=True)
    publisher = models.CharField(max_length=140, blank=True)
    catalog_app = models.ForeignKey(AppCatalog, on_delete=models.SET_NULL, null=True, blank=True, related_name="detected_installations")
    classification = models.CharField(max_length=20, choices=CLASS_CHOICES, default=CLASS_UNAUTHORIZED)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("machine", "display_name")]
        ordering = ["display_name"]


class DeviceMetric(models.Model):
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="metrics")
    cpu_percent = models.FloatField(default=0)
    memory_percent = models.FloatField(default=0)
    memory_used_gb = models.FloatField(default=0)
    memory_total_gb = models.FloatField(default=0)
    storage_percent = models.FloatField(default=0)
    storage_used_gb = models.FloatField(default=0)
    storage_total_gb = models.FloatField(default=0)
    storage_volumes = models.JSONField(default=list, blank=True)
    uptime_seconds = models.BigIntegerField(default=0)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]


class PowerEvent(models.Model):
    EVENT_BOOT = "boot"
    EVENT_SHUTDOWN = "shutdown"
    EVENT_UNEXPECTED = "unexpected_shutdown"
    EVENT_CHOICES = [(EVENT_BOOT, "Boot"), (EVENT_SHUTDOWN, "Shutdown"), (EVENT_UNEXPECTED, "Unexpected shutdown")]
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="power_events")
    event_type = models.CharField(max_length=24, choices=EVENT_CHOICES)
    occurred_at = models.DateTimeField()
    source_id = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("machine", "event_type", "occurred_at")]
        ordering = ["-occurred_at"]


class DevicePairingCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="device_pairing_codes")
    code_hash = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AgentTask(models.Model):
    KIND_UNINSTALL_DETECTED = "uninstall_detected"
    KIND_CHOICES = [(KIND_UNINSTALL_DETECTED, "Uninstall detected software")]
    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [(STATUS_QUEUED, "Queued"), (STATUS_RUNNING, "Running"), (STATUS_SUCCEEDED, "Succeeded"), (STATUS_FAILED, "Failed")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="agent_tasks")
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="agent_tasks")
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    result_message = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_dispatch_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
