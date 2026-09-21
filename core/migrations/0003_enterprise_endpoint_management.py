from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings
import uuid


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0002_employee_portal"),
    ]

    operations = [
        migrations.CreateModel(
            name="NetworkPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("mode", models.CharField(choices=[("blocklist", "Block selected sites"), ("allowlist", "Allow only selected sites")], default="blocklist", max_length=16)),
                ("allowed_sites", models.JSONField(blank=True, default=list)),
                ("blocked_sites", models.JSONField(blank=True, default=list)),
                ("enforce_edge", models.BooleanField(default=True)),
                ("enforce_chrome", models.BooleanField(default=True)),
                ("enabled", models.BooleanField(default=True)),
                ("revision", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddField(model_name="machine", name="compliance_mode", field=models.CharField(choices=[("audit", "Audit only"), ("enforce", "Enforce approved software")], default="audit", max_length=16)),
        migrations.AddField(model_name="machine", name="last_boot_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="machine", name="software_exceptions", field=models.JSONField(blank=True, default=list)),
        migrations.AddField(model_name="machine", name="network_policy", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="machines", to="core.networkpolicy")),
        migrations.AddField(model_name="appcatalog", name="publisher", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="appcatalog", name="description", field=models.TextField(blank=True, max_length=1200)),
        migrations.AddField(model_name="appcatalog", name="category", field=models.CharField(blank=True, max_length=80)),
        migrations.AddField(model_name="appcatalog", name="employee_visible", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="appcatalog", name="license_required", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="appcatalog", name="license_notes", field=models.CharField(blank=True, max_length=400)),
        migrations.AddField(model_name="appcatalog", name="update_notes", field=models.CharField(blank=True, max_length=600)),
        migrations.CreateModel(
            name="DeviceMetric",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cpu_percent", models.FloatField(default=0)),
                ("memory_percent", models.FloatField(default=0)),
                ("memory_used_gb", models.FloatField(default=0)),
                ("memory_total_gb", models.FloatField(default=0)),
                ("storage_percent", models.FloatField(default=0)),
                ("storage_used_gb", models.FloatField(default=0)),
                ("storage_total_gb", models.FloatField(default=0)),
                ("uptime_seconds", models.BigIntegerField(default=0)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("machine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="metrics", to="core.machine")),
            ],
            options={"ordering": ["-recorded_at"]},
        ),
        migrations.CreateModel(
            name="MachineAppPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(choices=[("required", "Required"), ("optional", "Optional"), ("blocked", "Blocked")], default="optional", max_length=16)),
                ("auto_update", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("app", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="machine_policies", to="core.appcatalog")),
                ("machine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="app_policies", to="core.machine")),
            ],
            options={"unique_together": {("machine", "app")}},
        ),
        migrations.CreateModel(
            name="PowerEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("boot", "Boot"), ("shutdown", "Shutdown"), ("unexpected_shutdown", "Unexpected shutdown")], max_length=24)),
                ("occurred_at", models.DateTimeField()),
                ("source_id", models.CharField(blank=True, max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("machine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="power_events", to="core.machine")),
            ],
            options={"ordering": ["-occurred_at"], "unique_together": {("machine", "event_type", "occurred_at")}},
        ),
        migrations.CreateModel(
            name="UnauthorizedSoftware",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("display_name", models.CharField(max_length=180)),
                ("version", models.CharField(blank=True, max_length=64)),
                ("publisher", models.CharField(blank=True, max_length=140)),
                ("detected_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen", models.DateTimeField(auto_now=True)),
                ("resolved", models.BooleanField(default=False)),
                ("resolution", models.CharField(blank=True, max_length=160)),
                ("machine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="unauthorized_software", to="core.machine")),
            ],
            options={"ordering": ["-last_seen"], "unique_together": {("machine", "display_name")}},
        ),
        migrations.AddField(model_name="softwarerequest", name="action", field=models.CharField(choices=[("install", "Install"), ("update", "Update"), ("uninstall", "Uninstall")], default="install", max_length=16)),
        migrations.CreateModel(
            name="AgentTask",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False, editable=False)),
                ("kind", models.CharField(choices=[("uninstall_detected", "Uninstall detected software")], max_length=32)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed")], default="queued", max_length=16)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("result_message", models.TextField(blank=True)),
                ("machine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agent_tasks", to="core.machine")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="agent_tasks", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-requested_at"]},
        ),
        migrations.CreateModel(
            name="DevicePairingCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code_hash", models.CharField(max_length=255)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="device_pairing_codes", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
