from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from main.models import Reservation
from room.models import Room

from .models import Guest


class GuestPrivacyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.guest = Guest.objects.create(
            first_name="Privacy",
            last_name="Test",
            email="privacy@example.invalid",
            phone_number="13800000000",
            government_id="SECRET-ID-1234",
            address="Test address",
        )
        cls.staff = get_user_model().objects.create_user(
            username="guest-viewer", password="test-password", is_staff=True
        )
        view_permission = Permission.objects.get(
            content_type__app_label="guest", codename="view_guest"
        )
        cls.staff.user_permissions.add(view_permission)

    def test_guest_string_does_not_include_phone_number(self):
        self.assertEqual(str(self.guest), "Privacy Test")
        self.assertNotIn(self.guest.phone_number, str(self.guest))

    def test_guest_detail_hides_government_id_without_sensitive_permission(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("guest_detail", args=[self.guest.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.guest.government_id)
        self.assertNotContains(response, "Government ID")

    def test_guest_detail_shows_only_masked_id_with_sensitive_permission(self):
        sensitive_permission = Permission.objects.get(
            content_type__app_label="guest",
            codename="view_guest_sensitive_data",
        )
        self.staff.user_permissions.add(sensitive_permission)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("guest_detail", args=[self.guest.pk]))
        self.assertContains(response, self.guest.masked_government_id)
        self.assertNotContains(response, self.guest.government_id)


class GuestHistoryProtectionTests(TestCase):
    def test_guest_with_reservation_cannot_be_deleted(self):
        guest = Guest.objects.create(
            first_name="History",
            last_name="Guest",
            email="history-guest@example.invalid",
            phone_number="0000000000",
            government_id="HISTORY-ID",
            address="Test address",
        )
        room = Room.objects.create(
            room_number="H-01", room_type="Single", price_per_night="100.00"
        )
        Reservation.objects.create(
            room=room,
            guest=guest,
            check_in_date=date(2026, 10, 1),
            check_out_date=date(2026, 10, 2),
        )

        with self.assertRaises(ProtectedError):
            guest.delete()
