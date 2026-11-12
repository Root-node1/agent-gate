from django.db import migrations, models


def forwards_execution_blocked_status(apps, schema_editor):
    spend_requests = apps.get_model("spend", "SpendRequest").objects.using(
        schema_editor.connection.alias
    )
    spend_requests.filter(status="blocked").update(
        status="execution_blocked"
    )


def backwards_execution_blocked_status(apps, schema_editor):
    spend_requests = apps.get_model("spend", "SpendRequest").objects.using(
        schema_editor.connection.alias
    )
    spend_requests.filter(status="execution_blocked").update(status="blocked")


class Migration(migrations.Migration):

    dependencies = [
        ("spend", "0003_source_untrusted"),
    ]

    operations = [
        migrations.RunPython(
            forwards_execution_blocked_status,
            backwards_execution_blocked_status,
        ),
        migrations.AlterField(
            model_name="spendrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending_approval", "Pending approval"),
                    ("denied", "Denied"),
                    ("approved", "Approved"),
                    ("executing", "Executing"),
                    ("succeeded", "Succeeded"),
                    ("failed", "Failed"),
                    ("execution_blocked", "Execution blocked"),
                    ("rejected", "Rejected"),
                    ("expired", "Expired"),
                    ("reversed", "Reversed"),
                ],
                max_length=20,
            ),
        ),
    ]
