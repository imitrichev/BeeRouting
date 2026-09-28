"""Добавляет сохраняемый признак оперативной доступности инженера."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Расширяет инженера флагом, который синхронизируется с domain-снимком."""

    dependencies = [
        ("api_v2", "0003_engineer_available_router_count_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="engineer",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
