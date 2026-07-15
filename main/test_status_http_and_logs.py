from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from guest.models import Guest
from room.models import Room

from .models import AdminOperationLog, Reservation


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


class StatusHttpPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.room = Room.objects.create(
            room_number="HTTP-1", room_type="Test", price_per_night="100.00"
        )
        cls.guest = Guest.objects.create(
            first_name="HTTP",
            last_name="Guest",
            email="http-guest@example.invalid",
            phone_number="13700000000",
            government_id="HTTP-ID-1234",
            address="HTTP test address",
        )
        user_model = get_user_model()
        cls.non_staff = user_model.objects.create_user(
            username="status-non-staff", password="test-password"
        )
        cls.staff_without_permission = user_model.objects.create_user(
            username="status-staff-no-perm",
            password="test-password",
            is_staff=True,
        )
        cls.authorized_staff = user_model.objects.create_user(
            username="status-authorized",
            password="test-password",
            is_staff=True,
        )
        cls.superuser = user_model.objects.create_superuser(
            username="status-superuser",
            email="status-superuser@example.invalid",
            password="test-password",
        )

    def setUp(self):
        self.reservation = Reservation.objects.create(
            room=self.room,
            guest=self.guest,
            check_in_date=self.today,
            check_out_date=self.today + timedelta(days=2),
        )
        grant_permissions(
            self.authorized_staff,
            "main.view_reservation",
            "main.manage_reservation_status",
        )

    def test_anonymous_user_cannot_execute_status_operation(self):
        response = self.client.post(
            reverse("reservation_confirm", args=[self.reservation.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)

    def test_non_staff_user_cannot_execute_status_operation(self):
        grant_permissions(
            self.non_staff,
            "main.view_reservation",
            "main.manage_reservation_status",
        )
        self.client.force_login(self.non_staff)
        response = self.client.post(
            reverse("reservation_confirm", args=[self.reservation.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_without_manage_permission_cannot_execute_status_operation(self):
        grant_permissions(self.staff_without_permission, "main.view_reservation")
        self.client.force_login(self.staff_without_permission)
        response = self.client.post(
            reverse("reservation_confirm", args=[self.reservation.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_authorized_staff_can_execute_status_operation(self):
        self.client.force_login(self.authorized_staff)
        response = self.client.post(
            reverse("reservation_confirm", args=[self.reservation.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.CONFIRMED)

    def test_get_request_only_displays_confirmation(self):
        self.client.force_login(self.authorized_staff)
        response = self.client.get(
            reverse("reservation_confirm", args=[self.reservation.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_status_post_is_csrf_protected(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.authorized_staff)
        response = csrf_client.post(
            reverse("reservation_confirm", args=[self.reservation.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)

    def test_arbitrary_posted_status_cannot_bypass_explicit_action(self):
        self.client.force_login(self.authorized_staff)
        self.client.post(
            reverse("reservation_confirm", args=[self.reservation.pk]),
            {"status": Reservation.Status.CHECKED_OUT},
        )
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.CONFIRMED)

    def test_illegal_action_returns_clear_response_without_mutation(self):
        self.client.force_login(self.authorized_staff)
        response = self.client.post(
            reverse("reservation_check_in", args=[self.reservation.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_superuser_has_all_status_permissions(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("reservation_confirm", args=[self.reservation.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.CONFIRMED)

    def test_staff_without_log_permission_cannot_view_logs(self):
        self.client.force_login(self.staff_without_permission)
        response = self.client.get(reverse("operation_log_list"))
        self.assertEqual(response.status_code, 403)

    def test_staff_with_log_permission_can_view_logs(self):
        grant_permissions(
            self.staff_without_permission,
            "main.view_adminoperationlog",
        )
        self.client.force_login(self.staff_without_permission)
        response = self.client.get(reverse("operation_log_list"))
        self.assertEqual(response.status_code, 200)


class CrudOperationLogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.room = Room.objects.create(
            room_number="LOG-1", room_type="Test", price_per_night="100.00"
        )
        cls.guest = Guest.objects.create(
            first_name="Log",
            last_name="Guest",
            email="log-guest@example.invalid",
            phone_number="13612345678",
            government_id="LOG-SECRET-1234",
            address="Sensitive test address",
        )
        cls.staff = get_user_model().objects.create_user(
            username="crud-logger",
            password="test-password",
            is_staff=True,
        )
        grant_permissions(
            cls.staff,
            "main.view_reservation",
            "main.add_reservation",
            "main.change_reservation",
            "room.add_room",
            "room.change_room",
            "guest.add_guest",
            "guest.change_guest",
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def reservation_data(self, **overrides):
        values = {
            "room": self.room.pk,
            "guest": self.guest.pk,
            "additional": "",
            "check_in_date": self.today.isoformat(),
            "check_out_date": (self.today + timedelta(days=2)).isoformat(),
        }
        values.update(overrides)
        return values

    def test_create_reservation_writes_sanitized_log_and_ignores_status_post(self):
        response = self.client.post(
            reverse("reservation_create"),
            self.reservation_data(
                additional="private additional text",
                status=Reservation.Status.CHECKED_OUT,
            ),
        )
        self.assertEqual(response.status_code, 302)
        reservation = Reservation.objects.get()
        self.assertEqual(reservation.status, Reservation.Status.PENDING)
        operation_log = AdminOperationLog.objects.get()
        self.assertEqual(
            operation_log.action, AdminOperationLog.Action.RESERVATION_CREATED
        )
        self.assertNotIn("private additional text", operation_log.description)
        self.assertNotIn(self.guest.phone_number, operation_log.description)
        self.assertNotIn(self.guest.government_id, operation_log.description)

    def test_update_reservation_logs_only_changed_field_categories(self):
        reservation = Reservation.objects.create(
            room=self.room,
            guest=self.guest,
            additional="",
            check_in_date=self.today,
            check_out_date=self.today + timedelta(days=2),
        )
        sensitive_text = "do not copy this additional body"
        response = self.client.post(
            reverse("reservation_update", args=[reservation.pk]),
            self.reservation_data(additional=sensitive_text),
        )
        self.assertEqual(response.status_code, 302)
        operation_log = AdminOperationLog.objects.get()
        self.assertEqual(
            operation_log.action, AdminOperationLog.Action.RESERVATION_UPDATED
        )
        self.assertIn("additional", operation_log.description)
        self.assertNotIn(sensitive_text, operation_log.description)

    def test_unchanged_reservation_does_not_write_update_log(self):
        reservation = Reservation.objects.create(
            room=self.room,
            guest=self.guest,
            additional="",
            check_in_date=self.today,
            check_out_date=self.today + timedelta(days=2),
        )
        response = self.client.post(
            reverse("reservation_update", args=[reservation.pk]),
            self.reservation_data(),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_failed_reservation_creation_does_not_write_log(self):
        Reservation.objects.create(
            room=self.room,
            guest=self.guest,
            check_in_date=self.today,
            check_out_date=self.today + timedelta(days=2),
        )
        response = self.client.post(
            reverse("reservation_create"), self.reservation_data()
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_room_and_guest_views_write_only_non_sensitive_logs(self):
        room_response = self.client.post(
            reverse("room_create"),
            {
                "room_number": "LOG-NEW",
                "room_type": "Suite",
                "price_per_night": "320.00",
            },
        )
        self.assertEqual(room_response.status_code, 302)
        guest_response = self.client.post(
            reverse("guest_create"),
            {
                "first_name": "Sensitive",
                "last_name": "Guest",
                "email": "sensitive-log@example.invalid",
                "phone_number": "13587654321",
                "government_id": "PRIVATE-ID-5678",
                "address": "Private address value",
            },
        )
        self.assertEqual(guest_response.status_code, 302)
        created_room = Room.objects.get(room_number="LOG-NEW")
        room_update_response = self.client.post(
            reverse("room_update", args=[created_room.pk]),
            {
                "room_number": "LOG-NEW",
                "room_type": "Updated Suite",
                "price_per_night": "320.00",
            },
        )
        self.assertEqual(room_update_response.status_code, 302)
        created_guest = Guest.objects.get(email="sensitive-log@example.invalid")
        guest_update_response = self.client.post(
            reverse("guest_update", args=[created_guest.pk]),
            {
                "first_name": "Sensitive",
                "last_name": "Guest",
                "email": "sensitive-log@example.invalid",
                "phone_number": "13500000000",
                "address": "Another private address",
            },
        )
        self.assertEqual(guest_update_response.status_code, 302)
        descriptions = " ".join(
            AdminOperationLog.objects.values_list("description", flat=True)
        )
        self.assertNotIn("13587654321", descriptions)
        self.assertNotIn("PRIVATE-ID-5678", descriptions)
        self.assertNotIn("Private address value", descriptions)
        self.assertTrue(
            AdminOperationLog.objects.filter(
                action=AdminOperationLog.Action.ROOM_CREATED
            ).exists()
        )
        self.assertTrue(
            AdminOperationLog.objects.filter(
                action=AdminOperationLog.Action.GUEST_CREATED
            ).exists()
        )
        self.assertTrue(
            AdminOperationLog.objects.filter(
                action=AdminOperationLog.Action.ROOM_UPDATED
            ).exists()
        )
        self.assertTrue(
            AdminOperationLog.objects.filter(
                action=AdminOperationLog.Action.GUEST_UPDATED
            ).exists()
        )
        self.assertNotIn("13500000000", descriptions)
        self.assertNotIn("Another private address", descriptions)

    def test_deleted_operator_does_not_delete_log(self):
        reservation = Reservation.objects.create(
            room=self.room,
            guest=self.guest,
            check_in_date=self.today,
            check_out_date=self.today + timedelta(days=2),
        )
        operation_log = AdminOperationLog.objects.create(
            operator=self.staff,
            action=AdminOperationLog.Action.RESERVATION_CREATED,
            target_type=AdminOperationLog.TargetType.RESERVATION,
            target_id=reservation.pk,
            description=f"Reservation #{reservation.pk} created.",
        )
        self.staff.delete()
        operation_log.refresh_from_db()
        self.assertIsNone(operation_log.operator)

    def test_operation_log_ordering_and_indexes_are_configured(self):
        self.assertEqual(
            AdminOperationLog._meta.ordering,
            ["-created_at", "-id"],
        )
        for field_name in ("created_at", "action", "target_type", "target_id"):
            with self.subTest(field=field_name):
                self.assertTrue(
                    AdminOperationLog._meta.get_field(field_name).db_index
                )
        self.assertIn(
            ["target_type", "target_id"],
            [index.fields for index in AdminOperationLog._meta.indexes],
        )


class AdminWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.superuser = get_user_model().objects.create_superuser(
            username="admin-workflow",
            email="admin-workflow@example.invalid",
            password="test-password",
        )
        cls.room = Room.objects.create(
            room_number="ADMIN-1", room_type="Test", price_per_night="100.00"
        )
        cls.guest = Guest.objects.create(
            first_name="Admin",
            last_name="Guest",
            email="admin-guest@example.invalid",
            phone_number="13400000000",
            government_id="ADMIN-ID-1234",
            address="Admin test address",
        )

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_admin_reservation_create_and_update_are_logged(self):
        add_response = self.client.post(
            reverse("admin:main_reservation_add"),
            {
                "room": self.room.pk,
                "guest": self.guest.pk,
                "additional": "",
                "check_in_date": self.today.isoformat(),
                "check_out_date": (self.today + timedelta(days=2)).isoformat(),
                "_save": "Save",
            },
        )
        self.assertEqual(add_response.status_code, 302)
        reservation = Reservation.objects.get()
        self.assertEqual(reservation.status, Reservation.Status.PENDING)
        self.assertEqual(
            AdminOperationLog.objects.filter(
                action=AdminOperationLog.Action.RESERVATION_CREATED
            ).count(),
            1,
        )

        change_response = self.client.post(
            reverse("admin:main_reservation_change", args=[reservation.pk]),
            {
                "room": self.room.pk,
                "guest": self.guest.pk,
                "additional": "changed in admin",
                "status": Reservation.Status.CANCELLED,
                "check_in_date": self.today.isoformat(),
                "check_out_date": (self.today + timedelta(days=2)).isoformat(),
                "_save": "Save",
            },
        )
        self.assertEqual(change_response.status_code, 302)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.PENDING)
        updated_log = AdminOperationLog.objects.get(
            action=AdminOperationLog.Action.RESERVATION_UPDATED
        )
        self.assertIn("additional", updated_log.description)
        self.assertNotIn("changed in admin", updated_log.description)

    def test_admin_status_action_uses_transition_service(self):
        reservation = Reservation.objects.create(
            room=self.room,
            guest=self.guest,
            check_in_date=self.today,
            check_out_date=self.today + timedelta(days=2),
        )
        response = self.client.post(
            reverse("admin:main_reservation_changelist"),
            {
                "action": "confirm_selected",
                "_selected_action": [str(reservation.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CONFIRMED)
        self.assertTrue(
            AdminOperationLog.objects.filter(
                action=AdminOperationLog.Action.RESERVATION_CONFIRMED,
                target_id=reservation.pk,
            ).exists()
        )

    def test_operation_log_admin_is_immutable_even_for_superuser(self):
        log_admin = admin.site._registry[AdminOperationLog]
        request = type("Request", (), {"user": self.superuser})()
        self.assertFalse(log_admin.has_add_permission(request))
        self.assertFalse(log_admin.has_change_permission(request))
        self.assertFalse(log_admin.has_delete_permission(request))

    def test_admin_status_actions_are_hidden_without_manage_permission(self):
        staff = get_user_model().objects.create_user(
            username="admin-without-status-permission",
            password="test-password",
            is_staff=True,
        )
        grant_permissions(staff, "main.view_reservation")
        reservation_admin = admin.site._registry[Reservation]
        request = type("Request", (), {"user": staff, "GET": {}})()
        actions = reservation_admin.get_actions(request)
        for action_name in reservation_admin.actions:
            self.assertNotIn(action_name, actions)


class ReservationStatusFilterAndDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.room = Room.objects.create(
            room_number="FILTER-1", room_type="Test", price_per_night="100.00"
        )
        cls.guest = Guest.objects.create(
            first_name="Filter",
            last_name="Guest",
            email="filter-guest@example.invalid",
            phone_number="13300000000",
            government_id="FILTER-ID-1234",
            address="Filter test address",
        )
        cls.staff = get_user_model().objects.create_user(
            username="filter-staff", password="test-password", is_staff=True
        )
        grant_permissions(cls.staff, "main.view_reservation")

    def setUp(self):
        self.client.force_login(self.staff)

    def create_reservation(self, status, check_in_offset=0, check_out_offset=1):
        return Reservation.objects.create(
            room=self.room,
            guest=self.guest,
            status=status,
            check_in_date=self.today + timedelta(days=check_in_offset),
            check_out_date=self.today + timedelta(days=check_out_offset),
        )

    def test_legal_status_filters_reservations(self):
        pending = self.create_reservation(Reservation.Status.PENDING)
        self.create_reservation(
            Reservation.Status.CANCELLED, check_in_offset=3, check_out_offset=4
        )
        response = self.client.get(
            reverse("reservation_list"), {"status": Reservation.Status.PENDING}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["reservations"]), [pending])

    def test_illegal_status_filter_is_ignored_without_error(self):
        self.create_reservation(Reservation.Status.PENDING)
        self.create_reservation(
            Reservation.Status.CANCELLED, check_in_offset=3, check_out_offset=4
        )
        response = self.client.get(
            reverse("reservation_list"), {"status": "not-a-real-status"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["reservations"]), 2)

    def test_pagination_preserves_status_filter(self):
        for offset in range(11):
            self.create_reservation(
                Reservation.Status.CANCELLED,
                check_in_offset=offset * 2,
                check_out_offset=offset * 2 + 1,
            )
        response = self.client.get(
            reverse("reservation_list"), {"status": Reservation.Status.CANCELLED}
        )
        self.assertContains(response, "status=cancelled&amp;page=2")

    def test_dashboard_status_statistics_match_definitions(self):
        self.create_reservation(Reservation.Status.PENDING)
        self.create_reservation(
            Reservation.Status.CONFIRMED, check_in_offset=0, check_out_offset=2
        )
        self.create_reservation(
            Reservation.Status.CONFIRMED, check_in_offset=3, check_out_offset=5
        )
        self.create_reservation(
            Reservation.Status.CHECKED_IN, check_in_offset=-2, check_out_offset=0
        )
        self.create_reservation(
            Reservation.Status.CHECKED_IN, check_in_offset=-1, check_out_offset=2
        )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["pending_reservations"], 1)
        self.assertEqual(response.context["confirmed_reservations"], 2)
        self.assertEqual(response.context["today_check_ins"], 1)
        self.assertEqual(response.context["today_check_outs"], 1)
        self.assertEqual(response.context["current_checked_in"], 2)
