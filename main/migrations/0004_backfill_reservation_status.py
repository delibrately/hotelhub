from django.db import migrations


def backfill_historical_reservations(apps, schema_editor):
    Reservation = apps.get_model("main", "Reservation")
    Reservation.objects.filter(status__isnull=True).update(status="confirmed")


def reverse_backfill(apps, schema_editor):
    Reservation = apps.get_model("main", "Reservation")
    Reservation.objects.filter(status="confirmed").update(status=None)


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0003_reservation_status_nullable_and_operation_log"),
    ]

    operations = [
        migrations.RunPython(backfill_historical_reservations, reverse_backfill),
    ]
