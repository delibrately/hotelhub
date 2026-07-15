from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from guest.models import Guest
from room.models import Room

from .forms import ReservationForm
from .models import AdminOperationLog, Reservation
from .services import (
    ReservationTransitionError,
    cancel_reservation,
    check_in_reservation,
    check_out_reservation,
    confirm_reservation,
    get_allowed_transitions,
    mark_reservation_no_show,
)


class StatusTestBase(TestCase):
    business_date = date(2026, 8, 10)

    @classmethod
    def setUpTestData(cls):
        cls.room = Room.objects.create(
            room_number="STATUS-1",
            room_type="Test",
            price_per_night="100.00",
        )
        cls.other_room = Room.objects.create(
            room_number="STATUS-2",
            room_type="Test",
            price_per_night="100.00",
        )
        cls.guest = Guest.objects.create(
            first_name="Status",
            last_name="Guest",
            email="status-guest@example.invalid",
            phone_number="13900000000",
            government_id="STATUS-ID-1234",
            address="Status test address",
        )
        cls.operator = get_user_model().objects.create_user(
            username="status-operator",
            password="test-password",
            is_staff=True,
        )

    def create_reservation(self, status=Reservation.Status.PENDING, **overrides):
        values = {
            "room": self.room,
            "guest": self.guest,
            "check_in_date": self.business_date,
            "check_out_date": self.business_date + timedelta(days=2),
            "status": status,
        }
        values.update(overrides)
        return Reservation.objects.create(**values)

    def form_data(self, **overrides):
        values = {
            "room": self.room.pk,
            "guest": self.guest.pk,
            "additional": "",
            "check_in_date": self.business_date.isoformat(),
            "check_out_date": (self.business_date + timedelta(days=2)).isoformat(),
        }
        values.update(overrides)
        return values


