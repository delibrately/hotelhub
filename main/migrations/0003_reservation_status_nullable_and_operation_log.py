import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("main", "0002_alter_reservation_guest_alter_reservation_room_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="reservation",
            options={
                "permissions": [
                    (
                        "manage_reservation_status",
                        "Can confirm, cancel, check in, check out, and mark no-show",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="reservation",
            name="status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("pending", "待确认"),
                    ("confirmed", "已确认"),
                    ("checked_in", "已入住"),
                    ("checked_out", "已退房"),
                    ("cancelled", "已取消"),
                    ("no_show", "未到店"),
                ],
                db_index=True,
                max_length=20,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="AdminOperationLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("reservation_created", "创建订单"),
                            ("reservation_updated", "修改订单"),
                            ("reservation_confirmed", "确认订单"),
                            ("reservation_cancelled", "取消订单"),
                            ("reservation_checked_in", "办理入住"),
                            ("reservation_checked_out", "办理退房"),
                            ("reservation_no_show", "标记未到店"),
                            ("room_created", "创建房间"),
                            ("room_updated", "修改房间"),
                            ("guest_created", "创建客人"),
                            ("guest_updated", "修改客人"),
                        ],
                        db_index=True,
                        max_length=40,
                    ),
                ),
                (
                    "target_type",
                    models.CharField(
                        choices=[
                            ("reservation", "订单"),
                            ("room", "房间"),
                            ("guest", "客人"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("target_id", models.PositiveBigIntegerField(db_index=True)),
                ("description", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "operator",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="admin_operation_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["target_type", "target_id"],
                        name="main_admin_log_target_idx",
                    )
                ],
            },
        ),
    ]
