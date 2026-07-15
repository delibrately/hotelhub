from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from guest.models import Guest
from room.models import Room

from .admin import ReservationAdmin
from .forms import ReservationForm
from .models import Reservation


def grant_permissions(user, *permission_names):
    permissions = []
    for permission_name in permission_names:
        app_label, codename = permission_name.split(".", 1)
        permissions.append(
            Permission.objects.get(
                content_type__app_label=app_label,
                codename=codename,
            )
        )
    user.user_permissions.add(*permissions)


class BaseReservationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.room_a = Room.objects.create(
            room_number="A101", room_type="Double", price_per_night="280.00"
        )
        cls.room_b = Room.objects.create(
            room_number="B-02", room_type="Single", price_per_night="180.00"
        )
        cls.guest = Guest.objects.create(
            first_name="Test",
            last_name="Guest",
            email="guest@example.invalid",
            phone_number="0000000000",
            government_id="TEST-ID-1234",
            address="Test address",
        )

    def reservation_data(self, **overrides):
        data = {
            "room": self.room_a.pk,
            "guest": self.guest.pk,
            "additional": "",
            "check_in_date": "2026-08-10",
            "check_out_date": "2026-08-12",
        }
        data.update(overrides)
        return data


class ManagementPermissionTests(BaseReservationTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        user_model = get_user_model()
        cls.normal_user = user_model.objects.create_user(
            username="normal-user", password="test-password"
        )
        cls.staff_user = user_model.objects.create_user(
            username="staff-user", password="test-password", is_staff=True
        )
        cls.superuser = user_model.objects.create_superuser(
            username="superuser",
            email="superuser@example.invalid",
            password="test-password",
        )
        cls.reservation = Reservation.objects.create(
            room=cls.room_a,
            guest=cls.guest,
            check_in_date=date(2026, 8, 10),
            check_out_date=date(2026, 8, 12),
        )

    def management_urls(self):
        return [
            reverse("dashboard"),
            reverse("room_list"),
            reverse("room_detail", args=[self.room_a.pk]),
            reverse("room_create"),
            reverse("room_update", args=[self.room_a.pk]),
            reverse("guest_list"),
            reverse("guest_detail", args=[self.guest.pk]),
            reverse("guest_create"),
            reverse("guest_update", args=[self.guest.pk]),
            reverse("reservation_list"),
            reverse("reservation_detail", args=[self.reservation.pk]),
            reverse("reservation_create"),
            reverse("reservation_update", args=[self.reservation.pk]),
        ]

    def test_anonymous_dashboard_redirects_to_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_anonymous_users_cannot_access_management_pages(self):
        for url in self.management_urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response.url)

    def test_non_staff_users_cannot_access_management_pages(self):
        self.client.force_login(self.normal_user)
        for url in self.management_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_staff_with_permissions_can_access_corresponding_pages(self):
        grant_permissions(
            self.staff_user,
            "room.view_room",
            "room.add_room",
            "room.change_room",
            "guest.view_guest",
            "guest.add_guest",
            "guest.change_guest",
            "main.view_reservation",
            "main.add_reservation",
            "main.change_reservation",
        )
        self.client.force_login(self.staff_user)
        for url in self.management_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_staff_without_change_permission_cannot_update_reservation(self):
        grant_permissions(self.staff_user, "main.view_reservation")
        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse("reservation_update", args=[self.reservation.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_access_all_management_pages(self):
        self.client.force_login(self.superuser)
        for url in self.management_urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_dashboard_only_contains_permitted_counts(self):
        grant_permissions(self.staff_user, "room.view_room")
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_rooms"], 2)
        self.assertIsNone(response.context["total_guests"])
        self.assertIsNone(response.context["total_reservations"])
        self.assertNotContains(response, "Total Guests")

    def test_profile_remains_available_to_non_staff_user(self):
        self.client.force_login(self.normal_user)
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)


class ReservationFormValidationTests(BaseReservationTestCase):
    def test_admin_uses_shared_reservation_form(self):
        self.assertIs(ReservationAdmin.form, ReservationForm)

    def test_valid_date_range_is_accepted(self):
        self.assertTrue(ReservationForm(data=self.reservation_data()).is_valid())

    def test_dates_are_required(self):
        form = ReservationForm(
            data=self.reservation_data(check_in_date="", check_out_date="")
        )
        self.assertFalse(form.is_valid())
        self.assertIn("check_in_date", form.errors)
        self.assertIn("check_out_date", form.errors)

    def test_empty_room_returns_form_error_without_conflict_query_failure(self):
        form = ReservationForm(data=self.reservation_data(room=""))
        self.assertFalse(form.is_valid())
        self.assertIn("room", form.errors)

    def test_equal_dates_are_rejected(self):
        form = ReservationForm(
            data=self.reservation_data(check_out_date="2026-08-10")
        )
        self.assertFalse(form.is_valid())
        self.assertIn("check_out_date", form.errors)

    def test_check_in_after_check_out_is_rejected(self):
        form = ReservationForm(
            data=self.reservation_data(
                check_in_date="2026-08-13", check_out_date="2026-08-12"
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn("check_out_date", form.errors)

    def test_overlapping_reservation_for_same_room_is_rejected(self):
        Reservation.objects.create(
            room=self.room_a,
            guest=self.guest,
            check_in_date=date(2026, 8, 10),
            check_out_date=date(2026, 8, 12),
        )
        form = ReservationForm(
            data=self.reservation_data(
                check_in_date="2026-08-11", check_out_date="2026-08-13"
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn("room", form.errors)

    def test_same_dates_for_different_rooms_are_accepted(self):
        Reservation.objects.create(
            room=self.room_a,
            guest=self.guest,
            check_in_date=date(2026, 8, 10),
            check_out_date=date(2026, 8, 12),
        )
        form = ReservationForm(
            data=self.reservation_data(room=self.room_b.pk)
        )
        self.assertTrue(form.is_valid())

    def test_adjacent_reservation_is_accepted(self):
        Reservation.objects.create(
            room=self.room_a,
            guest=self.guest,
            check_in_date=date(2026, 8, 10),
            check_out_date=date(2026, 8, 12),
        )
        form = ReservationForm(
            data=self.reservation_data(
                check_in_date="2026-08-12", check_out_date="2026-08-14"
            )
        )
        self.assertTrue(form.is_valid())

    def test_updating_reservation_does_not_conflict_with_itself(self):
        reservation = Reservation.objects.create(
            room=self.room_a,
            guest=self.guest,
            check_in_date=date(2026, 8, 10),
            check_out_date=date(2026, 8, 12),
        )
        form = ReservationForm(
            data=self.reservation_data(additional="Updated"),
            instance=reservation,
        )
        self.assertTrue(form.is_valid())

    def test_updating_reservation_to_overlap_is_rejected(self):
        Reservation.objects.create(
            room=self.room_a,
            guest=self.guest,
            check_in_date=date(2026, 8, 10),
            check_out_date=date(2026, 8, 12),
        )
        reservation = Reservation.objects.create(
            room=self.room_a,
            guest=self.guest,
            check_in_date=date(2026, 8, 14),
            check_out_date=date(2026, 8, 16),
        )
        form = ReservationForm(
            data=self.reservation_data(
                check_in_date="2026-08-11", check_out_date="2026-08-15"
            ),
            instance=reservation,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("room", form.errors)

    def test_updating_reservation_to_non_overlapping_dates_is_accepted(self):
        Reservation.objects.create(
            room=self.room_a,
            guest=self.guest,
            check_in_date=date(2026, 8, 10),
            check_out_date=date(2026, 8, 12),
        )
        reservation = Reservation.objects.create(
            room=self.room_a,
            guest=self.guest,
            check_in_date=date(2026, 8, 14),
            check_out_date=date(2026, 8, 16),
        )
        form = ReservationForm(
            data=self.reservation_data(
                check_in_date="2026-08-12", check_out_date="2026-08-14"
            ),
            instance=reservation,
        )
        self.assertTrue(form.is_valid())

    def test_database_constraint_rejects_invalid_date_range(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Reservation.objects.create(
                    room=self.room_a,
                    guest=self.guest,
                    check_in_date=date(2026, 8, 10),
                    check_out_date=date(2026, 8, 10),
                )

    def test_model_full_clean_rejects_room_overlap(self):
        Reservation.objects.create(
            room=self.room_a,
            guest=self.guest,
            check_in_date=date(2026, 8, 10),
            check_out_date=date(2026, 8, 12),
        )
        reservation = Reservation(
            room=self.room_a,
            guest=self.guest,
            check_in_date=date(2026, 8, 11),
            check_out_date=date(2026, 8, 13),
        )
        with self.assertRaisesMessage(
            ValidationError, "This room is already booked for the selected dates."
        ):
            reservation.full_clean()


class ReservationViewValidationTests(BaseReservationTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.staff_user = get_user_model().objects.create_user(
            username="reservation-editor",
            password="test-password",
            is_staff=True,
        )
        cls.reservation = Reservation.objects.create(
            room=cls.room_a,
            guest=cls.guest,
            check_in_date=date(2026, 8, 10),
            check_out_date=date(2026, 8, 12),
        )

    def setUp(self):
        grant_permissions(
            self.staff_user,
            "main.add_reservation",
            "main.change_reservation",
            "main.view_reservation",
        )
        self.client.force_login(self.staff_user)

    def test_update_view_saves_unchanged_dates(self):
        response = self.client.post(
            reverse("reservation_update", args=[self.reservation.pk]),
            self.reservation_data(additional="Only this changed"),
        )
        self.assertEqual(response.status_code, 302)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.additional, "Only this changed")

    def test_update_view_rejects_overlap_with_another_reservation(self):
        other = Reservation.objects.create(
            room=self.room_a,
            guest=self.guest,
            check_in_date=date(2026, 8, 14),
            check_out_date=date(2026, 8, 16),
        )
        response = self.client.post(
            reverse("reservation_update", args=[other.pk]),
            self.reservation_data(
                check_in_date="2026-08-11", check_out_date="2026-08-15"
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "room",
            "This room is already booked for the selected dates.",
        )

    def test_update_view_saves_non_overlapping_dates(self):
        other = Reservation.objects.create(
            room=self.room_a,
            guest=self.guest,
            check_in_date=date(2026, 8, 14),
            check_out_date=date(2026, 8, 16),
        )
        response = self.client.post(
            reverse("reservation_update", args=[other.pk]),
            self.reservation_data(
                check_in_date="2026-08-12", check_out_date="2026-08-14"
            ),
        )
        self.assertEqual(response.status_code, 302)
        other.refresh_from_db()
        self.assertEqual(other.check_in_date, date(2026, 8, 12))
        self.assertEqual(other.check_out_date, date(2026, 8, 14))

    def test_create_view_cannot_bypass_overlap_validation(self):
        response = self.client.post(
            reverse("reservation_create"),
            self.reservation_data(
                check_in_date="2026-08-11", check_out_date="2026-08-13"
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Reservation.objects.filter(room=self.room_a).count(), 1)

    def test_alphanumeric_room_filter_does_not_raise_an_error(self):
        response = self.client.get(
            reverse("reservation_list"), {"room_number": "A101"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["reservations"]), [self.reservation])

    def test_pagination_preserves_room_filter(self):
        for offset in range(1, 11):
            check_in = date(2026, 9, 1) + timedelta(days=offset * 2)
            Reservation.objects.create(
                room=self.room_a,
                guest=self.guest,
                check_in_date=check_in,
                check_out_date=check_in + timedelta(days=1),
            )
        response = self.client.get(
            reverse("reservation_list"), {"room_number": "A101"}
        )
        self.assertContains(response, "room_number=A101&amp;page=2")
