from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ReservationNoteMigrationTests(TransactionTestCase):
    migrate_from = [("main", "0005_reservation_status_required")]
    migrate_to = [
        ("main", "0006_alter_adminoperationlog_action_and_more")
    ]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.old_apps = executor.loader.project_state(self.migrate_from).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_migration_creates_empty_reservation_note_table(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        ReservationNote = new_apps.get_model("main", "ReservationNote")
        self.assertEqual(ReservationNote.objects.count(), 0)

    def test_migration_preserves_additional_without_creating_note(self):
        Guest = self.old_apps.get_model("guest", "Guest")
        Room = self.old_apps.get_model("room", "Room")
        Reservation = self.old_apps.get_model("main", "Reservation")
        guest = Guest.objects.create(
            first_name="Migration",
            last_name="Guest",
            email="note-migration@example.invalid",
            phone_number="0000000000",
            government_id="NOTE-MIGRATION",
            address="Migration address",
        )
        room = Room.objects.create(
            room_number="NOTE-MIG",
            room_type="Test",
            price_per_night="100.00",
        )
        reservation = Reservation.objects.create(
            room=room,
            guest=guest,
            additional="Keep this existing additional text",
            check_in_date=date(2026, 1, 1),
            check_out_date=date(2026, 1, 2),
            status="confirmed",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        MigratedReservation = new_apps.get_model("main", "Reservation")
        ReservationNote = new_apps.get_model("main", "ReservationNote")
        migrated = MigratedReservation.objects.get(pk=reservation.pk)
        self.assertEqual(
            migrated.additional,
            "Keep this existing additional text",
        )
        self.assertEqual(ReservationNote.objects.count(), 0)
