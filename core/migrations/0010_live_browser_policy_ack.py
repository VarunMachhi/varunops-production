from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0009_normalize_browser_policy_rules")]

    operations = [
        migrations.AddField(model_name="machine", name="browser_policy_ack_id", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="machine", name="browser_policy_ack_revision", field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name="machine", name="browser_policy_ack_enabled", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="machine", name="browser_policy_ack_verified", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="machine", name="browser_policy_ack_at", field=models.DateTimeField(blank=True, null=True)),
    ]
