from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


def initialize_existing_onboarding(apps, schema_editor):
    EmployeeProfile = apps.get_model("core", "EmployeeProfile")
    EmployeeProfile.objects.filter(assigned_machine__isnull=False).update(onboarding_state="verify_email")


def reverse_existing_onboarding(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0006_ticket_attachment_blob"),
    ]

    operations = [
        migrations.AddField(
            model_name="machine",
            name="asset_details",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="employeeprofile",
            name="asset_details",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="employeeprofile",
            name="onboarding_state",
            field=models.CharField(
                choices=[
                    ("pair_device", "Connect company PC"),
                    ("verify_email", "Verify email and set password"),
                    ("active", "Active"),
                ],
                default="pair_device",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="employeeprofile",
            name="temporary_password_issued_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="employeeprofile",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="employeeprofile",
            name="password_changed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="PasswordResetOTP",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code_hash", models.CharField(max_length=255)),
                ("expires_at", models.DateTimeField()),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="varunops_password_otps", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="passwordresetotp",
            index=models.Index(fields=["user", "used_at", "expires_at"], name="core_otp_user_state_idx"),
        ),
        migrations.RunPython(initialize_existing_onboarding, reverse_existing_onboarding),
    ]
