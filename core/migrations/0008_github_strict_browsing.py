from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0007_onboarding_asset_otp")]
    operations = [
        migrations.AddField(model_name="appcatalog", name="github_repo", field=models.CharField(blank=True, max_length=180)),
        migrations.AddField(model_name="appcatalog", name="github_asset_name", field=models.CharField(blank=True, max_length=220)),
        migrations.AddField(model_name="appcatalog", name="github_release_tag", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="networkpolicy", name="strict_browsing", field=models.BooleanField(default=False, help_text="Block common unmanaged browsers from outbound web access; Edge/Chrome remain governed by URL policy.")),
        migrations.AlterField(model_name="appcatalog", name="source_type", field=models.CharField(choices=[("winget", "Winget"), ("direct", "Direct HTTPS installer"), ("github", "GitHub Release asset")], default="winget", max_length=16)),
    ]
