from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0004_detected_software_inventory")]

    operations = [
        migrations.AddField(
            model_name="machine",
            name="live_metrics",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="machine",
            name="metrics_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="machine",
            name="agent_live_mode",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="appcatalog",
            name="source_type",
            field=models.CharField(choices=[("winget", "Winget"), ("direct", "Direct HTTPS installer")], default="winget", max_length=16),
        ),
        migrations.AddField(
            model_name="appcatalog",
            name="installer_url",
            field=models.URLField(blank=True, max_length=1200),
        ),
        migrations.AddField(
            model_name="appcatalog",
            name="installer_sha256",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="appcatalog",
            name="installer_kind",
            field=models.CharField(choices=[("exe", "EXE"), ("msi", "MSI")], default="exe", max_length=8),
        ),
        migrations.AddField(
            model_name="appcatalog",
            name="install_args",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="appcatalog",
            name="update_args",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="appcatalog",
            name="homepage_url",
            field=models.URLField(blank=True, max_length=600),
        ),
        migrations.AddField(
            model_name="appcatalog",
            name="icon_url",
            field=models.URLField(blank=True, max_length=600),
        ),
    ]
