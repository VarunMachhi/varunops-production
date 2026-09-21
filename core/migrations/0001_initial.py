# Generated manually for the packaged starter project.
import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="AppCatalog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("latest_version", models.CharField(blank=True, max_length=64)),
                ("winget_id", models.CharField(blank=True, max_length=120)),
                ("detection_names", models.JSONField(blank=True, default=list)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Machine",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120, unique=True)),
                ("branch", models.CharField(blank=True, max_length=120)),
                ("device_type", models.CharField(default="Desktop", max_length=40)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("os_version", models.CharField(blank=True, max_length=180)),
                ("serial_number", models.CharField(blank=True, max_length=120)),
                ("policy", models.CharField(choices=[("manual", "Manual"), ("automatic", "Automatic"), ("locked", "Locked")], default="manual", max_length=16)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("system_info", models.JSONField(blank=True, default=dict)),
                ("last_seen", models.DateTimeField(blank=True, null=True)),
                ("enrolled_at", models.DateTimeField(auto_now_add=True)),
                ("agent_key_hash", models.CharField(blank=True, max_length=255)),
                ("agent_key_rotated_at", models.DateTimeField(blank=True, null=True)),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="InstalledApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version", models.CharField(blank=True, max_length=64)),
                ("detected_name", models.CharField(blank=True, max_length=180)),
                ("last_reported", models.DateTimeField(auto_now=True)),
                ("app", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="installations", to="core.appcatalog")),
                ("machine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="installed_apps", to="core.machine")),
            ],
            options={"ordering": ["app__name"], "unique_together": {("machine", "app")}},
        ),
        migrations.CreateModel(
            name="Command",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("action", models.CharField(choices=[("install", "Install"), ("update", "Update"), ("uninstall", "Uninstall")], max_length=16)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("cancelled", "Cancelled")], default="queued", max_length=16)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("result_message", models.TextField(blank=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_dispatch_at", models.DateTimeField(blank=True, null=True)),
                ("app", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="commands", to="core.appcatalog")),
                ("machine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="commands", to="core.machine")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-requested_at"]},
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("info", "Info"), ("success", "Success"), ("warning", "Warning"), ("error", "Error")], default="info", max_length=16)),
                ("event", models.CharField(max_length=80)),
                ("message", models.TextField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("machine", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.machine")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="command", index=models.Index(fields=["machine", "status", "requested_at"], name="core_comman_machine_57cdf6_idx")),
        migrations.AddIndex(model_name="auditlog", index=models.Index(fields=["-created_at"], name="core_auditl_created_5226bc_idx")),
    ]
