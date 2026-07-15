from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from guest.models import Guest
from main.models import Reservation

from .models import Room


class RoomListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(
            username="room-viewer", password="test-password", is_staff=True
        )
        cls.staff.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="room", codename="view_room"
            )
        )
        for room_number in ["B-02", "A101", "3F01"]:
            Room.objects.create(
                room_number=room_number,
                room_type="Test",
                price_per_night="100.00",
            )

    def test_room_list_has_stable_room_number_ordering(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("room_list"))
        room_numbers = [room.room_number for room in response.context["rooms"]]
        self.assertEqual(room_numbers, ["3F01", "A101", "B-02"])


class RoomAvailabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.room = Room.objects.create(
            room_number="DATE-1", room_type="Test", price_per_night="100.00"
        )
        cls.guest = Guest.objects.create(
            first_name="Room",
            last_name="Guest",
            email="room-guest@example.invalid",
            phone_number="0000000000",
            government_id="ROOM-GUEST-ID",
            address="Test address",
        )

    def test_room_is_booked_during_half_open_date_range(self):
        today = timezone.localdate()
        Reservation.objects.create(
            room=self.room,
            guest=self.guest,
            check_in_date=today,
            check_out_date=today + timedelta(days=1),
        )
        self.assertTrue(self.room.is_booked_now())

    def test_room_is_available_on_checkout_date(self):
        today = timezone.localdate()
        Reservation.objects.create(
            room=self.room,
            guest=self.guest,
            check_in_date=today - timedelta(days=1),
            check_out_date=today,
        )
        self.assertFalse(self.room.is_booked_now())

    def test_room_with_reservation_cannot_be_deleted(self):
        today = timezone.localdate()
        Reservation.objects.create(
            room=self.room,
            guest=self.guest,
            check_in_date=today,
            check_out_date=today + timedelta(days=1),
        )
        with self.assertRaises(ProtectedError):
            self.room.delete()
