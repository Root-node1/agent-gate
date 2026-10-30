from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0002_checkoutorder"),
    ]

    operations = [
        migrations.AddField(
            model_name="checkoutorder",
            name="payer_action_url",
            field=models.URLField(blank=True, max_length=2048, null=True),
        ),
    ]
