import core.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0005_realdeploy_fields")]

    operations = [
        migrations.AlterField(
            model_name="ticketattachment",
            name="file",
            field=models.FileField(blank=True, upload_to=core.models.ticket_attachment_path),
        ),
        migrations.AddField(
            model_name="ticketattachment",
            name="blob",
            field=models.BinaryField(blank=True, editable=False, null=True),
        ),
    ]
