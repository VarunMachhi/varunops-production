from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_enterprise_endpoint_management"),
    ]

    operations = [
        migrations.AddField(
            model_name="devicemetric",
            name="storage_volumes",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="agenttask",
            name="attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="agenttask",
            name="last_dispatch_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="DetectedSoftware",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("display_name", models.CharField(max_length=180)),
                ("version", models.CharField(blank=True, max_length=64)),
                ("publisher", models.CharField(blank=True, max_length=140)),
                ("classification", models.CharField(choices=[("catalog", "Company approved"), ("exception", "Per-PC exception"), ("system", "Windows / Microsoft baseline"), ("unauthorized", "Unauthorized")], default="unauthorized", max_length=20)),
                ("first_seen", models.DateTimeField(auto_now_add=True)),
                ("last_seen", models.DateTimeField(auto_now=True)),
                ("catalog_app", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="detected_installations", to="core.appcatalog")),
                ("machine", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="detected_software", to="core.machine")),
            ],
            options={
                "ordering": ["display_name"],
                "unique_together": {("machine", "display_name")},
            },
        ),
    ]