class ReservationStatusModelTests(StatusTestBase):
    def test_new_reservation_defaults_to_pending(self):
        reservation = Reservation.objects.create(
            room=self.room,
            guest=self.guest,
            check_in_date=self.business_date,
            check_out_date=self.business_date + timedelta(days=1),
        )
        self.assertEqual(reservation.status, Reservation.Status.PENDING)

    def test_status_field_is_required_indexed_and_not_in_normal_form(self):
        field = Reservation._meta.get_field("status")
        self.assertFalse(field.null)
        self.assertTrue(field.db_index)
        self.assertEqual(field.default, Reservation.Status.PENDING)
        self.assertNotIn("status", ReservationForm().fields)

    def test_database_rejects_null_status(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Reservation.objects.create(
                    room=self.room,
                    guest=self.guest,
                    check_in_date=self.business_date,
                    check_out_date=self.business_date + timedelta(days=1),
                    status=None,
                )


class OccupancyStatusTests(StatusTestBase):
    def test_occupying_statuses_block_overlapping_reservations(self):
        for status in Reservation.OCCUPYING_STATUSES:
            with self.subTest(status=status):
                reservation = self.create_reservation(status=status)
                form = ReservationForm(
                    data=self.form_data(
                        check_in_date=(
                            self.business_date + timedelta(days=1)
                        ).isoformat(),
                        check_out_date=(
                            self.business_date + timedelta(days=3)
                        ).isoformat(),
                    )
                )
                self.assertFalse(form.is_valid())
                self.assertIn("room", form.errors)
                reservation.delete()

    def test_non_occupying_statuses_release_room_inventory(self):
        non_occupying_statuses = (
            Reservation.Status.CANCELLED,
            Reservation.Status.NO_SHOW,
            Reservation.Status.CHECKED_OUT,
        )
        for status in non_occupying_statuses:
            with self.subTest(status=status):
                reservation = self.create_reservation(status=status)
                form = ReservationForm(data=self.form_data())
                self.assertTrue(form.is_valid(), form.errors)
                reservation.delete()

    def test_adjacent_dates_remain_available(self):
        self.create_reservation(status=Reservation.Status.CONFIRMED)
        form = ReservationForm(
            data=self.form_data(
                check_in_date=(
                    self.business_date + timedelta(days=2)
                ).isoformat(),
                check_out_date=(
                    self.business_date + timedelta(days=3)
                ).isoformat(),
            )
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_update_still_excludes_current_reservation(self):
        reservation = self.create_reservation(status=Reservation.Status.CHECKED_IN)
        form = ReservationForm(
            data=self.form_data(additional="Changed"),
            instance=reservation,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_room_occupancy_ignores_terminal_statuses(self):
        for status in (
            Reservation.Status.CANCELLED,
            Reservation.Status.NO_SHOW,
            Reservation.Status.CHECKED_OUT,
        ):
            with self.subTest(status=status):
                reservation = self.create_reservation(
                    status=status,
                    check_in_date=timezone.localdate(),
                    check_out_date=timezone.localdate() + timedelta(days=1),
                )
                self.assertFalse(self.room.is_booked_now())
                reservation.delete()


class ReservationTransitionServiceTests(StatusTestBase):
    def assert_transition_log(self, reservation, action):
        operation_log = AdminOperationLog.objects.get(
            target_type=AdminOperationLog.TargetType.RESERVATION,
            target_id=reservation.pk,
        )
        self.assertEqual(operation_log.action, action)
        self.assertEqual(operation_log.operator, self.operator)

    def test_pending_can_be_confirmed(self):
        reservation = self.create_reservation()
        confirm_reservation(
            reservation_id=reservation.pk,
            operator=self.operator,
            business_date=self.business_date,
        )
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CONFIRMED)
        self.assert_transition_log(
            reservation, AdminOperationLog.Action.RESERVATION_CONFIRMED
        )

    def test_pending_can_be_cancelled(self):
        reservation = self.create_reservation()
        cancel_reservation(
            reservation_id=reservation.pk,
            operator=self.operator,
            business_date=self.business_date,
        )
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CANCELLED)
        self.assert_transition_log(
            reservation, AdminOperationLog.Action.RESERVATION_CANCELLED
        )

    def test_confirmed_can_check_in_on_arrival_date(self):
        reservation = self.create_reservation(status=Reservation.Status.CONFIRMED)
        check_in_reservation(
            reservation_id=reservation.pk,
            operator=self.operator,
            business_date=self.business_date,
        )
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CHECKED_IN)
        self.assert_transition_log(
            reservation, AdminOperationLog.Action.RESERVATION_CHECKED_IN
        )

    def test_checked_in_can_check_out_early(self):
        reservation = self.create_reservation(status=Reservation.Status.CHECKED_IN)
        check_out_reservation(
            reservation_id=reservation.pk,
            operator=self.operator,
            business_date=self.business_date,
        )
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CHECKED_OUT)
        self.assert_transition_log(
            reservation, AdminOperationLog.Action.RESERVATION_CHECKED_OUT
        )

    def test_pending_and_confirmed_can_be_marked_no_show_on_arrival_date(self):
        for status in (Reservation.Status.PENDING, Reservation.Status.CONFIRMED):
            with self.subTest(status=status):
                reservation = self.create_reservation(
                    status=status,
                    room=self.room if status == Reservation.Status.PENDING else self.other_room,
                )
                mark_reservation_no_show(
                    reservation_id=reservation.pk,
                    operator=self.operator,
                    business_date=self.business_date,
                )
                reservation.refresh_from_db()
                self.assertEqual(reservation.status, Reservation.Status.NO_SHOW)
                self.assert_transition_log(
                    reservation, AdminOperationLog.Action.RESERVATION_NO_SHOW
                )

    def test_pending_cannot_check_in_directly(self):
        reservation = self.create_reservation()
        with self.assertRaises(ReservationTransitionError):
            check_in_reservation(
                reservation_id=reservation.pk,
                operator=self.operator,
                business_date=self.business_date,
            )

    def test_confirmed_cannot_check_out_directly(self):
        reservation = self.create_reservation(status=Reservation.Status.CONFIRMED)
        with self.assertRaises(ReservationTransitionError):
            check_out_reservation(
                reservation_id=reservation.pk,
                operator=self.operator,
                business_date=self.business_date,
            )

    def test_terminal_statuses_cannot_transition(self):
        cases = (
            (Reservation.Status.CANCELLED, check_in_reservation),
            (Reservation.Status.CHECKED_OUT, check_in_reservation),
            (Reservation.Status.NO_SHOW, confirm_reservation),
        )
        for index, (status, transition_function) in enumerate(cases):
            with self.subTest(status=status):
                reservation = self.create_reservation(
                    status=status,
                    room=self.room if index == 0 else self.other_room,
                    check_in_date=self.business_date + timedelta(days=index * 3),
                    check_out_date=self.business_date + timedelta(days=index * 3 + 2),
                )
                with self.assertRaises(ReservationTransitionError):
                    transition_function(
                        reservation_id=reservation.pk,
                        operator=self.operator,
                        business_date=self.business_date + timedelta(days=10),
                    )
                self.assertEqual(get_allowed_transitions(reservation), [])

    def test_check_in_before_arrival_date_is_rejected(self):
        reservation = self.create_reservation(
            status=Reservation.Status.CONFIRMED,
            check_in_date=self.business_date + timedelta(days=1),
            check_out_date=self.business_date + timedelta(days=3),
        )
        with self.assertRaises(ReservationTransitionError):
            check_in_reservation(
                reservation_id=reservation.pk,
                operator=self.operator,
                business_date=self.business_date,
            )

    def test_check_in_on_or_after_checkout_date_is_rejected(self):
        for offset in (0, 1):
            with self.subTest(offset=offset):
                reservation = self.create_reservation(
                    status=Reservation.Status.CONFIRMED,
                    room=self.room if offset == 0 else self.other_room,
                    check_in_date=self.business_date - timedelta(days=2),
                    check_out_date=self.business_date,
                )
                with self.assertRaises(ReservationTransitionError):
                    check_in_reservation(
                        reservation_id=reservation.pk,
                        operator=self.operator,
                        business_date=self.business_date + timedelta(days=offset),
                    )

    def test_no_show_before_arrival_date_is_rejected(self):
        reservation = self.create_reservation(
            check_in_date=self.business_date + timedelta(days=1),
            check_out_date=self.business_date + timedelta(days=2),
        )
        with self.assertRaises(ReservationTransitionError):
            mark_reservation_no_show(
                reservation_id=reservation.pk,
                operator=self.operator,
                business_date=self.business_date,
            )

    def test_repeated_transition_does_not_write_duplicate_log(self):
        reservation = self.create_reservation()
        confirm_reservation(
            reservation_id=reservation.pk,
            operator=self.operator,
            business_date=self.business_date,
        )
        with self.assertRaises(ReservationTransitionError):
            confirm_reservation(
                reservation_id=reservation.pk,
                operator=self.operator,
                business_date=self.business_date,
            )
        self.assertEqual(
            AdminOperationLog.objects.filter(
                action=AdminOperationLog.Action.RESERVATION_CONFIRMED,
                target_id=reservation.pk,
            ).count(),
            1,
        )

    def test_log_failure_rolls_back_status_change(self):
        reservation = self.create_reservation()
        with patch(
            "main.services.AdminOperationLog.objects.create",
            side_effect=RuntimeError("simulated log failure"),
        ):
            with self.assertRaises(RuntimeError):
                confirm_reservation(
                    reservation_id=reservation.pk,
                    operator=self.operator,
                    business_date=self.business_date,
                )
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.PENDING)
        self.assertFalse(
            AdminOperationLog.objects.filter(target_id=reservation.pk).exists()
        )
