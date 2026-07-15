from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0004_backfill_reservation_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reservation",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "待确认"),
                    ("confirmed", "已确认"),
                    ("checked_in", "已入住"),
                    ("checked_out", "已退房"),
                    ("cancelled", "已取消"),
                    ("no_show", "未到店"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
    ]
