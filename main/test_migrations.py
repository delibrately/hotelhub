from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ReservationStatusMigrationTests(TransactionTestCase):
    migrate_from = [
        ("main", "0002_alter_reservation_guest_alter_reservation_room_and_more")
    ]
    migrate_to = [("main", "0005_reservation_status_required")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.old_apps = executor.loader.project_state(self.migrate_from).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_historical_reservation_is_backfilled_and_reverse_is_safe(self):
        Guest = self.old_apps.get_model("guest", "Guest")
        Room = self.old_apps.get_model("room", "Room")
        Reservation = self.old_apps.get_model("main", "Reservation")

        guest = Guest.objects.create(
            first_name="Historical",
            last_name="Guest",
            email="historical@example.invalid",
            phone_number="0000000000",
            government_id="HISTORY-ID",
            address="Historical test address",
        )
        room = Room.objects.create(
            room_number="HISTORY-1",
            room_type="Test",
            price_per_night="100.00",
        )
        reservation = Reservation.objects.create(
            room=room,
            guest=guest,
            check_in_date=date(2025, 1, 1),
            check_out_date=date(2025, 1, 2),
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        MigratedReservation = new_apps.get_model("main", "Reservation")
        migrated = MigratedReservation.objects.get(pk=reservation.pk)
        self.assertEqual(migrated.status, "confirmed")

        reverse_target = [
            ("main", "0003_reservation_status_nullable_and_operation_log")
        ]
        executor = MigrationExecutor(connection)
        executor.migrate(reverse_target)
        reversed_apps = executor.loader.project_state(reverse_target).apps
        ReversedReservation = reversed_apps.get_model("main", "Reservation")
        self.assertIsNone(
            ReversedReservation.objects.get(pk=reservation.pk).status
        )
