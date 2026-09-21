import uuid
import core.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EmployeeProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("employee_code", models.CharField(blank=True, max_length=40, null=True, unique=True)),
                ("job_title", models.CharField(blank=True, max_length=100)),
                ("department", models.CharField(blank=True, max_length=100)),
                ("branch", models.CharField(blank=True, max_length=120)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assigned_machine", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_employees", to="core.machine")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="employee_profile", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["user__first_name", "user__username"]},
        ),
        migrations.CreateModel(
            name="SoftwareRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reason", models.TextField(blank=True, max_length=1200)),
                ("status", models.CharField(choices=[("submitted", "Submitted"), ("queued", "Approved / Queued"), ("completed", "Completed"), ("rejected", "Rejected"), ("failed", "Failed"), ("cancelled", "Cancelled")], default="submitted", max_length=20)),
                ("admin_note", models.TextField(blank=True, max_length=1200)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("app", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="software_requests", to="core.appcatalog")),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="software_requests", to=settings.AUTH_USER_MODEL)),
                ("linked_command", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="software_request", to="core.command")),
                ("machine", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="software_requests", to="core.machine")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_software_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-requested_at"]},
        ),
        migrations.CreateModel(
            name="SupportTicket",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("category", models.CharField(choices=[("hardware", "Hardware"), ("network", "Network"), ("printer", "Printer"), ("software", "Software"), ("access", "Account / Access"), ("other", "Other")], max_length=20)),
                ("priority", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")], default="medium", max_length=20)),
                ("subject", models.CharField(max_length=180)),
                ("description", models.TextField(max_length=5000)),
                ("status", models.CharField(choices=[("submitted", "Submitted"), ("assigned", "Assigned"), ("in_progress", "In progress"), ("resolved", "Resolved"), ("closed", "Closed")], default="submitted", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_support_tickets", to=settings.AUTH_USER_MODEL)),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="support_tickets", to=settings.AUTH_USER_MODEL)),
                ("machine", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="support_tickets", to="core.machine")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="TicketMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField(blank=True, max_length=4000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ticket_messages", to=settings.AUTH_USER_MODEL)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="core.supportticket")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="TicketAttachment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("file", models.FileField(upload_to=core.models.ticket_attachment_path)),
                ("original_name", models.CharField(max_length=180)),
                ("content_type", models.CharField(blank=True, max_length=80)),
                ("size", models.PositiveIntegerField(default=0)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("message", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="attachment", to="core.ticketmessage")),
            ],
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("info", "Info"), ("success", "Success"), ("warning", "Warning")], default="info", max_length=16)),
                ("title", models.CharField(max_length=140)),
                ("message", models.CharField(max_length=500)),
                ("link", models.CharField(blank=True, max_length=240)),
                ("is_read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="varunops_notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="softwarerequest", index=models.Index(fields=["employee", "status", "requested_at"], name="core_swreq_emp_status_idx")),
        migrations.AddIndex(model_name="supportticket", index=models.Index(fields=["employee", "status", "created_at"], name="core_ticket_emp_status_idx")),
        migrations.AddIndex(model_name="notification", index=models.Index(fields=["user", "is_read", "created_at"], name="core_notice_user_read_idx")),
    ]
